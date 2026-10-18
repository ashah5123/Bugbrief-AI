"""Company-only flat duplicate groups; public messages never disclose other reports."""
import hashlib
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import Field, field_validator
from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import (Feedback, CustomerSubmission, EmployeeAccount, EmployeeProject, IssueProgress,
                     IssueEvent, ReportMessage, DuplicateGroup, DuplicateMember, DuplicateAction, now)
from .schemas import StrictModel
from .workflow import visible_feedback, progress_snapshot, received_at, LABELS
from .notifications import emit, add_alert, deliver_pending
from .employee_auth import current_employee
from .customer_auth import throttle

router = APIRouter(prefix='/api/feedback')
MAX_MEMBERS = 50


def group_for(db, feedback_id):
    member = db.get(DuplicateMember, feedback_id)
    return db.get(DuplicateGroup, member.group_id) if member else None


def group_summary(db, feedback_id):
    group = group_for(db, feedback_id)
    if not group:
        return None
    count = db.scalar(select(func.count()).select_from(DuplicateMember).where(DuplicateMember.group_id == group.id))
    return {'main_feedback_id': group.main_feedback_id, 'count': count, 'is_main': group.main_feedback_id == feedback_id}


def members(db, group):
    return db.scalars(select(Feedback).join(DuplicateMember, DuplicateMember.feedback_id == Feedback.id)
        .where(DuplicateMember.group_id == group.id).order_by(Feedback.created_at, Feedback.id)).all()


def snapshot(db, feedback_id):
    group = group_for(db, feedback_id)
    if not group:
        return {'group': None}
    rows = members(db, group)
    return {'group': {'main_feedback_id': group.main_feedback_id, 'version': group.version,
        'work_status': group.work_status, 'assigned_employee_id': group.assigned_employee_id,
        'members': [{'id': row.id, 'reference': row.id[:8].upper(),
            'title': (row.report or {}).get('title') or row.text[:120] or 'Untitled feedback',
            'workflow': progress_snapshot(db, row, history=False)} for row in rows]}}


def conflict():
    return HTTPException(409, 'Linked reports changed. Reload linked reports before trying again.')


def lock_group(db, group, version, **values):
    changed = db.execute(update(DuplicateGroup).where(DuplicateGroup.id == group.id,
        DuplicateGroup.version == version).values(version=version + 1, **values))
    if changed.rowcount != 1:
        raise conflict()


def remove_group(db, group_id):
    db.execute(delete(DuplicateAction).where(DuplicateAction.group_id == group_id))
    db.execute(delete(DuplicateMember).where(DuplicateMember.group_id == group_id))
    db.execute(delete(DuplicateGroup).where(DuplicateGroup.id == group_id))


def detach_for_deletion(db, feedback_id):
    group = group_for(db, feedback_id)
    if not group:
        return
    if group.main_feedback_id == feedback_id:
        remove_group(db, group.id)
    else:
        db.execute(delete(DuplicateMember).where(DuplicateMember.feedback_id == feedback_id))
        remaining = db.scalar(select(func.count()).select_from(DuplicateMember).where(DuplicateMember.group_id == group.id))
        if remaining < 2:
            remove_group(db, group.id)
        else:
            lock_group(db, group, group.version)


class GroupVersion(StrictModel):
    version: int = Field(ge=0)


class LinkInput(GroupVersion):
    main_feedback_id: str = Field(min_length=1, max_length=100)


@router.get('/{feedback_id}/duplicates')
def detail(feedback_id: str, db: Session = Depends(get_db)):
    visible_feedback(db, feedback_id)
    return snapshot(db, feedback_id)


