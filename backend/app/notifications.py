"""Account-specific alerts, filtered by current report access on every read/delivery."""
from typing import Literal
from threading import Lock
import logging
from sqlalchemy.exc import SQLAlchemyError
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from .db import get_db
from .models import (Notification, NotificationPreference, EmployeeAccount, EmployeeProject,
                     CustomerAccount, CustomerSubmission, Feedback, MailMessage, now)
from .schemas import StrictModel
from .config import settings
from .auth import owner_allowed
from .employee_auth import current_employee
from .customer_auth import current_customer
from .project_access import customer_can_access, employee_has_project
from .account_management import deliver_mail

router = APIRouter(prefix='/api/auth/notifications')
_delivery_lock = Lock()


def identity(request, db, audience):
    if audience == 'customer':
        account = current_customer(request, db)
        if account:
            return 'customer', account.id, account
    else:
        if owner_allowed(request):
            return 'owner', 'owner', None
        account = current_employee(request, db)
        if account:
            return 'employee', account.id, account
    raise HTTPException(401, 'Sign in to see your notifications.')


def can_view(db, scope, account_id, feedback):
    if not feedback or feedback.deleted_at:
        return False
    if scope == 'owner':
        return True
    if scope == 'employee':
        employee = db.get(EmployeeAccount, account_id)
        return bool(employee and not employee.disabled_at and employee_has_project(db, account_id, feedback.project_id))
    item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id,
        CustomerSubmission.account_id == account_id, CustomerSubmission.stage == 'submitted'))
    return bool(item and customer_can_access(db, account_id, feedback.project_id))


def visible_notifications(db, scope, account_id):
    # Filter in SQL so unread counts and pagination never reveal inaccessible reports.
    query = select(Notification).join(Feedback, Feedback.id == Notification.feedback_id).where(
        Notification.scope == scope, Notification.account_id == account_id, Feedback.deleted_at.is_(None))
    if scope == 'employee':
        query = query.where(Feedback.project_id.in_(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == account_id)))
    elif scope == 'customer':
        from .models import CustomerMembership, Project
        allowed = select(CustomerMembership.project_id).where(CustomerMembership.account_id == account_id,
            CustomerMembership.revoked_at.is_(None))
        revoked = select(CustomerMembership.project_id).where(CustomerMembership.account_id == account_id,
            CustomerMembership.revoked_at.is_not(None))
        account = db.get(CustomerAccount, account_id)
        verified = bool(account and account.email_verified_at)
        query = query.join(CustomerSubmission, CustomerSubmission.feedback_id == Feedback.id).join(Project, Project.id == Feedback.project_id).where(
            CustomerSubmission.account_id == account_id, CustomerSubmission.stage == 'submitted',
            Feedback.project_id.not_in(revoked), (Project.customer_access == 'link') | (Feedback.project_id.in_(allowed) & verified))
    return query


def add_alert(db, feedback, scope, account_id, kind, title):
    if not can_view(db, scope, account_id, feedback):
        return
    alert = Notification(scope=scope, account_id=account_id, feedback_id=feedback.id, kind=kind,
                         title=title + ' · BB-' + feedback.id[:8].upper())
    db.add(alert)
    db.flush()
    preference = db.get(NotificationPreference, (scope, account_id))
    if not preference or not preference.email_enabled or scope == 'owner':
        return
    model = CustomerAccount if scope == 'customer' else EmployeeAccount
    account = db.get(model, account_id)
    if settings.mail_mode != 'local' and not account.email_verified_at:
        return
    if scope == 'customer':
        item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
        path = '/s/' + item.access_token
    else:
        path = '/workspace?report=' + feedback.id
    body = f'{alert.title}\n\nOpen your report:\n{settings.public_base_url.rstrip("/")}{path}\n\nSign in to view the details. Manage email alerts in your notification inbox.'
    db.add(MailMessage(notification_id=alert.id, recipient=account.email, subject=alert.title, body=body,
                       delivery='local' if settings.mail_mode == 'local' else 'pending'))


def emit(db, request, feedback, kind, title, company=False, customer=False):
    # All alerts commit with the action; exceptions/rollbacks cannot leave phantom alerts.
    actor = ('owner', 'owner') if owner_allowed(request) else None
    employee = current_employee(request, db)
    person = current_customer(request, db)
    # Explicit event side avoids a second signed-in role suppressing the intended recipient.
    if kind in ('customer_reply', 'retest_result', 'report_received'):
        actor = ('customer', person.id) if person else None
    elif employee and not actor:
        actor = ('employee', employee.id)
    recipients = set()
    if company:
        recipients.add(('owner', 'owner'))
        recipients.update(('employee', employee_id) for employee_id in db.scalars(select(EmployeeProject.employee_id).where(
            EmployeeProject.project_id == feedback.project_id)).all())
    if customer:
        item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id,
            CustomerSubmission.stage == 'submitted'))
        if item and item.account_id:
            recipients.add(('customer', item.account_id))
    for scope, account_id in recipients:
        if (scope, account_id) != actor:
            add_alert(db, feedback, scope, account_id, kind, title)


