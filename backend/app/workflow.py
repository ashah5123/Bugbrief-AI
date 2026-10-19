"""Issue progress is independent of report generation and evidence versions."""
from datetime import date
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import Field, field_validator
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Feedback, CustomerSubmission, EmployeeAccount, EmployeeProject, IssueProgress, IssueEvent, ReportMessage, now
from .schemas import StrictModel
from .activity import actor_details, history_page

router = APIRouter()
LABELS = {'new': 'New', 'needs_information': 'Needs information', 'in_progress': 'In progress',
          'ready_to_retest': 'Ready to retest', 'resolved': 'Resolved'}
TRANSITIONS = {'new': {'needs_information', 'in_progress'},
               'needs_information': {'new', 'in_progress'},
               'in_progress': {'needs_information', 'ready_to_retest'},
               'ready_to_retest': {'needs_information', 'in_progress', 'resolved'},
               'resolved': {'in_progress'}}


def received_at(db, feedback):
    submission = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
    return submission.submitted_at if submission and submission.submitted_at else feedback.created_at


def waiting_since(db, feedback, status):
    """Only public responses clear a customer's wait; reads and private notes do not."""
    submission = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
    if not submission or submission.stage != 'submitted' or status == 'resolved':
        return None
    customer_reply = db.scalar(select(func.max(ReportMessage.created_at)).where(
        ReportMessage.feedback_id == feedback.id, ReportMessage.visibility == 'public',
        ReportMessage.author_role == 'customer'))
    retest = db.scalar(select(func.max(IssueEvent.created_at)).where(
        IssueEvent.feedback_id == feedback.id,
        IssueEvent.label == 'Customer says the issue is still happening'))
    customer_at = max(v for v in (submission.submitted_at or feedback.created_at, customer_reply, retest) if v)
    company_reply = db.scalar(select(func.max(ReportMessage.created_at)).where(
        ReportMessage.feedback_id == feedback.id, ReportMessage.visibility == 'public',
        ReportMessage.author_role == 'company'))
    company_update = db.scalar(select(func.max(IssueEvent.created_at)).where(
        IssueEvent.feedback_id == feedback.id,
        IssueEvent.visibility == 'public',
        ~IssueEvent.label.in_(['Customer confirmed the fix', 'Customer says the issue is still happening']),
        (IssueEvent.note != '') | IssueEvent.label.like('Status changed to %') |
        IssueEvent.label.like('Report reopened%')))
    responses = [v for v in (company_reply, company_update) if v]
    return customer_at if not responses or customer_at > max(responses) else None


def progress_snapshot(db, feedback, public=False, history=True):
    progress = db.get(IssueProgress, feedback.id)
    employee = db.get(EmployeeAccount, progress.assigned_employee_id) if progress and progress.assigned_employee_id else None
    status = progress.status if progress else 'new'
    value = {'status': status, 'label': LABELS[status],
             'assigned_to': {'name': employee.name} if employee else None,
             'updated_at': progress.updated_at if progress else received_at(db, feedback)}
    if public and status == 'ready_to_retest':
        value['retest_version'] = progress.version
    if not public:
        value.update(version=progress.version if progress else 0,
                     assigned_employee_id=progress.assigned_employee_id if progress else None,
                     priority=progress.priority if progress else 'normal',
                     due_date=progress.due_date if progress else None,
                     waiting_since=waiting_since(db, feedback, status))
    if history:
        page = history_page(db, IssueEvent, feedback.id, audience='customer' if public else 'company')
        value['events'] = page['items'] or [
            {'id': 'received', 'label': 'Report received', 'note': '', 'created_at': received_at(db, feedback), 'actor_name': None, 'actor_role': None}]
        value['history_truncated'] = bool(page['next_before'])
        value['history_before'] = page['next_before']
    return value


def visible_feedback(db, feedback_id):
    feedback = db.get(Feedback, feedback_id)
    if feedback is None or feedback.deleted_at:
        raise HTTPException(404, 'Feedback not found')
    submission = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
    if submission and submission.stage != 'submitted':
        raise HTTPException(409, 'The customer has not sent this report yet.')
    return feedback


class ProgressUpdate(StrictModel):
    version: int = Field(ge=0)
    status: Literal['new', 'needs_information', 'in_progress', 'ready_to_retest', 'resolved']
    assigned_employee_id: str | None = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=1000)


@router.get('/api/employees')
def employees(request: Request, db: Session = Depends(get_db)):
    from .project_access import company_project_ids
    ids = company_project_ids(request, db)
    query = select(EmployeeAccount).where(EmployeeAccount.disabled_at.is_(None))
    if ids is not None:
        query = query.where(EmployeeAccount.id.in_(select(EmployeeProject.employee_id).where(EmployeeProject.project_id.in_(ids))))
    return [{'id': employee.id, 'name': employee.name,
             'project_ids': [project_id for project_id in db.scalars(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == employee.id)).all()
                             if ids is None or project_id in ids]}
            for employee in db.scalars(query.order_by(EmployeeAccount.name, EmployeeAccount.id)).all()]


@router.get('/api/feedback/{feedback_id}/workflow')
def get_progress(feedback_id: str, db: Session = Depends(get_db)):
    return progress_snapshot(db, visible_feedback(db, feedback_id))


