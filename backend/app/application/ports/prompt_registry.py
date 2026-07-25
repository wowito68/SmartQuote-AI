from abc import ABC, abstractmethod

from app.application.ports.ai_extraction_service import PromptDefinition


class PromptRegistry(ABC):
    @abstractmethod
    def get(self, name: str, version: str) -> PromptDefinition:
        raise NotImplementedError
