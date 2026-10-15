import asyncio
import re
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import Project, Feedback, now
from .schemas import ProjectIn, FeedbackIn, SaveReport, GenerateIn, ApplyProposal
from .providers.gemini import GeminiGenerator, GeminiImageAnalyzer
from .storage import LocalStorage
from .jobs import usage, ensure_idle, evidence_changed, run_job
from .evidence import router, serialize, get_feedback, report_evidence, MAX_BYTES

app = FastAPI(title='BugBrief AI', version='0.2.0')
app.state.generator = GeminiGenerator(settings)
app.state.image_analyzer = GeminiImageAnalyzer(settings)
app.state.storage = LocalStorage(settings.attachments_dir)
app.state.job_lock = asyncio.Lock()
app.include_router(router)

@app.middleware('http')
async def local_write_guard(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8001', 'http://localhost:8001', 'http://127.0.0.1:15173'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        upload = request.method == 'POST' and re.fullmatch(r'/api/feedback/[a-f0-9-]{36}/attachments', request.url.path)
        limit = MAX_BYTES if upload else 32768
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse({'detail': 'Screenshot exceeds 2 MiB.' if upload else 'Request is too large. Maximum JSON size is 32 KiB.'}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
    return await call_next(request)

@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Project))
    return {'status': 'ok', 'version': app.version, 'ai_configured': bool(settings.gemini_api_key),
            'free_tier_confirmed': settings.free_tier_confirmed, 'model': settings.gemini_model,
            'busy': app.state.job_lock.locked(), 'usage': usage(db)}

@app.get('/api/projects')
def projects(db: Session = Depends(get_db)):
    return [serialize(p) for p in db.scalars(select(Project).order_by(Project.created_at)).all()]

@app.post('/api/projects', status_code=201)
async def create_project(data: ProjectIn, db: Session = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    return serialize(project)

@app.get('/api/feedback')
def feedback_list(db: Session = Depends(get_db)):
    return [serialize(f, db) for f in db.scalars(select(Feedback).order_by(Feedback.updated_at.desc())).all()]

@app.post('/api/feedback', status_code=201)
async def create_feedback(data: FeedbackIn, db: Session = Depends(get_db)):
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    feedback = Feedback(**data.model_dump())
    db.add(feedback)
    db.commit()
    return serialize(feedback, db)

@app.put('/api/feedback/{feedback_id}')
async def edit_feedback(feedback_id: str, data: FeedbackIn, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    ensure_idle(app)
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    evidence_changed(item)
    db.commit()
    return serialize(item, db)

@app.put('/api/feedback/{feedback_id}/report')
async def save_report(feedback_id: str, data: SaveReport, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    ensure_idle(app)
    if item.version != data.version:
        raise HTTPException(409, 'This report changed in another tab. Reopen it before saving.')
    if any(claim.source.startswith('screenshot:') for claim in data.report.reproduction_steps) or (data.report.expected_behaviour and data.report.expected_behaviour.source.startswith('screenshot:')):
        raise HTTPException(422, 'Screenshots cannot establish reproduction steps or expected behaviour. Add the user-supplied detail as a clarification first.')
    item.report = data.report.model_dump()
    item.version += 1
    item.updated_at = now()
    item.status = 'review'
    db.commit()
    return serialize(item, db)

@app.post('/api/feedback/{feedback_id}/apply-proposal')
async def apply_proposal(feedback_id: str, data: ApplyProposal, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    ensure_idle(app)
    if item.version != data.version:
        raise HTTPException(409, 'This report changed. Reopen it before applying.')
    if item.proposal is None:
        raise HTTPException(400, 'No new proposal to apply')
    item.report, item.proposal = item.proposal, None
    item.version += 1
    item.updated_at = now()
    item.status = 'review'
    db.commit()
    return serialize(item, db)

@app.post('/api/feedback/{feedback_id}/generate')
async def generate(feedback_id: str, data: GenerateIn, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    if not data.consent:
        raise HTTPException(400, 'Confirm this feedback can be sent to the hosted free-tier provider.')
    evidence = report_evidence(db, item)
    def save(result):
        if item.report is None:
            item.report = result.report.model_dump()
        else:
            item.proposal = result.report.model_dump()
        item.status = 'review'
        item.version += 1
        item.updated_at = now()
    await run_job(app, db, item, 'report', lambda: app.state.generator.generate(evidence), save)
    return serialize(item, db)
