"""Immutable actor snapshots and bounded history pages with per-audience visibility."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from .db import get_db
from .models import IssueEvent, ProjectEvent

router = APIRouter()


def actor_details(request, db, customer=False, guest_name='Customer'):
    if customer:
        from .customer_auth import current_customer
        account = current_customer(request, db)
        return {'actor_role': 'customer', 'actor_name': account.name if account else guest_name or 'Customer'}
    from .auth import owner_allowed
    from .employee_auth import current_employee
    if owner_allowed(request):
        return {'actor_role': 'owner', 'actor_name': 'Workspace owner'}
    employee = current_employee(request, db)
    return {'actor_role': 'employee', 'actor_name': employee.name} if employee else {'actor_role': 'system', 'actor_name': 'System'}


def project_event(db, request, project_id, label, note=''):
    db.add(ProjectEvent(project_id=project_id, label=label, note=note, **actor_details(request, db)))


def history_page(db, model, target_id, before=None, audience='company'):
    foreign_key = model.feedback_id if model is IssueEvent else model.project_id
    conditions = [foreign_key == target_id]
    if model is IssueEvent:
        conditions.append(IssueEvent.visibility.in_(('public', 'customer') if audience == 'customer' else ('public', 'internal')))
    if before:
        cursor = db.scalar(select(model).where(*conditions, model.id == before))
        if not cursor:
            raise HTTPException(404, 'This history position is unavailable. Reload the report.')
        conditions.append(or_(model.created_at < cursor.created_at,
            and_(model.created_at == cursor.created_at, model.id < cursor.id)))
    rows = list(db.scalars(select(model).where(*conditions).order_by(model.created_at.desc(), model.id.desc()).limit(51)))
    more = len(rows) > 50
    rows = rows[:50]
    return {'items': [{'id': row.id, 'label': row.label, 'note': row.note, 'created_at': row.created_at,
                       'actor_name': row.actor_name, 'actor_role': row.actor_role} for row in reversed(rows)],
            'next_before': rows[-1].id if more else None}


@router.get('/api/feedback/{feedback_id}/activity')
def company_history(feedback_id: str, before: str | None = None, db: Session = Depends(get_db)):
    from .workflow import visible_feedback
    visible_feedback(db, feedback_id)
    return history_page(db, IssueEvent, feedback_id, before)


@router.get('/api/public/submissions/{token}/activity')
def customer_history(token: str, request: Request, before: str | None = None, db: Session = Depends(get_db)):
    from .conversation import sent_submission
    item = sent_submission(db, token, request)
    return history_page(db, IssueEvent, item.feedback_id, before, 'customer')


@router.get('/api/projects/{project_id}/activity')
def project_history(project_id: str, request: Request, before: str | None = None, db: Session = Depends(get_db)):
    from .account_management import require_owner
    from .project_access import require_company_project
    require_owner(request)
    require_company_project(request, db, project_id)
    return history_page(db, ProjectEvent, project_id, before)
