"""Project-scoped customer intake. Public responses never serialize agency reports."""
from datetime import datetime, timezone
import secrets
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import get_db
from .config import settings
from .models import Project, IntakeLink, CustomerSubmission, Feedback, Clarification, AIJob, now
from .schemas import StrictModel, ClarificationIn, GenerateIn
from .intake_schemas import CustomerDraft, CustomerCreate
from .evidence import attachments, clarifications, report_evidence, upload, delete, content
from .jobs import ensure_idle, evidence_changed, run_job, usage, day
from .deletion import erase_feedback
from .customer_auth import current_customer
from .workflow import progress_snapshot

router = APIRouter()

def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return ''
    host = parsed.hostname.encode('idna').decode().lower()
    host = '[' + host + ']' if ':' in host else host
    port = parsed.port
    suffix = ':' + str(port) if port and port != (443 if parsed.scheme == 'https' else 80) else ''
    return f'{parsed.scheme}://{host}{suffix}'

def active_link(db, token):
    link = db.scalar(select(IntakeLink).where(IntakeLink.token == token, IntakeLink.revoked_at.is_(None)))
    if not link:
        raise HTTPException(404, 'This feedback link is unavailable. Ask the agency for a new link.')
    return link

def submission(db, token, request):
    item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.access_token == token))
    if item is None or item.stage == 'deleted':
        raise HTTPException(404, 'This submission link is unavailable.')
    authorize_submission(db, item, request)
    if item.account_id:
        return item
    link = db.get(IntakeLink, item.link_id)
    if link is None or link.revoked_at:
        raise HTTPException(404, 'This feedback link was closed by the agency.')
    return item

def authorize_submission(db, item, request):
    if item.account_id:
        account = current_customer(request, db)
        if account is None or account.id != item.account_id:
            raise HTTPException(404, 'Sign in to the customer account that owns this report.')

def editable(request, item):
    if item.stage == 'submitted':
        raise HTTPException(409, 'This submission is already with the agency. Start a new report for another issue.')
    if item.processing_started_at:
        elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(item.processing_started_at)
        if elapsed.total_seconds() < 300:
            raise HTTPException(409, 'Your submission is being checked. Please wait a moment.')
        item.processing_started_at = None
    ensure_idle(request.app, item.feedback_id)

def pending_questions(db, item):
    feedback = db.get(Feedback, item.feedback_id)
    report = feedback.proposal or feedback.report or {}
    answered = {entry.question for entry in clarifications(db, feedback.id)}
    return [q for q in report.get('questions', []) if q not in answered][:3]

def public_quota(db, item):
    if db.scalar(select(IntakeLink.id).where(IntakeLink.id == item.link_id, IntakeLink.revoked_at.is_(None))) is None:
        raise HTTPException(410, 'This feedback link has been closed.')
    query = select(func.count()).select_from(AIJob).join(CustomerSubmission, CustomerSubmission.feedback_id == AIJob.feedback_id).where(AIJob.day == day(), CustomerSubmission.link_id == item.link_id)
    if db.scalar(query) >= settings.public_ai_daily_limit:
        raise HTTPException(429, 'Automatic follow-up is paused for this project. Your feedback can still be sent.')
    attempts = db.scalar(select(func.count()).select_from(AIJob).where(AIJob.feedback_id == item.feedback_id, AIJob.day == day()))
    if attempts >= 5:
        raise HTTPException(429, 'This submission has reached its automatic follow-up limit. Send it to the agency for review.')

def snapshot(db, item):
    feedback = db.get(Feedback, item.feedback_id)
    link = db.get(IntakeLink, item.link_id)
    project = db.get(Project, link.project_id)
    return {'access_token': item.access_token, 'intake_token': link.token, 'reference': feedback.id[:8].upper(),
            'project_name': project.name, 'project_url': project.url, 'stage': item.stage, 'account_owned': bool(item.account_id),
            'reporter_name': item.reporter_name, 'text': feedback.text, 'page_url': feedback.page_url,
            'workflow': progress_snapshot(db, feedback, public=True) if item.stage == 'submitted' else None,
            'context': item.context, 'processing_error': item.processing_error,
            'processing': bool(item.processing_started_at and (datetime.now(timezone.utc) - datetime.fromisoformat(item.processing_started_at)).total_seconds() < 300), 'submitted_at': item.submitted_at,
            'has_report': feedback.report is not None, 'questions': pending_questions(db, item),
            'answers': [{'id': a.id, 'question': a.question, 'answer': a.answer} for a in clarifications(db, feedback.id)],
            'attachments': [{'id': a.id, 'filename': a.filename, 'width': a.width, 'height': a.height,
                             'analyzed': a.analysis is not None} for a in attachments(db, feedback.id)]}

