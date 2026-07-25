from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    name: str
    version: str
    schema_version: str
    description: str
    instructions: str
    user_template: str
    output_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AIExtractionRequest:
    prompt: PromptDefinition
    model: str
    temperature: float
    document_id: str
    pages: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class AIExtractionResult:
    payload: dict[str, Any]
    model: str
    provider_response_id: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    duration_ms: int


class AIExtractionService(ABC):
    @abstractmethod
    def extract(self, request: AIExtractionRequest) -> AIExtractionResult:
        raise NotImplementedError
