"""OpenAI (and OpenAI-compatible) provider with structured, validated output."""

from __future__ import annotations

import json
import time

import openai
from pydantic import BaseModel, ValidationError

from app.ai.base import CompletionResult, EmbeddingResult, TModel, Usage
from app.core.errors import AIOutputError, AIUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)


def _schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))


class OpenAIProvider:
    is_simulated = False

    def __init__(
        self,
        *,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        timeout: float,
        max_retries: int,
        base_url: str | None = None,
        name: str = "openai",
    ) -> None:
        self.name = name
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        # The SDK performs bounded retries with exponential backoff on 429/5xx/timeouts.
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

    @staticmethod
    def _translate(exc: Exception) -> Exception:
        if isinstance(exc, openai.AuthenticationError):
            return AIUnavailableError("The AI provider rejected the configured API key.", code="ai_auth_failed")
        if isinstance(exc, openai.RateLimitError):
            return AIUnavailableError(
                "The AI provider is rate limiting requests. Please try again shortly.", code="ai_rate_limited"
            )
        if isinstance(exc, openai.APITimeoutError):
            return AIUnavailableError("The AI provider timed out. Please try again.", code="ai_timeout")
        if isinstance(exc, openai.APIConnectionError):
            return AIUnavailableError("Could not reach the AI provider.", code="ai_connection_failed")
        if isinstance(exc, openai.APIStatusError):
            return AIUnavailableError(f"The AI provider returned an error (HTTP {exc.status_code}).", code="ai_error")
        return AIUnavailableError("The AI provider request failed.", code="ai_error")

    def complete_structured(
        self, *, system: str, user: str, schema: type[TModel], operation: str, temperature: float = 0.3
    ) -> CompletionResult[TModel]:
        system_full = (
            f"{system}\n\nRespond with a single JSON object only. It must validate against this JSON schema:\n"
            f"{_schema_hint(schema)}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_full},
            {"role": "user", "content": user},
        ]
        in_tok = out_tok = 0
        start = time.perf_counter()
        last_error: str | None = None
        for attempt in range(2):  # one corrective retry on invalid structured output
            try:
                resp = self._client.chat.completions.create(  # type: ignore[call-overload]
                    model=self.chat_model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
            except openai.OpenAIError as exc:
                log.warning("ai_request_failed", operation=operation, error_type=type(exc).__name__)
                raise self._translate(exc) from exc
            if resp.usage:
                in_tok += resp.usage.prompt_tokens or 0
                out_tok += resp.usage.completion_tokens or 0
            content = (resp.choices[0].message.content or "") if resp.choices else ""
            try:
                data = schema.model_validate_json(content)
                return CompletionResult(
                    data=data,
                    model=resp.model or self.chat_model,
                    provider=self.name,
                    usage=Usage(in_tok, out_tok, int((time.perf_counter() - start) * 1000)),
                )
            except ValidationError as exc:
                last_error = str(exc)[:500]
                log.warning("ai_invalid_structured_output", operation=operation, attempt=attempt)
                messages += [
                    {"role": "assistant", "content": content[:4000]},
                    {"role": "user", "content": f"That JSON was invalid: {last_error}. Return corrected JSON only."},
                ]
        raise AIOutputError("The AI provider returned output that failed validation.", details={"operation": operation})

    def embed(self, texts: list[str]) -> EmbeddingResult:
        start = time.perf_counter()
        try:
            resp = self._client.embeddings.create(model=self.embedding_model, input=texts)
        except openai.OpenAIError as exc:
            log.warning("ai_embedding_failed", error_type=type(exc).__name__)
            raise self._translate(exc) from exc
        vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        tokens = resp.usage.prompt_tokens if resp.usage else None
        return EmbeddingResult(
            vectors=vectors,
            model=self.embedding_model,
            provider=self.name,
            usage=Usage(tokens, 0, int((time.perf_counter() - start) * 1000)),
        )