@router.get('/{feedback_id}/duplicates/candidates')
def candidates(feedback_id: str, q: str = '', db: Session = Depends(get_db)):
    feedback = visible_feedback(db, feedback_id)
    if len(q) > 120:
        raise HTTPException(422, 'Search is limited to 120 characters.')
    query = select(Feedback).outerjoin(CustomerSubmission, CustomerSubmission.feedback_id == Feedback.id).where(
        Feedback.project_id == feedback.project_id, Feedback.id != feedback_id, Feedback.deleted_at.is_(None),
        or_(CustomerSubmission.id.is_(None), CustomerSubmission.stage == 'submitted'))
    if q.strip():
        term = q.strip().lower()
        query = query.where(or_(func.lower(Feedback.text).contains(term, autoescape=True),
            func.lower(Feedback.id).contains(term, autoescape=True),
            func.lower(Feedback.report['title'].as_string()).contains(term, autoescape=True)))
    # Child reports cannot become a main report; explicit unlinking prevents nested groups/cycles.
    children = select(DuplicateMember.feedback_id).join(DuplicateGroup, DuplicateGroup.id == DuplicateMember.group_id).where(
        DuplicateMember.feedback_id != DuplicateGroup.main_feedback_id)
    rows = db.scalars(query.where(Feedback.id.not_in(children)).order_by(Feedback.created_at.desc(), Feedback.id).limit(50)).all()
    return [{'id': row.id, 'reference': row.id[:8].upper(),
             'title': (row.report or {}).get('title') or row.text[:120] or 'Untitled feedback',
             'version': group_for(db, row.id).version if group_for(db, row.id) else 0} for row in rows]


