import hashlib
import json
from dataclasses import dataclass

from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    TextExtractionResult,
)
from app.domain.documents.exceptions import DocumentExtractionFailure


@dataclass(frozen=True, slots=True)
class ExtractionPolicy:
    minimum_characters: int = 100
    maximum_empty_page_percentage: float = 60.0
    minimum_characters_per_page: float = 20.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "minimum_characters": self.minimum_characters,
            "maximum_empty_page_percentage": self.maximum_empty_page_percentage,
            "minimum_characters_per_page": self.minimum_characters_per_page,
        }


class FallbackDocumentTextExtractor:
    def __init__(
        self,
        primary: DocumentTextExtractor,
        fallback: DocumentTextExtractor,
        policy: ExtractionPolicy,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.policy = policy

    @property
    def strategy_version(self) -> str:
        return (
            f"{self.primary.name}:{self.primary.version}|"
            f"{self.fallback.name}:{self.fallback.version}"
        )

    def configuration(self) -> dict[str, object]:
        return {
            "primary": {"name": self.primary.name, "version": self.primary.version},
            "fallback": {"name": self.fallback.name, "version": self.fallback.version},
            "policy": self.policy.as_dict(),
        }

    def processing_key(self, file_hash: str) -> str:
        payload = {
            "file_hash": file_hash,
            "strategy_version": self.strategy_version,
            "configuration": self.configuration(),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def extract(self, content: bytes) -> TextExtractionResult:
        primary_result: TextExtractionResult | None = None
        primary_error: Exception | None = None
        try:
            primary_result = self.primary.extract(content)
            if self._is_sufficient(primary_result):
                return primary_result
        except Exception as exc:  # extractor adapters normalize third-party failures here
            primary_error = exc

        try:
            fallback_result = self.fallback.extract(content)
        except Exception as fallback_error:
            if primary_result is not None:
                return primary_result
            raise DocumentExtractionFailure(
                "Both PDF text extractors failed. "
                f"Primary: {primary_error!s}; fallback: {fallback_error!s}"
            ) from fallback_error

        if primary_result is None:
            return fallback_result
        return max((primary_result, fallback_result), key=self._score)

    def _is_sufficient(self, result: TextExtractionResult) -> bool:
        if not result.pages:
            return False
        characters_per_page = result.characters_extracted / len(result.pages)
        return (
            result.characters_extracted >= self.policy.minimum_characters
            and result.empty_page_percentage <= self.policy.maximum_empty_page_percentage
            and characters_per_page >= self.policy.minimum_characters_per_page
        )

    @staticmethod
    def _score(result: TextExtractionResult) -> tuple[int, float, int]:
        return (
            result.characters_extracted,
            -result.empty_page_percentage,
            len(result.pages),
        )
