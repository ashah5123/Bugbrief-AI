from typing import Literal
from pydantic import Field, field_validator
from .schemas import StrictModel, ProjectIn

class BrowserContext(StrictModel):
    user_agent: str = Field(default='', max_length=500)
    language: str = Field(default='', max_length=80)
    timezone: str = Field(default='', max_length=100)
    viewport_width: int = Field(default=0, ge=0, le=20000)
    viewport_height: int = Field(default=0, ge=0, le=20000)
    screen_width: int = Field(default=0, ge=0, le=20000)
    screen_height: int = Field(default=0, ge=0, le=20000)
    source: Literal['standalone', 'embedded', 'demo'] = 'standalone'
    same_browser_confirmed: bool = False

class GuidedDetails(StrictModel):
    goal: str = Field(default='', max_length=1000)
    expected: str = Field(default='', max_length=2000)
    steps: str = Field(default='', max_length=2000)
    frequency: Literal['', 'every_time', 'sometimes', 'once', 'not_sure'] = ''

    @field_validator('goal', 'expected', 'steps')
    @classmethod
    def trim_answer(cls, value):
        return value.strip()


class CustomerDraft(StrictModel):
    draft_version: int | None = Field(default=None, ge=1)
    text: str = Field(default='', max_length=8000)
    page_url: str = Field(default='', max_length=2000)
    reporter_name: str = Field(default='', max_length=80)
    context: BrowserContext = Field(default_factory=BrowserContext)
    guided_details: GuidedDetails | None = None
    _url = field_validator('page_url')(ProjectIn.url_check.__func__)

class CustomerCreate(CustomerDraft):
    client_nonce: str = Field(pattern=r'^[A-Za-z0-9_-]{20,80}$')