@router.patch('/api/feedback/{feedback_id}/workflow')
async def update_progress(feedback_id: str, data: ProgressUpdate, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    feedback = visible_feedback(db, feedback_id)
    current = db.get(IssueProgress, feedback_id)
    version = current.version if current else 0
    if data.version != version:
        raise HTTPException(409, 'Progress changed in another tab. Reload progress before saving.')
    previous = current.status if current else 'new'
    previous_employee = current.assigned_employee_id if current else None
    if data.status != previous and data.status not in TRANSITIONS[previous]:
        raise HTTPException(422, f'Cannot move directly from {LABELS[previous]} to {LABELS[data.status]}.')
    employee = db.get(EmployeeAccount, data.assigned_employee_id) if data.assigned_employee_id else None
    if data.assigned_employee_id and (employee is None or employee.disabled_at):
        raise HTTPException(422, 'Choose an employee from this workspace.')
    if employee and db.get(EmployeeProject, (employee.id, feedback.project_id)) is None:
        raise HTTPException(422, 'Assign an employee who belongs to this project. The workspace owner can add them under project access.')
    if data.status in ('in_progress', 'ready_to_retest', 'resolved') and employee is None:
        raise HTTPException(422, 'Assign an employee before work starts or a report is resolved.')
    note = data.note.strip()
    if data.status == 'needs_information' and previous != data.status and not note:
        raise HTTPException(422, 'Tell the customer what information is needed in the public update.')
    if previous == data.status and previous_employee == data.assigned_employee_id and not note:
        return progress_snapshot(db, feedback)
    stamp = now()
    values = {'status': data.status, 'assigned_employee_id': data.assigned_employee_id,
              'version': version+1, 'updated_at': stamp}
    try:
        if current:
            changed = db.execute(update(IssueProgress).where(IssueProgress.feedback_id == feedback_id,
                IssueProgress.version == data.version).values(**values))
            if changed.rowcount != 1:
                raise HTTPException(409, 'Progress changed in another tab. Reload progress before saving.')
        else:
            db.add(IssueProgress(feedback_id=feedback_id, **values))
            db.flush()
            db.add(IssueEvent(feedback_id=feedback_id, label='Report received', note='', created_at=received_at(db, feedback), actor_name='System', actor_role='system'))
        parts = []
        if data.status != previous:
            parts.append('Report reopened' if previous == 'resolved' else 'Status changed to ' + LABELS[data.status])
        if previous_employee != data.assigned_employee_id:
            parts.append('Assigned to ' + employee.name if employee else 'Assignment removed')
        db.add(IssueEvent(feedback_id=feedback_id, label=' · '.join(parts) or 'Update from the company', note=note, created_at=stamp, **actor_details(request, db)))
        from .notifications import emit, add_alert, deliver_pending
        if data.status != previous or note:
            emit(db, request, feedback, 'retest_requested' if data.status == 'ready_to_retest' else 'progress_update',
                 'A fix is ready to retest' if data.status == 'ready_to_retest' else 'Report progress updated', customer=True)
        if employee and previous_employee != employee.id:
            from .employee_auth import current_employee
            actor = current_employee(request, db)
            if actor is None or actor.id != employee.id:
                add_alert(db, feedback, 'employee', employee.id, 'assigned', 'An issue was assigned to you')
        db.commit()
        background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Progress changed in another tab. Reload progress before saving.')
    db.expire_all()
    return progress_snapshot(db, db.get(Feedback, feedback_id))


class TriageUpdate(StrictModel):
    version: int = Field(ge=0)
    priority: Literal['low', 'normal', 'high', 'urgent']
    due_date: str | None = Field(default=None, max_length=10)

    @field_validator('due_date')
    @classmethod
    def calendar_date(cls, value):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('Choose a date in YYYY-MM-DD format.')
            date.fromisoformat(value)
        return value


@router.patch('/api/feedback/{feedback_id}/triage')
def update_triage(feedback_id: str, data: TriageUpdate, request: Request, db: Session = Depends(get_db)):
    feedback = visible_feedback(db, feedback_id)
    current = db.get(IssueProgress, feedback_id)
    version = current.version if current else 0
    if version != data.version:
        raise HTTPException(409, 'Report changed in another tab. Reload triage before saving.')
    if current and current.priority == data.priority and current.due_date == data.due_date:
        return progress_snapshot(db, feedback)
    values = dict(priority=data.priority, due_date=data.due_date, version=version + 1, updated_at=now())
    try:
        if current:
            changed = db.execute(update(IssueProgress).where(IssueProgress.feedback_id == feedback_id,
                IssueProgress.version == data.version).values(**values))
            if changed.rowcount != 1:
                raise HTTPException(409, 'Report changed in another tab. Reload triage before saving.')
        else:
            db.add(IssueProgress(feedback_id=feedback_id, status='new', **values))
            db.flush()
            db.add(IssueEvent(feedback_id=feedback_id, label='Report received', note='', created_at=received_at(db, feedback), actor_name='System', actor_role='system'))
        db.add(IssueEvent(feedback_id=feedback_id, label='Triage updated', note='Priority: ' + data.priority + '. Due date: ' + (data.due_date or 'Not set'), visibility='internal', **actor_details(request, db)))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Report changed in another tab. Reload triage before saving.')
    db.expire_all()
    return progress_snapshot(db, db.get(Feedback, feedback_id))
