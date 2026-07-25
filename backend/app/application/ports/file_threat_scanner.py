from abc import ABC, abstractmethod


class FileThreatScanner(ABC):
    """Extension point for antivirus or malware scanning in a future iteration."""

    @abstractmethod
    def scan(self, original_file_name: str, content: bytes) -> None:
        """Raise an application/domain exception when content is unsafe."""
        raise NotImplementedError
