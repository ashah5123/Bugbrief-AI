"""Customer-safe instructions attached to an exact request to retest."""
from fastapi import HTTPException
from pydantic import Field, field_validator
from .schemas import StrictModel


class FixDetails(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    location: str = Field(min_length=1, max_length=1000)
    steps: str = Field(min_length=1, max_length=2000)

    @field_validator('summary', 'location', 'steps')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Complete all three customer-visible fix details before requesting a retest.')
        return value.strip()


def retest_values(status, previous, details, stamp, request_again=False):
    if status == 'ready_to_retest' and (previous != status or details is not None or request_again):
        if details is None:
            raise HTTPException(422, 'Explain what changed, where the fix is available and the steps to retest before requesting a retest.')
        return {'fix_details': details.model_dump(), 'retest_requested_at': stamp}
    if status not in ('ready_to_retest', 'resolved'):
        return {'fix_details': None, 'retest_requested_at': None}
    return {}
