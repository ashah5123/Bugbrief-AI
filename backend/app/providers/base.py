from typing import Protocol
from dataclasses import dataclass
from ..schemas import BugReport, ImageAnalysis

@dataclass
class Generation:
    report: BugReport
    input_tokens: int = 0
    output_tokens: int = 0

class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

class ReportGenerator(Protocol):
    async def generate(self, evidence: dict[str, str]) -> Generation: ...

@dataclass
class VisionGeneration:
    analysis: ImageAnalysis
    input_tokens: int = 0
    output_tokens: int = 0

# Independent hosted vision integration.
class ImageAnalyzer(Protocol):
    async def analyze(self, content: bytes, mime_type: str) -> VisionGeneration: ...

class Transcriber(Protocol):
    async def transcribe(self, content: bytes, mime_type: str) -> str: ...

class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
