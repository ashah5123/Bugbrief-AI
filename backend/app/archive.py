"""Company and customer archives are independent views, never deletion or resolution."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from .db import get_db
from .schemas import StrictModel
from .models import now
from .jobs import ensure_idle
from .workflow import visible_feedback
from .conversation import sent_submission
from .intake import snapshot
from .evidence import serialize

router = APIRouter()


class ArchiveInput(StrictModel):
    archived: bool


@router.patch('/api/feedback/{feedback_id}/archive')
async def company_archive(feedback_id: str, data: ArchiveInput, request: Request, db: Session = Depends(get_db)):
    feedback = visible_feedback(db, feedback_id)
    ensure_idle(request.app, feedback_id)
    if bool(feedback.archived_at) != data.archived:
        feedback.archived_at = now() if data.archived else None
        db.commit()
    return serialize(feedback, db)


@router.patch('/api/public/submissions/{token}/archive')
async def customer_archive(token: str, data: ArchiveInput, request: Request, db: Session = Depends(get_db)):
    item = sent_submission(db, token, request)
    if bool(item.archived_at) != data.archived:
        item.archived_at = now() if data.archived else None
        db.commit()
    return snapshot(db, item)
