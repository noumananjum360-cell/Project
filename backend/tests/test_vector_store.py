"""Vector store implementations: user scoping, persistence and similarity ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.mock_provider import hashed_embedding
from app.vector_store.stores import ChromaVectorStore, FaissVectorStore, InMemoryVectorStore

DOCS = {
    "react": "React TypeScript dashboard with charts and filters",
    "ml": "Machine learning model training with PyTorch for image classification",
    "wp": "WordPress WooCommerce shop theme customisation",
}


def _stores(tmp_path: Path) -> list:  # type: ignore[type-arg]
    return [
        ChromaVectorStore(str(tmp_path / "chroma")),
        FaissVectorStore(str(tmp_path / "faiss")),
        InMemoryVectorStore(),
    ]


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_store_ranking_and_isolation(tmp_path: Path, idx: int) -> None:
    store = _stores(tmp_path)[idx]
    for key, text in DOCS.items():
        store.upsert(namespace="portfolio__t", user_id="u1", item_id=f"u1-{key}", vector=hashed_embedding(text), content_hash=key)
    store.upsert(
        namespace="portfolio__t", user_id="u2", item_id="u2-react", vector=hashed_embedding(DOCS["react"]), content_hash="x"
    )

    hits = store.query(
        namespace="portfolio__t", user_id="u1", vector=hashed_embedding("Need a React dashboard developer"), top_k=3
    )
    assert hits[0].item_id == "u1-react"
    assert all(h.item_id.startswith("u1-") for h in hits)
    assert store.count(namespace="portfolio__t", user_id="u1") == 3

    store.delete(namespace="portfolio__t", user_id="u1", item_ids=["u1-react"])
    assert store.count(namespace="portfolio__t", user_id="u1") == 2
    store.delete_user(user_id="u2")
    assert store.count(namespace="portfolio__t", user_id="u2") == 0


def test_chroma_persists_across_instances(tmp_path: Path) -> None:
    s1 = ChromaVectorStore(str(tmp_path / "c"))
    s1.upsert(namespace="ns", user_id="u", item_id="a", vector=hashed_embedding("python api"), content_hash="h")
    s2 = ChromaVectorStore(str(tmp_path / "c"))
    assert s2.count(namespace="ns", user_id="u") == 1
