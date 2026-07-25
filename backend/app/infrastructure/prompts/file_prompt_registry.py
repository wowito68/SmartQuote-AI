import json
from pathlib import Path

from app.application.ports.ai_extraction_service import PromptDefinition
from app.application.ports.prompt_registry import PromptRegistry
from app.domain.catalog.exceptions import PromptNotFound


class FilePromptRegistry(PromptRegistry):
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).parents[2] / "prompts"

    def get(self, name: str, version: str) -> PromptDefinition:
        path = self._root / name / f"v{version.split('.')[0]}" / "prompt.json"
        if not path.is_file():
            raise PromptNotFound(f"Prompt {name} version {version} was not found.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["version"] != version:
            raise PromptNotFound(f"Prompt {name} version {version} was not found.")
        return PromptDefinition(
            name=payload["name"],
            version=payload["version"],
            schema_version=payload["schema_version"],
            description=payload["description"],
            instructions=payload["instructions"],
            user_template=payload["user_template"],
            output_schema=payload["output_schema"],
        )
