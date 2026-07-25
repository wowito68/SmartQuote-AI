import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.application.ports.ai_extraction_service import AIExtractionRequest
from app.domain.catalog.exceptions import AIResponseValidationError
from app.infrastructure.ai.openai_extraction_service import OpenAIExtractionService
from app.infrastructure.prompts.file_prompt_registry import FilePromptRegistry


class FakeResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test",
            model="gpt-test",
            output_text=self.output_text,
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
        )


class FakeClient:
    def __init__(self, output_text: str) -> None:
        self.responses = FakeResponses(output_text)


def request() -> AIExtractionRequest:
    return AIExtractionRequest(
        prompt=FilePromptRegistry().get("catalog_extraction", "1.0.0"),
        model="gpt-test",
        temperature=0,
        document_id="11111111-1111-1111-1111-111111111111",
        pages=({"page_number": 1, "text": "Partida 1 Cable 100 m"},),
    )


def test_openai_service_uses_strict_schema_store_false_and_records_cost() -> None:
    payload = {"products": []}
    client = FakeClient(json.dumps(payload))
    result = OpenAIExtractionService(
        client,
        input_cost_per_million_tokens=Decimal("1.25"),
        output_cost_per_million_tokens=Decimal("5.00"),
    ).extract(request())
    assert result.payload == payload
    assert result.input_tokens == 1200
    assert result.output_tokens == 300
    assert result.estimated_cost_usd == Decimal("0.003000")
    kwargs = client.responses.kwargs
    assert kwargs["store"] is False
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert "--- PAGE 1 ---" in kwargs["input"]


def test_openai_service_rejects_missing_or_invalid_json_output() -> None:
    with pytest.raises(AIResponseValidationError):
        OpenAIExtractionService(
            FakeClient(""),
            input_cost_per_million_tokens=Decimal("0"),
            output_cost_per_million_tokens=Decimal("0"),
        ).extract(request())
    with pytest.raises(AIResponseValidationError):
        OpenAIExtractionService(
            FakeClient("not-json"),
            input_cost_per_million_tokens=Decimal("0"),
            output_cost_per_million_tokens=Decimal("0"),
        ).extract(request())


def test_http_client_builds_authorized_request_and_parses_responses_payload(monkeypatch) -> None:
    from app.infrastructure.ai.openai_extraction_service import OpenAIResponsesHTTPClient

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "resp_http",
                    "model": "gpt-http",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": '{"products": []}'}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAIResponsesHTTPClient(
        api_key="secret-test-key",
        base_url="https://api.openai.com/v1/",
        timeout_seconds=12,
    )
    response = client.responses.create(model="gpt-http", input="test")
    assert response.id == "resp_http"
    assert response.output_text == '{"products": []}'
    assert response.usage.input_tokens == 10
    assert captured["timeout"] == 12
    assert captured["request"].get_header("Authorization") == "Bearer secret-test-key"
    assert captured["request"].full_url == "https://api.openai.com/v1/responses"


def test_http_client_maps_transport_error(monkeypatch) -> None:
    import urllib.error

    from app.domain.catalog.exceptions import AIExtractionFailure
    from app.infrastructure.ai.openai_extraction_service import OpenAIResponsesHTTPClient

    def failed(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", failed)
    client = OpenAIResponsesHTTPClient(
        api_key="secret",
        base_url="https://api.openai.com/v1",
        timeout_seconds=1,
    )
    with pytest.raises(AIExtractionFailure):
        client.create(model="gpt-test", input="x")
