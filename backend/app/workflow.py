"""Issue progress is independent of report generation and evidence versions."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import Field
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Feedback, CustomerSubmission, EmployeeAccount, EmployeeProject, IssueProgress, IssueEvent, now
from .schemas import StrictModel

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
                     assigned_employee_id=progress.assigned_employee_id if progress else None)
    if history:
        events = db.scalars(select(IssueEvent).where(IssueEvent.feedback_id == feedback.id)
            .order_by(IssueEvent.created_at.desc(), IssueEvent.id.desc()).limit(50)).all()
        total = db.scalar(select(func.count()).select_from(IssueEvent).where(IssueEvent.feedback_id == feedback.id))
        value['events'] = [{'id': event.id, 'label': event.label, 'note': event.note, 'created_at': event.created_at}
                           for event in reversed(events)] or [
            {'id': 'received', 'label': 'Report received', 'note': '', 'created_at': received_at(db, feedback)}]
        value['history_truncated'] = total > 50
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
            db.add(IssueEvent(feedback_id=feedback_id, label='Report received', note='', created_at=received_at(db, feedback)))
        parts = []
        if data.status != previous:
            parts.append('Report reopened' if previous == 'resolved' else 'Status changed to ' + LABELS[data.status])
        if previous_employee != data.assigned_employee_id:
            parts.append('Assigned to ' + employee.name if employee else 'Assignment removed')
        db.add(IssueEvent(feedback_id=feedback_id, label=' · '.join(parts) or 'Update from the company', note=note, created_at=stamp))
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