@router.post('/api/projects/{project_id}/intake-link')
async def project_link(project_id: str, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    link = db.scalar(select(IntakeLink).where(IntakeLink.project_id == project_id, IntakeLink.revoked_at.is_(None)))
    if link is None:
        link = IntakeLink(project_id=project_id, token=secrets.token_urlsafe(32))
        db.add(link)
        db.commit()
    return {'token': link.token, 'created_at': link.created_at}

@router.delete('/api/projects/{project_id}/intake-link')
async def revoke_link(project_id: str, db: Session = Depends(get_db)):
    links = db.scalars(select(IntakeLink).where(IntakeLink.project_id == project_id, IntakeLink.revoked_at.is_(None))).all()
    for link in links:
        link.revoked_at = now()
    db.commit()
    return {'revoked': True}

@router.get('/api/public/intake/{token}')
def intake_config(token: str, db: Session = Depends(get_db)):
    link = active_link(db, token)
    project = db.get(Project, link.project_id)
    return {'project_name': project.name, 'project_url': project.url, 'allowed_origin': origin(project.url)}

def set_draft(item, feedback, data):
    item.reporter_name = data.reporter_name.strip()
    item.context = data.context.model_dump()
    feedback.text = data.text
    feedback.page_url = data.page_url
    # Only a customer confirmation establishes that captured context matches the issue browser.
    feedback.browser = ('Customer-confirmed issue browser: ' + data.context.user_agent)[:200] if data.context.same_browser_confirmed else ''
    feedback.device = ''  # User agent and viewport never establish a device model.
    evidence_changed(feedback)
    item.stage = 'draft'
    item.processing_error = None

@router.post('/api/public/intake/{token}/submissions', status_code=201)
async def create_submission(token: str, data: CustomerCreate, request: Request, db: Session = Depends(get_db)):
    link = active_link(db, token)
    existing = db.scalar(select(CustomerSubmission).where(CustomerSubmission.link_id == link.id, CustomerSubmission.client_nonce == data.client_nonce))
    if existing is not None:
        if existing.stage == 'deleted':
            raise HTTPException(410, 'This report was deleted. Start a new report.')
        authorize_submission(db, existing, request)
        return snapshot(db, existing)
    count = db.scalar(select(func.count()).select_from(CustomerSubmission).where(CustomerSubmission.link_id == link.id, CustomerSubmission.created_at >= day()))
    if count >= settings.public_submissions_daily_limit:
        raise HTTPException(429, 'This project has reached its submission limit for today. Please contact the agency directly.')
    feedback = Feedback(project_id=link.project_id, text=data.text)
    db.add(feedback)
    db.flush()
    account = current_customer(request, db)
    if account:
        from .customer_projects import connect_project
        connect_project(db, account.id, link)
    item = CustomerSubmission(link_id=link.id, feedback_id=feedback.id, access_token=secrets.token_urlsafe(32), client_nonce=data.client_nonce, account_id=account.id if account else None)
    set_draft(item, feedback, data)
    db.add(item)
    db.commit()
    return snapshot(db, item)

@router.get('/api/public/submissions/{token}')
def get_submission(token: str, request: Request, db: Session = Depends(get_db)):
    return snapshot(db, submission(db, token, request))

@router.delete('/api/public/submissions/{token}')
async def delete_submission(token: str, request: Request, db: Session = Depends(get_db)):
    # A private return link can erase its own report, including after link revocation.
    item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.access_token == token))
    if item is None or item.stage == 'deleted':
        raise HTTPException(404, 'This submission link is unavailable.')
    authorize_submission(db, item, request)
    return erase_feedback(db, request.app, db.get(Feedback, item.feedback_id))

