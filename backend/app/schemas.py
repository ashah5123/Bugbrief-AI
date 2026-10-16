from typing import Literal, Annotated
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ProjectIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(default='', max_length=2000)

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Name cannot be blank')
        return value.strip()

    @field_validator('url')
    @classmethod
    def url_check(cls, value):
        if value:
            try:
                parsed = urlsplit(value)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
                    raise ValueError('Invalid URL')
                parsed.port
            except ValueError:
                raise ValueError('Use a valid http:// or https:// URL without embedded credentials')
        return value

class FeedbackIn(StrictModel):
    project_id: str
    text: str = Field(default='', max_length=8000)
    page_url: str = Field(default='', max_length=2000)
    device: str = Field(default='', max_length=200)
    browser: str = Field(default='', max_length=200)
    _url = field_validator('page_url')(ProjectIn.url_check.__func__)

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        if value and len(value.strip()) < 3:
            raise ValueError('Describe the feedback in at least 3 characters')
        return value

class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    evidence_quote: str = Field(min_length=1, max_length=2000)
    source: str = Field(pattern=r'^(feedback|page_url|device|browser|captured_context|clarification:[a-f0-9-]{36}|screenshot:[a-f0-9-]{36}:[0-9]{1,2})$')

class BugReport(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=1, max_length=4000)
    expected_behaviour: Claim | None
    actual_behaviour: Claim | None
    reproduction_steps: list[Claim] = Field(max_length=15)
    observations: list[Claim] = Field(max_length=20)
    hypotheses: list[str] = Field(max_length=10)
    unknowns: list[str] = Field(max_length=15)
    questions: list[str] = Field(max_length=5)
    category: Literal['UI / UX', 'Functionality', 'Performance', 'Content', 'Other']
    priority: Literal['Low', 'Medium', 'High', 'Critical']

class SaveReport(StrictModel):
    version: int
    report: BugReport

class GenerateIn(StrictModel):
    consent: bool = False

class ApplyProposal(StrictModel):
    version: int


class VisualObservation(StrictModel):
    description: str = Field(min_length=3, max_length=800)
    region: str = Field(min_length=1, max_length=150)

class ImageAnalysis(StrictModel):
    observations: list[VisualObservation] = Field(max_length=8)
    limitations: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=8)

class ClarificationIn(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)

    @field_validator('question', 'answer')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Question and answer cannot be blank')
        return value.strip()
