"""Provider-agnostic AI interfaces. Business logic depends only on these types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


@dataclass
class CompletionResult[TModel: BaseModel]:
    data: TModel
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    is_simulated: bool = False


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    is_simulated: bool = False


class AIProvider(Protocol):
    name: str
    chat_model: str
    embedding_model: str
    is_simulated: bool

    def complete_structured(
        self, *, system: str, user: str, schema: type[TModel], operation: str, temperature: float = 0.3
    ) -> CompletionResult[TModel]: ...

    def embed(self, texts: list[str]) -> EmbeddingResult: ...
