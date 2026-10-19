"""Authenticated customer dashboard, project connections and legacy report claims."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Literal
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
def reports(include_archived: bool = False, q: str = Query(default='', max_length=200),
            project_id: str = Query(default='', max_length=100),
            status: Literal['all', 'draft', 'new', 'needs_information', 'in_progress', 'ready_to_retest', 'resolved'] = 'all',
            attention: Literal['all', 'reply', 'retest'] = 'all',
            archive: Literal['active', 'archived', 'all'] | None = None,
            account=Depends(require_customer), db: Session = Depends(get_db)):
    records = db.scalars(select(CustomerSubmission).join(Feedback, Feedback.id == CustomerSubmission.feedback_id)
        .where(CustomerSubmission.account_id == account.id, CustomerSubmission.stage != 'deleted', Feedback.deleted_at.is_(None),
               True if include_archived or archive in ('all', 'archived') else CustomerSubmission.archived_at.is_(None))
        .order_by(CustomerSubmission.created_at.desc())).all()
    records = [item for item in records if customer_can_access(db, account.id, db.get(IntakeLink, item.link_id).project_id)]
    result = []
    needle = q.strip().casefold()
    for item in records:
        if archive == 'archived' and not item.archived_at or archive == 'active' and item.archived_at:
            continue
        project = db.get(Project, db.get(IntakeLink, item.link_id).project_id)
        feedback = db.get(Feedback, item.feedback_id)
        if project_id and project.id != project_id:
            continue
        workflow = progress_snapshot(db, feedback, public=True, history=False) if item.stage == 'submitted' else None
        current_status = workflow['status'] if workflow else 'draft'
        if status != 'all' and current_status != status:
            continue
        if attention != 'all' and current_status != ('needs_information' if attention == 'reply' else 'ready_to_retest'):
            continue
        reference = item.feedback_id[:8].upper()
        if needle and needle not in (feedback.text + ' ' + project.name + ' BB-' + reference).casefold():
            continue
        result.append({'access_token': item.access_token, 'project_id': project.id, 'project_name': project.name,
            'reference': reference, 'stage': item.stage, 'archived_at': item.archived_at, 'draft_version': item.draft_version,
            'summary': feedback.text[:160], 'workflow': workflow})
    return result


@router.get('/projects')
def projects(account=Depends(require_customer), db: Session = Depends(get_db)):
    rows = db.execute(select(CustomerMembership, Project, IntakeLink)
        .join(Project, Project.id == CustomerMembership.project_id)
        .join(IntakeLink, IntakeLink.id == CustomerMembership.link_id)
        .where(CustomerMembership.account_id == account.id, CustomerMembership.revoked_at.is_(None)).order_by(Project.name)).all()
    return [{'id': project.id,
             'name': 'Private project invitation' if project.customer_access == 'members' and not account.email_verified_at else project.name,
             'team_name': '' if project.customer_access == 'members' and not account.email_verified_at else project.team_name,
             'intake_token': link.token if not link.revoked_at and customer_can_access(db, account.id, project.id) else None,
             'verification_required': project.customer_access == 'members' and not bool(account.email_verified_at),
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
