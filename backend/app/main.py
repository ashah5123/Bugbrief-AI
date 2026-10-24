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
from .conversation import router as conversation_router
from .duplicates import router as duplicates_router
from .reply_media import MAX_REPLY_BODY
from .archive import router as archive_router
from .activity import router as activity_router, actor_details, project_event
from .account_management import router as account_management_router
from .project_access import router as access_router, company_project_ids, require_company_project, require_project_action, project_permissions
from .employee_auth import current_employee
from .models import EmployeeProject, EmployeeAccount, IssueProgress, IssueEvent
from .notifications import router as notification_router, deliver_pending
from .saved_views import router as saved_views_router
from .reminders import router as reminder_router, run_reminders

@asynccontextmanager
async def lifespan(app):
    access_code()
    async def mail_worker():
        while True:
            await asyncio.to_thread(run_reminders, app.state.session_factory)
            await asyncio.to_thread(deliver_pending, app.state.session_factory)
            await asyncio.sleep(30)
    worker = asyncio.create_task(mail_worker())
    try:
        yield
    finally:
        worker.cancel()
        from contextlib import suppress
        with suppress(asyncio.CancelledError):
            await worker

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
app.include_router(conversation_router)
app.include_router(duplicates_router)
app.include_router(account_management_router)
app.include_router(access_router)
app.include_router(notification_router)
app.include_router(saved_views_router)
app.include_router(reminder_router)
app.include_router(archive_router)
app.include_router(activity_router)

@app.middleware('http')
async def local_write_guard(request: Request, call_next):
    if request.url.path.startswith('/api/') and not request.url.path.startswith(('/api/public/', '/api/auth/', '/api/customer/')) and request.url.path not in ('/api/health',) and not agency_allowed(request):
        return JSONResponse({'detail': 'Agency sign-in required'}, status_code=401)
    target = re.match(r'^/api/(projects|feedback)/([^/]+)(?:/|$)', request.url.path)
    if target:
        with request.app.state.session_factory() as db:
            project_id = target[2] if target[1] == 'projects' else None
            if target[1] == 'feedback':
                item = db.get(Feedback, target[2])
                if item:
                    pending = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == item.id))
                    if pending and pending.stage != 'submitted':
                        return JSONResponse({'detail': 'Feedback not found'}, status_code=404)
                    project_id = item.project_id
            if project_id:
                try:
                    require_company_project(request, db, project_id)
                    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                        action = 'work'
                        if target[1] == 'projects':
                            action = 'manage'
                        elif request.method == 'DELETE' and request.url.path.rstrip('/') == f'/api/feedback/{target[2]}':
                            action = 'delete'
                        require_project_action(request, db, project_id, action)
                except HTTPException as error:
                    return JSONResponse({'detail': error.detail}, status_code=error.status_code)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8001', 'http://localhost:8001', 'http://127.0.0.1:15173'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        upload = request.method == 'POST' and re.fullmatch(r'/api/(?:feedback/[a-f0-9-]{36}|public/submissions/[A-Za-z0-9_-]{43})/attachments', request.url.path)
        reply = request.method == 'POST' and re.fullmatch(r'/api/(?:feedback/[a-f0-9-]{36}|public/submissions/[A-Za-z0-9_-]{43})/messages', request.url.path)
        draft = (request.method == 'POST' and re.fullmatch(r'/api/public/intake/[A-Za-z0-9_-]{43}/submissions', request.url.path)) or (request.method == 'PUT' and re.fullmatch(r'/api/public/submissions/[A-Za-z0-9_-]{43}', request.url.path))
        limit = MAX_BYTES if upload else MAX_REPLY_BODY if reply else 65536 if draft else 32768
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse({'detail': 'Screenshot exceeds 2 MiB.' if upload else 'Reply is too large. Attach at most three reviewed screenshots, each up to 2 MiB.' if reply else f'Request is too large. Maximum JSON size is {limit // 1024} KiB.'}, status_code=413)
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
def projects(request: Request, db: Session = Depends(get_db)):
    ids = company_project_ids(request, db)
    query = select(Project).order_by(Project.created_at)
    if ids is not None:
        query = query.where(Project.id.in_(ids))
    return [{**serialize(p), 'permissions': project_permissions(request, db, p.id)} for p in db.scalars(query).all()]

