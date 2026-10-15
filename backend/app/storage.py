from typing import Protocol
from pathlib import Path

class AttachmentStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def delete(self, key: str) -> None: ...

class LocalStorage:
    """Storage seam for Phase 2. No uploads accepted in Phase 1."""
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError('Invalid attachment key')
        return path

    def put(self, key, content):
        self.root.mkdir(parents=True, exist_ok=True)
        self.path(key).write_bytes(content)

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)
