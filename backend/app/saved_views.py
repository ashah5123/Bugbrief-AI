"""Personal inbox filters never grant access to report content."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from sqlalchemy import select, update, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import SavedView, Project, EmployeeAccount, EmployeeProject, CustomerSubmission, Feedback
from .schemas import StrictModel
from .auth import owner_allowed
from .employee_auth import current_employee
from .project_access import company_project_ids

router = APIRouter(prefix='/api/saved-views')
LIMIT = 20


class ViewFilters(StrictModel):
    view: Literal['feedback', 'reports'] = 'feedback'
    archive: bool = False
    search: str = Field(default='', max_length=200)
    project_id: str = Field(default='all', min_length=1, max_length=100)
    status: Literal['all', 'draft', 'review'] = 'all'
    progress: Literal['all', 'new', 'needs_information', 'in_progress', 'ready_to_retest', 'resolved'] = 'all'
    priority: Literal['all', 'low', 'normal', 'high', 'urgent'] = 'all'
    attention: Literal['all', 'open', 'overdue', 'today', 'waiting', 'retest', 'unassigned'] = 'all'
    assignee: str = Field(default='all', min_length=1, max_length=100)
    customer: str = Field(default='all', min_length=1, max_length=110)
    sort: Literal['triage', 'due', 'newest'] = 'triage'


class ViewInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    filters: ViewFilters

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Name your saved view.')
        return value.strip()


class ViewUpdate(ViewInput):
    version: int = Field(ge=1)


class ViewDelete(StrictModel):
    version: int = Field(ge=1)


def identity(request, db):
    if owner_allowed(request, db):
        return 'owner', 'owner'
    employee = current_employee(request, db)
    if employee:
        return 'employee', employee.id
    raise HTTPException(401, 'Sign in to the company workspace to use saved views.')


def available(request, db, filters):
    ids = company_project_ids(request, db)
    project = filters['project_id']
    if project != 'all' and (not db.get(Project, project) or (ids is not None and project not in ids)):
        return False
    assignee = filters['assignee']
    if assignee == 'me':
        if owner_allowed(request, db) or not current_employee(request, db):
            return False
    elif assignee not in ('all', 'unassigned'):
        person = db.get(EmployeeAccount, assignee)
        grants = select(EmployeeProject.employee_id).where(EmployeeProject.employee_id == assignee)
        if project != 'all':
            grants = grants.where(EmployeeProject.project_id == project)
        elif ids is not None:
            grants = grants.where(EmployeeProject.project_id.in_(ids))
        if not person or person.disabled_at or (project != 'all' or ids is not None) and not db.scalar(grants):
            return False
    customer = filters['customer']
    if customer not in ('all', 'manual'):
        if not customer.startswith('customer:'):
            return False
        target = customer.removeprefix('customer:')
        query = select(CustomerSubmission.id).join(Feedback, Feedback.id == CustomerSubmission.feedback_id).where(
            Feedback.deleted_at.is_(None), CustomerSubmission.stage == 'submitted',
            or_(CustomerSubmission.account_id == target,
                (CustomerSubmission.account_id.is_(None)) & (CustomerSubmission.id == target)))
        if project != 'all':
            query = query.where(Feedback.project_id == project)
        elif ids is not None:
            query = query.where(Feedback.project_id.in_(ids))
        if not db.scalar(query.limit(1)):
            return False
    return True


def snapshot(request, db, row):
    return {'id': row.id, 'name': row.name, 'filters': row.filters, 'version': row.version,
            'unavailable': not available(request, db, row.filters)}


def own_row(db, view_id, actor):
    row = db.get(SavedView, view_id)
    if not row or (row.scope, row.account_id) != actor:
        raise HTTPException(404, 'Saved view not found.')
    return row


def conflict():
    return HTTPException(409, 'Saved views changed or this name is already used. Reload saved views before trying again.')


@router.get('')
def list_views(request: Request, db: Session = Depends(get_db)):
    scope, account = identity(request, db)
    rows = db.scalars(select(SavedView).where(SavedView.scope == scope, SavedView.account_id == account)
        .order_by(SavedView.name_key, SavedView.id))
    return [snapshot(request, db, row) for row in rows]


@router.get('/{view_id}')
def get_view(view_id: str, request: Request, db: Session = Depends(get_db)):
    return snapshot(request, db, own_row(db, view_id, identity(request, db)))


@router.post('', status_code=201)
def create_view(data: ViewInput, request: Request, db: Session = Depends(get_db)):
    scope, account = identity(request, db)
    filters = data.filters.model_dump()
    if not available(request, db, filters):
        raise HTTPException(404, 'One of these filters is unavailable. Choose an accessible project, employee or customer.')
    used = set(db.scalars(select(SavedView.slot).where(SavedView.scope == scope, SavedView.account_id == account)))
    slot = next((number for number in range(LIMIT) if number not in used), None)
    if slot is None:
        raise HTTPException(422, 'You can keep up to 20 saved views. Delete one before adding another.')
    row = SavedView(scope=scope, account_id=account, slot=slot, name=data.name, name_key=data.name.casefold(), filters=filters)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict()
    return snapshot(request, db, row)


@router.patch('/{view_id}')
def update_view(view_id: str, data: ViewUpdate, request: Request, db: Session = Depends(get_db)):
    actor = identity(request, db)
    own_row(db, view_id, actor)
    if not available(request, db, data.filters.model_dump()):
        raise HTTPException(404, 'One of these filters is unavailable. Choose an accessible project, employee or customer.')
    try:
        changed = db.execute(update(SavedView).where(SavedView.id == view_id, SavedView.version == data.version,
            SavedView.scope == actor[0], SavedView.account_id == actor[1]).values(name=data.name, name_key=data.name.casefold(),
                filters=data.filters.model_dump(), version=data.version+1))
        if changed.rowcount != 1:
            raise conflict()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict()
    db.expire_all()
    return snapshot(request, db, db.get(SavedView, view_id))


@router.delete('/{view_id}')
def delete_view(view_id: str, data: ViewDelete, request: Request, db: Session = Depends(get_db)):
    actor = identity(request, db)
    own_row(db, view_id, actor)
    result = db.execute(delete(SavedView).where(SavedView.id == view_id, SavedView.version == data.version,
        SavedView.scope == actor[0], SavedView.account_id == actor[1]))
    if result.rowcount != 1:
        raise conflict()
    db.commit()
    return {'deleted': True}