@app.post('/api/projects', status_code=201)
async def create_project(data: ProjectIn, request: Request, db: Session = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    db.flush()
    employee = current_employee(request, db)
    if employee:
        db.add(EmployeeProject(employee_id=employee.id, project_id=project.id, role='manager'))
    project_event(db, request, project.id, 'Project created', 'Creator received Manager access without permanent deletion.' if employee else '')
    db.commit()
    return serialize(project)

@app.put('/api/projects/{project_id}')
async def edit_project(project_id: str, data: ProjectIn, request: Request, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, 'Project not found')
    changed = [label for key, label in [('name', 'Name'), ('url', 'Website URL'), ('team_name', 'Team name')]
               if key in data.model_fields_set and getattr(project, key) != getattr(data, key)]
    if changed:
        project_event(db, request, project_id, 'Project settings changed', ', '.join(changed))
    project.name, project.url = data.name, data.url
    if 'team_name' in data.model_fields_set:
        project.team_name = data.team_name
    db.commit()
    return serialize(project)

@app.get('/api/feedback')
def feedback_list(request: Request, include_archived: bool = False, db: Session = Depends(get_db)):
    query = select(Feedback).outerjoin(CustomerSubmission, CustomerSubmission.feedback_id == Feedback.id).where(Feedback.deleted_at.is_(None), (CustomerSubmission.id.is_(None)) | (CustomerSubmission.stage == 'submitted')).order_by(Feedback.updated_at.desc())
    ids = company_project_ids(request, db)
    if not include_archived:
        query = query.where(Feedback.archived_at.is_(None))
    if ids is not None:
        query = query.where(Feedback.project_id.in_(ids))
    return [serialize(f, db) for f in db.scalars(query).all()]

@app.delete('/api/feedback/{feedback_id}')
async def delete_feedback(feedback_id: str, request: Request, db: Session = Depends(get_db)):
    return erase_feedback(db, request.app, get_feedback(db, feedback_id))

@app.post('/api/feedback', status_code=201)
async def create_feedback(data: FeedbackIn, request: Request, db: Session = Depends(get_db)):
    require_project_action(request, db, data.project_id, 'work')
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    feedback = Feedback(**data.model_dump())
    db.add(feedback)
    db.commit()
    return serialize(feedback, db)

@app.put('/api/feedback/{feedback_id}')
async def edit_feedback(feedback_id: str, data: FeedbackIn, request: Request, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    ensure_idle(app, feedback_id)
    customer = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == item.id))
    if customer and any(getattr(item, key) != value for key, value in data.model_dump().items()):
        raise HTTPException(409, 'Original customer feedback is preserved. Add a clarification or edit the report instead.')
    require_project_action(request, db, data.project_id, 'work')
    if not db.get(Project, data.project_id):
        raise HTTPException(404, 'Project not found')
    if item.project_id != data.project_id:
        from .duplicates import group_for
        if group_for(db, item.id):
            raise HTTPException(409, 'Unlink this report from its shared issue before moving it to another project.')
        progress = db.get(IssueProgress, item.id)
        if progress and progress.assigned_employee_id:
            employee = db.get(EmployeeAccount, progress.assigned_employee_id)
            if not employee or employee.disabled_at or not db.get(EmployeeProject, (employee.id, data.project_id)):
                progress.assigned_employee_id = None
                progress.version += 1
                progress.updated_at = now()
                db.add(IssueEvent(feedback_id=item.id, label='Assignment removed', note='The report moved to another project. The team will assign an employee from that project.', **actor_details(request, db)))
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
