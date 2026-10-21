"""One durable reminder per waiting episode and recipient, using existing alert permissions."""
import hashlib
import logging
from datetime import datetime, timezone, timedelta, date
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import select, update, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import ReminderPolicy, Notification, Feedback, CustomerSubmission, IssueProgress, IssueEvent
from .schemas import StrictModel
from .account_management import require_owner
from .workflow import waiting_since

router = APIRouter(prefix='/api/team/reminders')
_lock = Lock()
DEFAULTS = dict(enabled=True, reply_hours=24, retest_hours=48, timezone='UTC', version=0)


def policy_snapshot(db):
    row = db.get(ReminderPolicy, 1)
    return {key: (bool(getattr(row, key)) if key == 'enabled' else getattr(row, key)) for key in DEFAULTS} if row else dict(DEFAULTS)


class PolicyInput(StrictModel):
    enabled: bool
    reply_hours: int = Field(ge=1, le=720)
    retest_hours: int = Field(ge=1, le=720)
    timezone: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=0)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Choose a valid IANA timezone, such as America/Phoenix or UTC.')
        return value


@router.get('')
def get_policy(request: Request, db: Session = Depends(get_db)):
    require_owner(request)
    return policy_snapshot(db)


@router.patch('')
def save_policy(data: PolicyInput, request: Request, db: Session = Depends(get_db)):
    require_owner(request)
    current = policy_snapshot(db)
    if data.version != current['version']:
        raise HTTPException(409, 'Reminder settings changed. Reload settings before saving.')
    values = data.model_dump(exclude={'version'}) | {'enabled': int(data.enabled), 'version': data.version + 1}
    try:
        if current['version']:
            changed = db.execute(update(ReminderPolicy).where(ReminderPolicy.id == 1, ReminderPolicy.version == data.version).values(**values))
            if changed.rowcount != 1:
                raise HTTPException(409, 'Reminder settings changed. Reload settings before saving.')
        else:
            db.add(ReminderPolicy(id=1, **values))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Reminder settings changed. Reload settings before saving.')
    db.expire_all()
    return policy_snapshot(db)


def parse_stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def candidates(db, feedback, policy, stamp):
    """Return kind, recipient, episode, title only while the required action is outstanding."""
    if not policy['enabled'] or not feedback or feedback.deleted_at:
        return []
    submission = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
    if submission and submission.stage != 'submitted':
        return []
    progress = db.get(IssueProgress, feedback.id)
    status = progress.status if progress else 'new'
    if status == 'resolved':
        return []
    result = []
    waiting = waiting_since(db, feedback, status)
    waiting_at = parse_stamp(waiting)
    if waiting_at and stamp >= waiting_at + timedelta(hours=policy['reply_hours']):
        # Unassigned work goes to the owner rather than every project employee.
        scope, account = ('employee', progress.assigned_employee_id) if progress and progress.assigned_employee_id else ('owner', 'owner')
        result.append(('reminder_reply', scope, account, waiting, 'Reminder: a customer is waiting for a response'))
    try:
        due = date.fromisoformat(progress.due_date) if progress and progress.due_date else None
    except ValueError:
        due = None
    if due and due < stamp.astimezone(ZoneInfo(policy['timezone'])).date():
        result.append(('reminder_overdue', 'owner', 'owner', progress.due_date, 'Escalation: a report is past its deadline'))
    if progress and status == 'ready_to_retest' and submission and submission.account_id:
        requested = progress.retest_requested_at or db.scalar(select(func.max(IssueEvent.created_at)).where(
            IssueEvent.feedback_id == feedback.id, IssueEvent.visibility == 'public',
            IssueEvent.label == 'Status changed to Ready to retest')) or progress.updated_at
        requested_at = parse_stamp(requested)
        if requested_at and stamp >= requested_at + timedelta(hours=policy['retest_hours']):
            result.append(('reminder_retest', 'customer', submission.account_id, requested, 'Reminder: a fix is waiting for your retest'))
    return result


def reminder_is_current(db, alert, feedback, stamp=None):
    if not alert.kind.startswith('reminder_'):
        return True
    stamp = stamp or datetime.now(timezone.utc)
    return any((kind, scope, account, episode) == (alert.kind, alert.scope, alert.account_id, alert.reminder_episode)
               for kind, scope, account, episode, _ in candidates(db, feedback, policy_snapshot(db), stamp))


def run_reminders(factory, stamp=None):
    if not _lock.acquire(blocking=False):
        return
    try:
        stamp = stamp or datetime.now(timezone.utc)
        with factory() as db:
            policy = policy_snapshot(db)
            if not policy['enabled']:
                return
            # Existing local-workspace limits apply; load IDs, then each report on demand.
            ids = db.scalars(select(Feedback.id).where(Feedback.deleted_at.is_(None))).all()
            from .notifications import add_alert, can_view
            for feedback_id in ids:
                feedback = db.get(Feedback, feedback_id)
                for kind, scope, account, episode, title in candidates(db, feedback, policy, stamp):
                    if not can_view(db, scope, account, feedback):
                        continue
                    key = hashlib.sha256(f'{feedback_id}|{kind}|{scope}|{account}|{episode}'.encode()).hexdigest()
                    if db.scalar(select(Notification.id).where(Notification.reminder_key == key)):
                        continue
                    try:
                        with db.begin_nested():
                            add_alert(db, feedback, scope, account, kind, title, reminder_key=key, reminder_episode=episode)
                    except IntegrityError:
                        # A database uniqueness guard also protects restart/concurrent scans.
                        continue
                db.commit()
    except SQLAlchemyError:
        logging.getLogger(__name__).warning('Reminder scan paused; outstanding work will be checked again.')
    finally:
        _lock.release()
