"""Project access is checked on the server, including direct report/evidence URLs."""
import secrets
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session
from .db import get_db
from .models import (Project, Feedback, EmployeeAccount, EmployeeProject, CustomerAccount,
                     CustomerMembership, IntakeLink, IssueProgress, IssueEvent, now)
from .auth import owner_allowed
from .employee_auth import current_employee
from .customer_auth import current_customer
from .account_management import require_owner, EmailInput
from .schemas import StrictModel

router = APIRouter()


def employee_has_project(db, employee_id, project_id):
    return db.get(EmployeeProject, (employee_id, project_id)) is not None


def company_project_ids(request, db):
    if owner_allowed(request):
        return None
    employee = current_employee(request, db)
    return list(db.scalars(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == employee.id)).all()) if employee else []


def require_company_project(request, db, project_id):
    project = db.get(Project, project_id)
    ids = company_project_ids(request, db)
    if not project or (ids is not None and project_id not in ids):
        raise HTTPException(404, 'Project not found or access has been removed.')
    return project


def project_permissions(request, db, project_id):
    if owner_allowed(request):
        return {'role': 'owner', 'work': True, 'manage': True, 'delete': True}
    employee = current_employee(request, db)
    grant = db.get(EmployeeProject, (employee.id, project_id)) if employee else None
    return {'role': grant.role if grant else 'none', 'work': bool(grant and grant.role in ('contributor', 'manager')),
            'manage': bool(grant and grant.role == 'manager'), 'delete': bool(grant and grant.can_delete)}


def require_project_action(request, db, project_id, action):
    require_company_project(request, db, project_id)
    if not project_permissions(request, db, project_id)[action]:
        raise HTTPException(403, 'Your project permissions do not allow this action. Ask the workspace owner.')


def customer_membership(db, account_id, project_id):
    return db.scalar(select(CustomerMembership).where(CustomerMembership.account_id == account_id,
        CustomerMembership.project_id == project_id))


def customer_can_access(db, account_id, project_id):
    member = customer_membership(db, account_id, project_id)
    project = db.get(Project, project_id)
    if not project or (member and member.revoked_at):
        return False
    return project.customer_access == 'link' or bool(member)


def require_customer_project(request, db, project_id):
    account = current_customer(request, db)
    if not customer_can_access(db, account.id if account else '', project_id):
        raise HTTPException(403 if account else 401, 'Sign in with a customer account invited to this project. Contact the workspace owner if your access was removed.')


@router.get('/api/projects/{project_id}/access', dependencies=[Depends(require_owner)])
def access(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, 'Project not found.')
    employees = db.scalars(select(EmployeeAccount).join(EmployeeProject, EmployeeProject.employee_id == EmployeeAccount.id)
        .where(EmployeeProject.project_id == project_id, EmployeeAccount.disabled_at.is_(None)).order_by(EmployeeAccount.name)).all()
    customers = db.execute(select(CustomerAccount, CustomerMembership).join(CustomerMembership,
        CustomerMembership.account_id == CustomerAccount.id).where(CustomerMembership.project_id == project_id).order_by(CustomerAccount.name)).all()
    return {'customer_access': project.customer_access,
        'employees': [{'id': m.id, 'name': m.name, 'email': m.email,
                       'role': db.get(EmployeeProject, (m.id, project_id)).role,
                       'can_delete': bool(db.get(EmployeeProject, (m.id, project_id)).can_delete)} for m in employees],
        'customers': [{'id': m.id, 'name': m.name, 'email': m.email, 'revoked_at': membership.revoked_at} for m, membership in customers]}


class CustomerAccess(StrictModel):
    mode: Literal['link', 'members']


class EmployeePermissions(StrictModel):
    role: Literal['viewer', 'contributor', 'manager']
    can_delete: bool = False


@router.patch('/api/projects/{project_id}/members/employee/{member_id}', dependencies=[Depends(require_owner)])
def employee_permissions(project_id: str, member_id: str, data: EmployeePermissions, db: Session = Depends(get_db)):
    grant = db.get(EmployeeProject, (member_id, project_id))
    if not grant:
        raise HTTPException(404, 'Employee project membership not found.')
    grant.role, grant.can_delete = data.role, int(data.can_delete)
    db.commit()
    return access(project_id, db)


@router.patch('/api/projects/{project_id}/access', dependencies=[Depends(require_owner)])
def change_access(project_id: str, data: CustomerAccess, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, 'Project not found.')
    project.customer_access = data.mode
    db.commit()
    return access(project_id, db)


@router.post('/api/projects/{project_id}/members/{role}', dependencies=[Depends(require_owner)])
def add_member(project_id: str, role: Literal['employee', 'customer'], data: EmailInput, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, 'Project not found.')
    model = EmployeeAccount if role == 'employee' else CustomerAccount
    member = db.scalar(select(model).where(model.email == data.email))
    if not member or getattr(member, 'disabled_at', None):
        raise HTTPException(404, f'No active {role} account uses this email. Ask them to create their account first.')
    if role == 'employee':
        if not employee_has_project(db, member.id, project_id):
            db.add(EmployeeProject(employee_id=member.id, project_id=project_id))
    else:
        membership = customer_membership(db, member.id, project_id)
        if membership:
            membership.revoked_at = None
            active = db.scalar(select(IntakeLink).where(IntakeLink.project_id == project_id, IntakeLink.revoked_at.is_(None)))
            if active:
                membership.link_id = active.id
        else:
            link = db.scalar(select(IntakeLink).where(IntakeLink.project_id == project_id, IntakeLink.revoked_at.is_(None)))
            if not link:
                link = IntakeLink(project_id=project_id, token=secrets.token_urlsafe(32))
                db.add(link); db.flush()
            db.add(CustomerMembership(account_id=member.id, project_id=project_id, link_id=link.id))
    db.commit()
    return access(project_id, db)


@router.delete('/api/projects/{project_id}/members/{role}/{member_id}', dependencies=[Depends(require_owner)])
def remove_member(project_id: str, role: Literal['employee', 'customer'], member_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, 'Project not found.')
    if role == 'employee':
        db.execute(delete(EmployeeProject).where(EmployeeProject.project_id == project_id, EmployeeProject.employee_id == member_id))
        feedback_ids = select(Feedback.id).where(Feedback.project_id == project_id)
        for progress in db.scalars(select(IssueProgress).where(IssueProgress.feedback_id.in_(feedback_ids), IssueProgress.assigned_employee_id == member_id)).all():
            progress.assigned_employee_id = None
            progress.version += 1
            progress.updated_at = now()
            db.add(IssueEvent(feedback_id=progress.feedback_id, label='Assignment removed', note='The team will assign a new employee.'))
    else:
        member = customer_membership(db, member_id, project_id)
        if not member:
            raise HTTPException(404, 'Customer membership not found.')
        member.revoked_at = now()
    db.commit()
    return access(project_id, db)
