import asyncio
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db, SessionLocal
from .models import Project, Feedback, CustomerSubmission, now
from .schemas import ProjectIn, FeedbackIn, SaveReport, GenerateIn, ApplyProposal
from .providers.gemini import GeminiGenerator, GeminiImageAnalyzer
from .storage import LocalStorage
from .jobs import usage, ensure_idle, evidence_changed, run_job
from .evidence import router, serialize, get_feedback, report_evidence, MAX_BYTES

from .auth import router as auth_router, agency_allowed, access_code
from .intake import router as intake_router
from .deletion import erase_feedback
from .customer_auth import router as customer_auth_router
from .customer_routes import router as customer_router
from .employee_auth import router as employee_router
from .workflow import router as workflow_router

@asynccontextmanager
async def lifespan(app):
    access_code()
    yield

app = FastAPI(title='BugBrief AI', version='0.3.0', lifespan=lifespan)
app.state.generator = GeminiGenerator(settings)
app.state.image_analyzer = GeminiImageAnalyzer(settings)
app.state.storage = LocalStorage(settings.attachments_dir)
app.state.job_lock = asyncio.Lock()
app.state.active_feedback_id = None
app.state.session_factory = SessionLocal
app.include_router(router)
app.include_router(auth_router)
app.include_router(intake_router)
app.include_router(customer_auth_router)
app.include_router(customer_router)
app.include_router(employee_router)
app.include_router(workflow_router)

@app.middleware('http')
async def local_write_guard(request: Request, call_next):
    if request.url.path.startswith('/api/') and not request.url.path.startswith(('/api/public/', '/api/auth/', '/api/customer/')) and request.url.path not in ('/api/health',) and not agency_allowed(request):
        return JSONResponse({'detail': 'Agency sign-in required'}, status_code=401)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8001', 'http://localhost:8001', 'http://127.0.0.1:15173'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        upload = request.method == 'POST' and re.fullmatch(r'/api/(?:feedback/[a-f0-9-]{36}|public/submissions/[A-Za-z0-9_-]{43})/attachments', request.url.path)
        limit = MAX_BYTES if upload else 32768
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse({'detail': 'Screenshot exceeds 2 MiB.' if upload else 'Request is too large. Maximum JSON size is 32 KiB.'}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.get('/api/health')
def health(request: Request, db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Project))
    if not agency_allowed(request):
        return {'status': 'ok', 'version': app.version}
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

@app.put('/api/projects/{project_id}')
async def edit_project(project_id: str, data: ProjectIn, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, 'Project not found')
    project.name, project.url = data.name, data.url
    db.commit()
    return serialize(project)

@app.get('/api/feedback')
def feedback_list(db: Session = Depends(get_db)):
    query = select(Feedback).outerjoin(CustomerSubmission, CustomerSubmission.feedback_id == Feedback.id).where(Feedback.deleted_at.is_(None), (CustomerSubmission.id.is_(None)) | (CustomerSubmission.stage == 'submitted')).order_by(Feedback.updated_at.desc())
    return [serialize(f, db) for f in db.scalars(query).all()]

@app.delete('/api/feedback/{feedback_id}')
async def delete_feedback(feedback_id: str, request: Request, db: Session = Depends(get_db)):
    return erase_feedback(db, request.app, get_feedback(db, feedback_id))

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
    ensure_idle(app, feedback_id)
    customer = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == item.id))
    if customer and any(getattr(item, key) != value for key, value in data.model_dump().items()):
        raise HTTPException(409, 'Original customer feedback is preserved. Add a clarification or edit the report instead.')
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
    ensure_idle(app, feedback_id)
    if item.version != data.version:
        raise HTTPException(409, 'This report changed in another tab. Reopen it before saving.')
    if any((claim.source.startswith('screenshot:') or claim.source == 'captured_context') for claim in data.report.reproduction_steps) or (data.report.expected_behaviour and (data.report.expected_behaviour.source.startswith('screenshot:') or data.report.expected_behaviour.source == 'captured_context')):
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
    ensure_idle(app, feedback_id)
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