def deliver_pending(factory):
    if not _delivery_lock.acquire(blocking=False):
        return
    try:
        _deliver_pending(factory)
    except SQLAlchemyError:
        # A transient database error must not stop the periodic worker or turn a committed reply into a failed request.
        logging.getLogger(__name__).warning('Notification email delivery paused; pending messages will be checked again.')
    finally:
        _delivery_lock.release()


def _deliver_pending(factory):
    # New transactions per message prevent cached permissions and deleted rows from surviving a slow send.
    with factory() as db:
        ids = list(db.scalars(select(MailMessage.id).where(MailMessage.notification_id.is_not(None),
            MailMessage.delivery == 'pending').order_by(MailMessage.created_at).limit(100)).all())
    for mail_id in ids:
        with factory() as db:
            mail = db.get(MailMessage, mail_id)
            if mail is None or mail.delivery != 'pending':
                continue
            alert = db.get(Notification, mail.notification_id)
            feedback = db.get(Feedback, alert.feedback_id) if alert else None
            preference = db.get(NotificationPreference, (alert.scope, alert.account_id)) if alert else None
            account = db.get(CustomerAccount if alert and alert.scope == 'customer' else EmployeeAccount, alert.account_id) if alert and alert.scope != 'owner' else None
            if not alert or not preference or not preference.email_enabled or not account or not account.email_verified_at or not can_view(db, alert.scope, alert.account_id, feedback):
                mail.delivery, mail.body = 'cancelled', ''
            elif settings.mail_mode == 'local':
                mail.delivery = 'local'
            else:
                deliver_mail(mail)
            db.commit()


@router.get('/{audience}')
def inbox(audience: Literal['company', 'customer'], request: Request, db: Session = Depends(get_db)):
    scope, account_id, account = identity(request, db, audience)
    query = visible_notifications(db, scope, account_id)
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(50)).all()
    unread = db.scalar(select(func.count()).select_from(query.where(Notification.read_at.is_(None)).subquery()))
    preference = db.get(NotificationPreference, (scope, account_id))
    items = []
    for row in rows:
        item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == row.feedback_id)) if scope == 'customer' else None
        items.append({'id': row.id, 'kind': row.kind, 'title': row.title, 'read_at': row.read_at,
            'created_at': row.created_at, 'url': '/s/' + item.access_token if item else '/workspace?report=' + row.feedback_id})
    return {'items': items, 'unread_count': unread, 'email_enabled': bool(preference and preference.email_enabled),
            'email_available': bool(account), 'email_verified': bool(account and account.email_verified_at), 'mail_mode': settings.mail_mode}


class PreferenceInput(StrictModel):
    email_enabled: bool


@router.patch('/{audience}/preferences')
def preferences(audience: Literal['company', 'customer'], data: PreferenceInput, request: Request, db: Session = Depends(get_db)):
    scope, account_id, account = identity(request, db, audience)
    if data.email_enabled and (not account or (settings.mail_mode != 'local' and not account.email_verified_at)):
        raise HTTPException(400, 'Sign in with an account and verify your email before enabling email alerts.')
    row = db.get(NotificationPreference, (scope, account_id))
    if not row:
        row = NotificationPreference(scope=scope, account_id=account_id)
        db.add(row)
    row.email_enabled = int(data.email_enabled)
    db.commit()
    return inbox(audience, request, db)


@router.post('/{audience}/read-all')
def read_all(audience: Literal['company', 'customer'], request: Request, db: Session = Depends(get_db)):
    scope, account_id, _ = identity(request, db, audience)
    ids = visible_notifications(db, scope, account_id).with_only_columns(Notification.id)
    db.execute(update(Notification).where(Notification.id.in_(ids), Notification.read_at.is_(None)).values(read_at=now()),
        execution_options={'synchronize_session': False})
    db.commit()
    return inbox(audience, request, db)


@router.post('/{audience}/{notification_id}/read')
def read_one(audience: Literal['company', 'customer'], notification_id: str, request: Request, db: Session = Depends(get_db)):
    scope, account_id, _ = identity(request, db, audience)
    row = db.get(Notification, notification_id)
    if not row or (row.scope, row.account_id) != (scope, account_id) or not can_view(db, scope, account_id, db.get(Feedback, row.feedback_id)):
        raise HTTPException(404, 'Notification not found.')
    if not row.read_at:
        row.read_at = now()
        db.commit()
    return inbox(audience, request, db)


class ReadReport(StrictModel):
    report: str


@router.post('/{audience}/read-report')
def read_report(audience: Literal['company', 'customer'], data: ReadReport, request: Request, db: Session = Depends(get_db)):
    scope, account_id, _ = identity(request, db, audience)
    if scope == 'customer':
        item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.access_token == data.report,
            CustomerSubmission.account_id == account_id))
        feedback = db.get(Feedback, item.feedback_id) if item else None
    else:
        feedback = db.get(Feedback, data.report)
    if not can_view(db, scope, account_id, feedback):
        raise HTTPException(404, 'Report not found.')
    changed = db.execute(update(Notification).where(Notification.scope == scope, Notification.account_id == account_id,
        Notification.feedback_id == feedback.id, Notification.read_at.is_(None)).values(read_at=now()))
    db.commit()
    return {'changed': bool(changed.rowcount)}
