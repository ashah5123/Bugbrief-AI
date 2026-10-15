import asyncio
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import Project, Feedback, AIJob, now
from .schemas import ProjectIn, FeedbackIn, SaveReport, GenerateIn, ApplyProposal
from .providers.gemini import GeminiGenerator
from .providers.base import ProviderError

app = FastAPI(title='BugBrief AI', version='0.1.0')
app.state.generator = GeminiGenerator(settings)
app.state.job_lock = asyncio.Lock()

@app.middleware('http')
async def local_write_guard(request: Request, call_next):
    # JSON writes only. Prevent cross-origin websites from changing this local app.
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        from fastapi.responses import JSONResponse
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 32768:
                return JSONResponse({'detail': 'Request is too large. Maximum JSON size is 32 KiB.'}, status_code=413)
        request._body = bytes(body)
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000', 'http://127.0.0.1:8001', 'http://localhost:8001', 'http://127.0.0.1:15173'):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    return await call_next(request)

def day():
    return datetime.now(timezone.utc).date().isoformat()

def get_feedback(db, feedback_id):
    item = db.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, 'Feedback not found')
    return item

def serialize(item):
    return {c.name: getattr(item, c.name) for c in item.__table__.columns}

def usage(db):
    jobs = db.scalars(select(AIJob).where(AIJob.day == day())).all()
    return {'attempts': len(jobs), 'limit': settings.ai_daily_limit,
            'paused': any(j.outcome == 'quota' for j in jobs),
            'input_tokens': sum(j.input_tokens for j in jobs), 'output_tokens': sum(j.output_tokens for j in jobs),
            'successful': sum(j.outcome == 'success' for j in jobs),
            'average_latency_ms': round(sum(j.latency_ms for j in jobs) / len(jobs)) if jobs else 0,
            'resets': '00:00 UTC'}

@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Project))
    return {'status': 'ok', 'ai_configured': bool(settings.gemini_api_key),
            'free_tier_confirmed': settings.free_tier_confirmed, 'model': settings.gemini_model,
            'busy': app.state.job_lock.locked(), 'usage': usage(db)}

@app.get('/api/projects')
def projects(db: Session = Depends(get_db)):
    return [serialize(p) for p in db.scalars(select(Project).order_by(Project.created_at)).all()]

@app.post('/api/projects', status_code=201)
def create_project(data: ProjectIn, db: Session = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    return serialize(project)

@app.get('/api/feedback')
def feedback_list(db: Session = Depends(get_db)):
    return [serialize(f) for f in db.scalars(select(Feedback).order_by(Feedback.updated_at.desc())).all()]

@app.post('/api/feedback', status_code=201)
def create_feedback(data: FeedbackIn, db: Session = Depends(get_db)):
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    feedback = Feedback(**data.model_dump())
    db.add(feedback)
    db.commit()
    return serialize(feedback)

@app.put('/api/feedback/{feedback_id}')
def edit_feedback(feedback_id: str, data: FeedbackIn, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    if app.state.job_lock.locked():
        raise HTTPException(409, 'Wait for the current AI request to finish before changing evidence.')
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    item.updated_at = now()
    item.version += 1
    # Previously generated report stays intact; evidence edits require a new review.
    item.status = 'draft'
    item.proposal = None
    item.error = None
    db.commit()
    return serialize(item)

@app.put('/api/feedback/{feedback_id}/report')
def save_report(feedback_id: str, data: SaveReport, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    if app.state.job_lock.locked():
        raise HTTPException(409, 'Wait for AI processing to finish before saving or applying a report.')
    if item.version != data.version:
        raise HTTPException(409, 'This report changed in another tab. Reopen it before saving.')
    item.report = data.report.model_dump()
    item.version += 1
    item.updated_at = now()
    item.status = 'review'
    db.commit()
    return serialize(item)

@app.post('/api/feedback/{feedback_id}/apply-proposal')
def apply_proposal(feedback_id: str, data: ApplyProposal, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    if app.state.job_lock.locked():
        raise HTTPException(409, 'Wait for AI processing to finish before saving or applying a report.')
    if item.version != data.version:
        raise HTTPException(409, 'This report changed. Reopen it before applying.')
    if item.proposal is None:
        raise HTTPException(400, 'No new AI proposal to apply')
    item.report, item.proposal = item.proposal, None
    item.version += 1
    item.updated_at = now()
    db.commit()
    return serialize(item)

@app.post('/api/feedback/{feedback_id}/generate')
async def generate(feedback_id: str, data: GenerateIn, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    if not data.consent:
        raise HTTPException(400, 'Confirm this feedback can be sent to the hosted free-tier provider.')
    if not settings.gemini_api_key:
        raise HTTPException(503, 'Add GEMINI_API_KEY to backend/.env and restart. Your feedback is saved.')
    if not settings.free_tier_confirmed:
        raise HTTPException(503, 'Confirm billing is disabled and set FREE_TIER_CONFIRMED=true. Your feedback is saved.')
    if app.state.job_lock.locked():
        raise HTTPException(409, 'Another AI job is running. Try again after it finishes.')
    async with app.state.job_lock:
        current = usage(db)
        if current['paused'] or current['attempts'] >= settings.ai_daily_limit:
            raise HTTPException(429, 'AI is paused until 00:00 UTC. Your feedback and edits are safe.')
        job = AIJob(feedback_id=item.id, day=day(), model=settings.gemini_model)
        db.add(job)
        db.commit()  # Reserve attempt before external call; counts persist even on crash.
        start = time.monotonic()
        try:
            result = await app.state.generator.generate({'feedback': item.text, 'page_url': item.page_url, 'device': item.device, 'browser': item.browser})
            if item.report is None:
                item.report = result.report.model_dump()
            else:
                item.proposal = result.report.model_dump()
            item.error = None
            item.status = 'review'
            item.version += 1
            item.updated_at = now()
            job.outcome = 'success'
            job.input_tokens, job.output_tokens = result.input_tokens, result.output_tokens
        except ProviderError as exc:
            job.outcome = exc.code
            item.error = exc.message
            job.latency_ms = (time.monotonic() - start) * 1000
            db.commit()
            raise HTTPException(exc.status, exc.message)
        finally:
            job.latency_ms = (time.monotonic() - start) * 1000
        db.commit()
    return serialize(item)
