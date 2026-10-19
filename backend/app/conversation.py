"""Public report replies and strictly company-only notes; customer retest decisions."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import Field, field_validator
from sqlalchemy import select, update, or_, and_
from sqlalchemy.orm import Session
from .db import get_db
from .models import ReportMessage, Feedback, IssueProgress, IssueEvent, now
from .schemas import StrictModel
from .workflow import visible_feedback, progress_snapshot
from .intake import submission
from .customer_auth import current_customer, throttle
from .employee_auth import current_employee
from .notifications import emit, deliver_pending
from .reply_media import ReplyImage, MAX_IMAGES, message_images, prior_message, save_reply, image_content

router = APIRouter()


class MessageInput(StrictModel):
    request_id: UUID | None = None
    attachments: list[ReplyImage] = Field(default_factory=list, max_length=MAX_IMAGES)
    body: str = Field(min_length=1, max_length=4000)
    visibility: Literal['public', 'internal'] = 'public'

    @field_validator('body')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Write a message first.')
        return value.strip()


def messages(db, feedback_id, public=False, before=None, paged=False):
    query = select(ReportMessage).where(ReportMessage.feedback_id == feedback_id)
    if public:
        query = query.where(ReportMessage.visibility == 'public')
    if before:
        cursor = db.get(ReportMessage, before)
        if not cursor or cursor.feedback_id != feedback_id or (public and cursor.visibility != 'public'):
            raise HTTPException(404, 'Conversation position is unavailable. Reload the conversation.')
        query = query.where(or_(ReportMessage.created_at < cursor.created_at,
            and_(ReportMessage.created_at == cursor.created_at, ReportMessage.id < cursor.id)))
    rows = db.scalars(query.order_by(ReportMessage.created_at.desc(), ReportMessage.id.desc()).limit(101 if paged else 100)).all()
    more = len(rows) > 100
    rows = rows[:100]
    items = [{'id': m.id, 'visibility': m.visibility, 'author_role': m.author_role,
             'author_name': m.author_name, 'body': m.body, 'created_at': m.created_at,
             'attachments': message_images(db, m.id)} for m in reversed(rows)]
    return {'items': items, 'next_before': rows[-1].id if more else None} if paged else items


def sent_submission(db, token, request):
    item = submission(db, token, request)
    if item.stage != 'submitted':
        raise HTTPException(409, 'Send the report before replying or testing a fix.')
    return item


@router.get('/api/feedback/{feedback_id}/messages')
def company_messages(feedback_id: str, before: str | None = None, paged: bool = False, db: Session = Depends(get_db)):
    visible_feedback(db, feedback_id)
    return messages(db, feedback_id, before=before, paged=paged)


@router.post('/api/feedback/{feedback_id}/messages', status_code=201)
async def company_reply(feedback_id: str, data: MessageInput, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    throttle(request, 'company-message', 60)
    feedback = visible_feedback(db, feedback_id)
    employee = current_employee(request, db)
    actor = 'employee:' + employee.id if employee else 'owner'
    if prior_message(db, data, feedback_id, actor):
        return messages(db, feedback_id)
    save_reply(db, request, data, feedback_id, actor, 'company', employee.name if employee else 'Workspace owner',
        lambda: emit(db, request, feedback, 'company_reply' if data.visibility == 'public' else 'internal_note',
            'Company replied' if data.visibility == 'public' else 'Private team note added',
            company=True, customer=data.visibility == 'public'))
    background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    return messages(db, feedback_id)


@router.get('/api/public/submissions/{token}/messages')
def customer_messages(token: str, request: Request, before: str | None = None, paged: bool = False, db: Session = Depends(get_db)):
    item = sent_submission(db, token, request)
    return messages(db, item.feedback_id, public=True, before=before, paged=paged)


@router.post('/api/public/submissions/{token}/messages', status_code=201)
async def customer_reply(token: str, data: MessageInput, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    throttle(request, 'customer-message', 60)
    item = sent_submission(db, token, request)
    if data.visibility != 'public':
        raise HTTPException(403, 'Customers can only send public replies.')
    account = current_customer(request, db)
    actor = 'customer:' + account.id if account else 'guest:' + item.feedback_id
    if prior_message(db, data, item.feedback_id, actor):
        return messages(db, item.feedback_id, public=True)
    save_reply(db, request, data, item.feedback_id, actor, 'customer', account.name if account else item.reporter_name or 'Customer',
        lambda: emit(db, request, db.get(Feedback, item.feedback_id), 'customer_reply', 'Customer replied', company=True))
    background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    return messages(db, item.feedback_id, public=True)


class RetestInput(StrictModel):
    version: int = Field(ge=1)
    outcome: Literal['works', 'still_happening']
    note: str = Field(default='', max_length=1000)


@router.post('/api/public/submissions/{token}/retest')
def retest(token: str, data: RetestInput, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    throttle(request, 'customer-retest', 20)
    item = sent_submission(db, token, request)
    progress = db.get(IssueProgress, item.feedback_id)
    if not progress or progress.status != 'ready_to_retest' or progress.version != data.version:
        raise HTTPException(409, 'This fix has already been updated. Reload the report before confirming it.')
    note = data.note.strip()
    if data.outcome == 'still_happening' and not note:
        raise HTTPException(422, 'Tell the team what is still happening.')
    status = 'resolved' if data.outcome == 'works' else 'in_progress'
    changed = db.execute(update(IssueProgress).where(IssueProgress.feedback_id == item.feedback_id,
        IssueProgress.status == 'ready_to_retest', IssueProgress.version == data.version).values(
            status=status, version=data.version+1, updated_at=now()))
    if changed.rowcount != 1:
        raise HTTPException(409, 'The report changed. Reload it before confirming the fix.')
    db.add(IssueEvent(feedback_id=item.feedback_id,
        label='Customer confirmed the fix' if data.outcome == 'works' else 'Customer says the issue is still happening', note=note))
    emit(db, request, db.get(Feedback, item.feedback_id), 'retest_result',
         'Customer confirmed the fix' if data.outcome == 'works' else 'Customer says the issue is still happening', company=True)
    db.commit()
    background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    db.expire_all()
    return progress_snapshot(db, db.get(Feedback, item.feedback_id), public=True)


@router.get('/api/feedback/{feedback_id}/messages/{message_id}/attachments/{image_id}/content')
def company_image(feedback_id: str, message_id: str, image_id: str, request: Request, db: Session = Depends(get_db)):
    visible_feedback(db, feedback_id)
    return image_content(db, request, feedback_id, message_id, image_id)


@router.get('/api/public/submissions/{token}/messages/{message_id}/attachments/{image_id}/content')
def customer_image(token: str, message_id: str, image_id: str, request: Request, db: Session = Depends(get_db)):
    item = sent_submission(db, token, request)
    return image_content(db, request, item.feedback_id, message_id, image_id, public=True)
