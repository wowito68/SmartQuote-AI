import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "correlation_id",
            "tender_id",
            "document_id",
            "quote_id",
            "rfq_id",
            "supplier_id",
            "message_id",
            "extraction_run_id",
            "ai_extraction_run_id",
            "extractor_name",
            "model",
            "prompt_version",
            "duration_ms",
            "page_number",
            "document_status",
            "pages_processed",
            "characters_extracted",
            "empty_pages",
            "empty_page_percentage",
            "text_density",
            "quality_decision",
            "pending_count",
            "attempt",
            "provider",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
