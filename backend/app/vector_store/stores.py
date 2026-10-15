"""Vector store implementations: ChromaDB (default), FAISS and in-memory."""

from __future__ import annotations

import json
import math
import os
import re
import threading
from pathlib import Path
from typing import Any

from app.vector_store.base import VectorHit


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name)[:60].strip("-") or "default"


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class ChromaVectorStore:
    backend = "chroma"

    def __init__(self, persist_directory: str) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_directory, settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False)
        )

    def _collection(self, namespace: str) -> Any:
        # Chroma names: 3-512 chars of [a-zA-Z0-9._-], alphanumeric at both ends.
        return self._client.get_or_create_collection(name=f"bg-{_safe(namespace)}", metadata={"hnsw:space": "cosine"})

    def upsert(self, *, namespace: str, user_id: str, item_id: str, vector: list[float], content_hash: str) -> None:
        self._collection(namespace).upsert(
            ids=[item_id], embeddings=[vector], metadatas=[{"user_id": user_id, "content_hash": content_hash}]
        )

    def delete(self, *, namespace: str, user_id: str, item_ids: list[str]) -> None:
        if item_ids:
            self._collection(namespace).delete(ids=item_ids, where={"user_id": user_id})

    def delete_user(self, *, user_id: str) -> None:
        for col in self._client.list_collections():
            name = col if isinstance(col, str) else col.name
            self._client.get_collection(name).delete(where={"user_id": user_id})

    def query(self, *, namespace: str, user_id: str, vector: list[float], top_k: int) -> list[VectorHit]:
        col = self._collection(namespace)
        n = self.count(namespace=namespace, user_id=user_id)
        if n == 0:
            return []
        res = col.query(query_embeddings=[vector], n_results=min(top_k, n), where={"user_id": user_id})
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        return [VectorHit(item_id=i, score=round(1.0 - float(d), 4)) for i, d in zip(ids, dists, strict=False)]

    def count(self, *, namespace: str, user_id: str) -> int:
        got = self._collection(namespace).get(where={"user_id": user_id}, include=[])
        return len(got.get("ids") or [])

    def healthy(self) -> bool:
        try:
            self._client.heartbeat()
            return True
        except Exception:  # noqa: BLE001
            return False


class FaissVectorStore:
    """FAISS-backed store: one flat inner-product index per (namespace, user).

    Vectors and ids are persisted to disk so they survive restarts; the index
    is rebuilt in memory on load (portfolio collections are small).
    """

    backend = "faiss"

    def __init__(self, directory: str) -> None:
        import faiss  # noqa: F401  (fail fast if not installed)

        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, namespace: str, user_id: str) -> Path:
        return self._dir / _safe(namespace) / f"{_safe(user_id)}.json"

    def _load(self, namespace: str, user_id: str) -> dict[str, dict[str, Any]]:
        p = self._path(namespace, user_id)
        if not p.exists():
            return {}
        return json.loads(p.read_text())

    def _save(self, namespace: str, user_id: str, data: dict[str, dict[str, Any]]) -> None:
        p = self._path(namespace, user_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, p)

    def upsert(self, *, namespace: str, user_id: str, item_id: str, vector: list[float], content_hash: str) -> None:
        with self._lock:
            data = self._load(namespace, user_id)
            data[item_id] = {"v": _normalize(vector), "h": content_hash}
            self._save(namespace, user_id, data)

    def delete(self, *, namespace: str, user_id: str, item_ids: list[str]) -> None:
        with self._lock:
            data = self._load(namespace, user_id)
            for i in item_ids:
                data.pop(i, None)
            self._save(namespace, user_id, data)

    def delete_user(self, *, user_id: str) -> None:
        with self._lock:
            for p in self._dir.glob(f"*/{_safe(user_id)}.json"):
                p.unlink(missing_ok=True)

    def query(self, *, namespace: str, user_id: str, vector: list[float], top_k: int) -> list[VectorHit]:
        import faiss
        import numpy as np

        data = self._load(namespace, user_id)
        if not data:
            return []
        ids = list(data.keys())
        mat = np.array([data[i]["v"] for i in ids], dtype="float32")
        index = faiss.IndexFlatIP(mat.shape[1])
        index.add(mat)
        q = np.array([_normalize(vector)], dtype="float32")
        scores, idx = index.search(q, min(top_k, len(ids)))
        return [VectorHit(item_id=ids[j], score=round(float(s), 4)) for s, j in zip(scores[0], idx[0], strict=False) if j >= 0]

    def count(self, *, namespace: str, user_id: str) -> int:
        return len(self._load(namespace, user_id))

    def healthy(self) -> bool:
        return self._dir.exists()


class InMemoryVectorStore:
    """Non-persistent store for unit tests only."""

    backend = "memory"

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], dict[str, list[float]]] = {}

    def upsert(self, *, namespace: str, user_id: str, item_id: str, vector: list[float], content_hash: str) -> None:
        self._data.setdefault((namespace, user_id), {})[item_id] = _normalize(vector)

    def delete(self, *, namespace: str, user_id: str, item_ids: list[str]) -> None:
        bucket = self._data.get((namespace, user_id), {})
        for i in item_ids:
            bucket.pop(i, None)

    def delete_user(self, *, user_id: str) -> None:
        for key in [k for k in self._data if k[1] == user_id]:
            del self._data[key]

    def query(self, *, namespace: str, user_id: str, vector: list[float], top_k: int) -> list[VectorHit]:
        q = _normalize(vector)
        bucket = self._data.get((namespace, user_id), {})
        hits = [VectorHit(i, round(sum(a * b for a, b in zip(q, v, strict=False)), 4)) for i, v in bucket.items()]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def count(self, *, namespace: str, user_id: str) -> int:
        return len(self._data.get((namespace, user_id), {}))

    def healthy(self) -> bool:
        return True