@router.put('/api/public/submissions/{token}')
async def update_submission(token: str, data: CustomerDraft, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    editable(request, item)
    set_draft(item, db.get(Feedback, item.feedback_id), data)
    db.commit()
    return snapshot(db, item)

@router.post('/api/public/submissions/{token}/attachments', status_code=201)
async def upload_image(token: str, request: Request, filename: str = 'screenshot.png', reviewed: bool = False, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    editable(request, item)
    await upload(item.feedback_id, request, filename, reviewed, db)
    item.stage = 'draft'
    db.commit()
    return snapshot(db, item)

@router.get('/api/public/submissions/{token}/attachments/{attachment_id}/content')
def image_content(token: str, attachment_id: str, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    return content(item.feedback_id, attachment_id, request, db)

@router.delete('/api/public/submissions/{token}/attachments/{attachment_id}')
async def delete_image(token: str, attachment_id: str, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    editable(request, item)
    await delete(item.feedback_id, attachment_id, request, db)
    item.stage = 'draft'
    db.commit()
    return snapshot(db, item)

class CustomerAnswers(StrictModel):
    answers: list[ClarificationIn] = Field(min_length=1, max_length=3)

@router.post('/api/public/submissions/{token}/answers')
async def save_answers(token: str, data: CustomerAnswers, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    editable(request, item)
    feedback = db.get(Feedback, item.feedback_id)
    history = clarifications(db, feedback.id)
    known = set(pending_questions(db, item)) | {a.question for a in history} | {'Additional context'}
    if any(a.question not in known for a in data.answers):
        raise HTTPException(422, 'Answer a displayed question or add Additional context.')
    new = [a for a in data.answers if not any(a.question == old.question and a.answer == old.answer for old in history)]
    if len(history) + len(new) > 20:
        raise HTTPException(409, 'This submission already contains the maximum number of answers.')
    for answer in new:
        db.add(Clarification(feedback_id=feedback.id, **answer.model_dump()))
    if new:
        evidence_changed(feedback)
        item.stage = 'draft'
    db.commit()
    return snapshot(db, item)

@router.post('/api/public/submissions/{token}/process')
async def process_submission(token: str, data: GenerateIn, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    editable(request, item)
    if not data.consent:
        raise HTTPException(400, 'Confirm that the saved feedback and reviewed screenshots may be processed by the hosted provider.')
    feedback = db.get(Feedback, item.feedback_id)
    if not feedback.text.strip() and not attachments(db, feedback.id):
        raise HTTPException(400, 'Describe the issue or attach a reviewed screenshot first.')
    item.processing_started_at = now()
    item.consented_at = now()
    item.processing_error = None
    db.commit()
    try:
        for image in attachments(db, feedback.id):
            if image.analysis is not None:
                continue
            try:
                image_bytes = request.app.state.storage.get(image.storage_key)
            except FileNotFoundError:
                raise HTTPException(404, 'A saved screenshot is missing. The agency can review your written feedback.')
            def save_image(result, image=image):
                image.analysis = result.analysis.model_dump()
                image.analyzed_at = now()
                image.error = None
                evidence_changed(feedback)
            await run_job(request.app, db, feedback, 'vision', lambda image=image, image_bytes=image_bytes: request.app.state.image_analyzer.analyze(image_bytes, image.mime_type), save_image, image, lambda: public_quota(db, item))
        evidence = report_evidence(db, feedback)
        def save_report(result):
            if feedback.report is None:
                feedback.report = result.report.model_dump()
            else:
                feedback.proposal = result.report.model_dump()
            feedback.version += 1
            feedback.updated_at = now()
            feedback.status = 'review'
        await run_job(request.app, db, feedback, 'report', lambda: request.app.state.generator.generate(evidence), save_report, before_reserve=lambda: public_quota(db, item))
        item.stage = 'needs_details' if pending_questions(db, item) else 'ready'
    except HTTPException as error:
        item.processing_error = ('Automatic follow-up is paused for now. Your work is saved; you can still send it to the agency.' if error.status_code in (409, 429, 503) else 'We could not complete the automatic check. Your feedback is saved and can still be sent to the agency.')
        item.stage = 'draft'
    finally:
        item.processing_started_at = None
        db.commit()
    return snapshot(db, item)

@router.post('/api/public/submissions/{token}/submit')
async def finish_submission(token: str, request: Request, db: Session = Depends(get_db)):
    item = submission(db, token, request)
    if item.stage == 'submitted':
        return snapshot(db, item)
    editable(request, item)
    feedback = db.get(Feedback, item.feedback_id)
    if not feedback.text.strip() and not attachments(db, feedback.id):
        raise HTTPException(400, 'Describe the issue or attach a screenshot before sending.')
    item.stage = 'submitted'
    item.submitted_at = now()
    feedback.updated_at = now()
    db.commit()
    return snapshot(db, item)
