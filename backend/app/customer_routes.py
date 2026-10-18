"""Authenticated customer dashboard, project connections and legacy report claims."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, update, or_
from sqlalchemy.orm import Session
from .db import get_db
from .schemas import StrictModel
from .models import CustomerSubmission, CustomerMembership, IntakeLink, Project, Feedback
from .customer_auth import require_customer
from .customer_projects import connect_project
from .intake import active_link, snapshot
from .workflow import progress_snapshot
from .project_access import customer_can_access, require_customer_project

router = APIRouter(prefix='/api/customer')


class Capability(StrictModel):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


@router.get('/reports')
def reports(account=Depends(require_customer), db: Session = Depends(get_db)):
    records = db.scalars(select(CustomerSubmission).join(Feedback, Feedback.id == CustomerSubmission.feedback_id)
        .where(CustomerSubmission.account_id == account.id, CustomerSubmission.stage != 'deleted', Feedback.deleted_at.is_(None))
        .order_by(CustomerSubmission.created_at.desc())).all()
    records = [item for item in records if customer_can_access(db, account.id, db.get(IntakeLink, item.link_id).project_id)]
    return [{'access_token': item.access_token, 'project_name': db.get(Project, db.get(IntakeLink, item.link_id).project_id).name,
             'reference': item.feedback_id[:8].upper(), 'stage': item.stage,
             'summary': db.get(Feedback, item.feedback_id).text[:160],
             'workflow': progress_snapshot(db, db.get(Feedback, item.feedback_id), public=True, history=False) if item.stage == 'submitted' else None} for item in records]


@router.get('/projects')
def projects(account=Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.execute(select(CustomerMembership, Project, IntakeLink)
        .join(Project, Project.id == CustomerMembership.project_id)
        .join(IntakeLink, IntakeLink.id == CustomerMembership.link_id)
        .where(CustomerMembership.account_id == account.id, CustomerMembership.revoked_at.is_(None)).order_by(Project.name)).all()
    return [{'id': project.id, 'name': project.name, 'team_name': project.team_name, 'intake_token': link.token if not link.revoked_at else None,
             'closed': bool(link.revoked_at)} for _, project, link in rows]


@router.post('/projects')
def join_project(data: Capability, account=Depends(require_customer), db: Session = Depends(get_db)):
    link = active_link(db, data.token)
    connect_project(db, account.id, link)
    db.commit()
    project = db.get(Project, link.project_id)
    return {'id': project.id, 'name': project.name, 'team_name': project.team_name, 'intake_token': link.token, 'closed': False}


@router.post('/claims')
def claim(data: Capability, request: Request, account=Depends(require_customer), db: Session = Depends(get_db)):
    item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.access_token == data.token))
    if item is None or item.stage == 'deleted' or (item.account_id and item.account_id != account.id):
        raise HTTPException(404, 'This report is unavailable for your account.')
    link = db.get(IntakeLink, item.link_id)
    require_customer_project(request, db, link.project_id)
    # The bearer capability is proof of access to a guest submission; never infer ownership from a name/email.
    changed = db.execute(update(CustomerSubmission).where(
        CustomerSubmission.id == item.id,
        or_(CustomerSubmission.account_id.is_(None), CustomerSubmission.account_id == account.id),
        CustomerSubmission.stage != 'deleted').values(account_id=account.id))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(404, 'This report is unavailable for your account.')
    db.refresh(item)
    link = db.get(IntakeLink, item.link_id)
    connect_project(db, account.id, link)
    db.commit()
    return snapshot(db, item)
