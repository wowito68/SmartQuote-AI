import json
import time
import urllib.error
import urllib.request
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Protocol

from app.application.ports.ai_extraction_service import (
    AIExtractionRequest,
    AIExtractionResult,
    AIExtractionService,
)
from app.domain.catalog.exceptions import AIExtractionFailure, AIResponseValidationError


class ResponsesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class OpenAIClient(Protocol):
    responses: ResponsesAPI


class OpenAIResponsesHTTPClient:
    """Minimal Responses API client used behind the AIExtractionService adapter."""

    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/responses"
        self._timeout = timeout_seconds
        self.responses = self

    def create(self, **kwargs: Any) -> Any:
        body = json.dumps(kwargs, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:4000]
            raise AIExtractionFailure(
                f"OpenAI Responses API returned HTTP {exc.code}: {details}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AIExtractionFailure(f"OpenAI Responses API is unavailable: {exc}") from exc
        output_text = ""
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text += content.get("text", "")
        usage = payload.get("usage") or {}
        return SimpleNamespace(
            id=payload.get("id"),
            model=payload.get("model"),
            output_text=output_text,
            usage=SimpleNamespace(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
        )


class OpenAIExtractionService(AIExtractionService):
    def __init__(
        self,
        client: OpenAIClient,
        *,
        input_cost_per_million_tokens: Decimal,
        output_cost_per_million_tokens: Decimal,
    ) -> None:
        self._client = client
        self._input_cost = input_cost_per_million_tokens
        self._output_cost = output_cost_per_million_tokens

    @staticmethod
    def _render_pages(pages: tuple[dict[str, Any], ...]) -> str:
        return "\n\n".join(
            f"--- PAGE {page['page_number']} ---\n{page['text']}"
            for page in pages
        )

    def extract(self, request: AIExtractionRequest) -> AIExtractionResult:
        user_text = request.prompt.user_template.format(
            document_id=request.document_id,
            pages=self._render_pages(request.pages),
        )
        started = time.perf_counter()
        try:
            response = self._client.responses.create(
                model=request.model,
                instructions=request.prompt.instructions,
                input=user_text,
                temperature=request.temperature,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "tender_catalog_extraction",
                        "description": request.prompt.description,
                        "schema": request.prompt.output_schema,
                        "strict": True,
                    }
                },
                store=False,
            )
        except Exception as exc:
            raise AIExtractionFailure(f"OpenAI extraction request failed: {exc}") from exc
        duration_ms = int((time.perf_counter() - started) * 1000)
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise AIResponseValidationError("OpenAI response did not contain structured output.")
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise AIResponseValidationError("OpenAI response was not valid JSON.") from exc
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost = (
            Decimal(input_tokens) * self._input_cost
            + Decimal(output_tokens) * self._output_cost
        ) / Decimal(1_000_000)
        return AIExtractionResult(
            payload=payload,
            model=str(getattr(response, "model", request.model) or request.model),
            provider_response_id=getattr(response, "id", None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost.quantize(Decimal("0.000001")),
            duration_ms=max(duration_ms, 0),
        )