@router.post('/{feedback_id}/duplicates')
async def link(feedback_id: str, data: LinkInput, db: Session = Depends(get_db)):
    feedback = visible_feedback(db, feedback_id)
    main = db.get(Feedback, data.main_feedback_id)
    if not main or main.deleted_at or main.project_id != feedback.project_id:
        raise HTTPException(404, 'Main report not found in this project.')
    pending = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == main.id))
    if pending and pending.stage != 'submitted':
        raise HTTPException(404, 'Main report not found in this project.')
    if main.id == feedback.id:
        raise HTTPException(422, 'A report cannot be its own duplicate.')
    if group_for(db, feedback_id):
        raise HTTPException(409, 'Unlink this report before linking it to another main report.')
    group = group_for(db, main.id)
    if group and group.main_feedback_id != main.id:
        raise HTTPException(409, 'Choose the main report, not one of its duplicates.')
    try:
        if not group:
            if data.version != 0:
                raise conflict()
            group = DuplicateGroup(main_feedback_id=main.id, version=0)
            db.add(group); db.flush()
            db.add(DuplicateMember(feedback_id=main.id, group_id=group.id)); db.flush()
        lock_group(db, group, data.version)
        count = db.scalar(select(func.count()).select_from(DuplicateMember).where(DuplicateMember.group_id == group.id))
        if count >= MAX_MEMBERS:
            raise HTTPException(422, f'A shared issue can contain at most {MAX_MEMBERS} reports.')
        db.add(DuplicateMember(feedback_id=feedback_id, group_id=group.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict()
    db.expire_all()
    return snapshot(db, feedback_id)


@router.delete('/{feedback_id}/duplicates')
async def unlink(feedback_id: str, data: GroupVersion, db: Session = Depends(get_db)):
    visible_feedback(db, feedback_id)
    group = group_for(db, feedback_id)
    if not group:
        raise conflict()
    lock_group(db, group, data.version)
    if feedback_id == group.main_feedback_id:
        remove_group(db, group.id)
    else:
        db.execute(delete(DuplicateMember).where(DuplicateMember.feedback_id == feedback_id))
        if db.scalar(select(func.count()).select_from(DuplicateMember).where(DuplicateMember.group_id == group.id)) < 2:
            remove_group(db, group.id)
    db.commit()
    db.expire_all()
    return snapshot(db, feedback_id)


class SharedAction(GroupVersion):
    request_id: UUID


class SharedMessage(SharedAction):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator('body')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Write a customer-safe update first.')
        return value.strip()


class SharedWorkflow(SharedAction):
    report_versions: dict[str, int] = Field(max_length=MAX_MEMBERS)
    status: Literal['in_progress', 'ready_to_retest']
    assigned_employee_id: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=1000)
    _nonblank = field_validator('note')(SharedMessage.nonblank.__func__)


def action_context(db, feedback_id, data, kind):
    feedback = visible_feedback(db, feedback_id)
    group = group_for(db, feedback_id)
    if not group or group.main_feedback_id != feedback_id:
        raise HTTPException(409, 'Open the main report to manage this shared issue.')
    fingerprint = hashlib.sha256(json.dumps({'kind': kind, 'data': data.model_dump(mode='json')}, sort_keys=True).encode()).hexdigest()
    receipt = db.get(DuplicateAction, str(data.request_id))
    if receipt:
        if receipt.group_id != group.id or receipt.fingerprint != fingerprint:
            raise HTTPException(409, 'This request identifier was already used for a different update.')
        return feedback, group, fingerprint, receipt.count
    if group.version != data.version:
        raise conflict()
    return feedback, group, fingerprint, None


def finish_action(db, feedback_id, group, data, fingerprint, count):
    db.add(DuplicateAction(id=str(data.request_id), group_id=group.id, fingerprint=fingerprint, count=count))
    db.commit()
    db.expire_all()
    return {**snapshot(db, feedback_id), 'updated_count': count}


@router.post('/{feedback_id}/duplicates/updates')
async def share_update(feedback_id: str, data: SharedMessage, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    throttle(request, 'shared-update', 20)
    feedback, group, fingerprint, previous_count = action_context(db, feedback_id, data, 'message')
    if previous_count is not None:
        return {**snapshot(db, feedback_id), 'updated_count': previous_count}
    lock_group(db, group, data.version)
    actor = current_employee(request, db)
    rows = members(db, group)
    for row in rows:
        db.add(ReportMessage(feedback_id=row.id, visibility='public', author_role='company',
            author_name=actor.name if actor else 'Workspace owner', body=data.body))
        emit(db, request, row, 'company_reply', 'Company replied', company=True, customer=True)
    result = finish_action(db, feedback_id, group, data, fingerprint, len(rows))
    background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    return result


@router.post('/{feedback_id}/duplicates/workflow')
async def shared_workflow(feedback_id: str, data: SharedWorkflow, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    throttle(request, 'shared-workflow', 20)
    feedback, group, fingerprint, previous_count = action_context(db, feedback_id, data, 'workflow')
    if previous_count is not None:
        return {**snapshot(db, feedback_id), 'updated_count': previous_count}
    rows = members(db, group)
    if set(data.report_versions) != {row.id for row in rows}:
        raise conflict()
    employee = db.get(EmployeeAccount, data.assigned_employee_id)
    if not employee or employee.disabled_at or not db.get(EmployeeProject, (employee.id, feedback.project_id)):
        raise HTTPException(422, 'Choose an active employee who belongs to this project.')
    main_progress = db.get(IssueProgress, feedback_id)
    if data.status == 'ready_to_retest' and group.work_status not in ('in_progress', 'ready_to_retest') and (not main_progress or main_progress.status not in ('in_progress', 'ready_to_retest')):
        raise HTTPException(422, 'Start work on the main report before requesting a shared retest.')
    lock_group(db, group, data.version, work_status=data.status, assigned_employee_id=employee.id)
    stamp, count = now(), 0
    actor = current_employee(request, db)
    try:
        for row in rows:
            current = db.get(IssueProgress, row.id)
            version = current.version if current else 0
            if data.report_versions[row.id] != version:
                raise conflict()
            # One customer's confirmation never resolves or reopens someone else's report.
            if current and current.status == 'resolved':
                continue
            previous_employee = current.assigned_employee_id if current else None
            values = dict(status=data.status, assigned_employee_id=employee.id, version=version + 1, updated_at=stamp)
            if current:
                changed = db.execute(update(IssueProgress).where(IssueProgress.feedback_id == row.id,
                    IssueProgress.version == version).values(**values))
                if changed.rowcount != 1:
                    raise conflict()
            else:
                db.add(IssueProgress(feedback_id=row.id, **values)); db.flush()
                db.add(IssueEvent(feedback_id=row.id, label='Report received', note='', created_at=received_at(db, row)))
            db.add(IssueEvent(feedback_id=row.id, label='Status changed to ' + LABELS[data.status], note=data.note, created_at=stamp))
            emit(db, request, row, 'retest_requested' if data.status == 'ready_to_retest' else 'progress_update',
                'A fix is ready to retest' if data.status == 'ready_to_retest' else 'Report progress updated', customer=True)
            if previous_employee != employee.id and (actor is None or actor.id != employee.id):
                add_alert(db, row, 'employee', employee.id, 'assigned', 'An issue was assigned to you')
            count += 1
        if count == 0:
            raise HTTPException(409, 'All linked reports are resolved. Reopen the relevant report individually before sharing more work.')
        result = finish_action(db, feedback_id, group, data, fingerprint, count)
    except IntegrityError:
        db.rollback()
        raise conflict()
    background_tasks.add_task(deliver_pending, request.app.state.session_factory)
    return result
