from typing import Protocol
from pathlib import Path

class AttachmentStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...

class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path.parent != self.root or path.name != key:
            raise ValueError('Invalid attachment key')
        return path

    def put(self, key, content):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path(key).open('xb') as file:
            file.write(content)

    def get(self, key):
        return self.path(key).read_bytes()

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)
