"""Vector store abstraction.

Every operation is scoped by ``user_id``. Results are candidates only: the
caller must re-check ownership against PostgreSQL, which remains the
authoritative source for permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class VectorHit:
    item_id: str
    score: float  # cosine similarity in [-1, 1]


class VectorStore(Protocol):
    backend: str

    def upsert(self, *, namespace: str, user_id: str, item_id: str, vector: list[float], content_hash: str) -> None: ...

    def delete(self, *, namespace: str, user_id: str, item_ids: list[str]) -> None: ...

    def delete_user(self, *, user_id: str) -> None: ...

    def query(self, *, namespace: str, user_id: str, vector: list[float], top_k: int) -> list[VectorHit]: ...

    def count(self, *, namespace: str, user_id: str) -> int: ...

    def healthy(self) -> bool: ...
