from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.vector_store.base import VectorStore
from app.vector_store.stores import ChromaVectorStore, FaissVectorStore, InMemoryVectorStore

_override: VectorStore | None = None


def set_vector_store_override(store: VectorStore | None) -> None:
    global _override
    _override = store


@lru_cache
def _build() -> VectorStore:
    s = get_settings()
    if s.VECTOR_STORE == "faiss":
        return FaissVectorStore(s.FAISS_INDEX_DIRECTORY)
    if s.VECTOR_STORE == "memory":
        return InMemoryVectorStore()
    return ChromaVectorStore(s.CHROMA_PERSIST_DIRECTORY)


def get_vector_store() -> VectorStore:
    return _override or _build()
