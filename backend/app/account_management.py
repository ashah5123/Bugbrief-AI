"""One-use security links and owner-controlled team access."""
import hashlib
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import (AccountAction, MailMessage, CustomerAccount, CustomerSession,
                     EmployeeAccount, EmployeeSession, IssueProgress, IssueEvent, now)
from .schemas import StrictModel
from .customer_auth import Credentials, current_customer, password_hash, throttle
from .employee_auth import current_employee
from .activity import actor_details, project_event

router = APIRouter()
ACK = {'message': 'If the account is eligible, a message will be sent. Check your inbox.'}


def require_owner(request: Request):
    from .auth import owner_allowed
    if not owner_allowed(request):
        raise HTTPException(403, 'Only the workspace owner can manage team access and test emails.')


def issue_action(db, scope, kind, email):
    # Issuing a replacement invalidates every older link of the same purpose.
    db.execute(update(AccountAction).where(AccountAction.scope == scope, AccountAction.kind == kind,
        AccountAction.email == email, AccountAction.used_at.is_(None)).values(used_at=now()))
    token = secrets.token_urlsafe(32)
    ttl = 7*86400 if kind == 'invite' else (86400 if kind == 'verify' else 3600)
    db.add(AccountAction(token_hash=hashlib.sha256(token.encode()).hexdigest(), scope=scope,
                         kind=kind, email=email, expires_at=time.time()+ttl))
    route = '/workspace/signup' if kind == 'invite' else '/account'
    url = settings.public_base_url.rstrip('/') + route + f'#{scope}/{kind}/{token}'
    subject = {'invite': 'Your BugBrief employee invitation', 'verify': 'Verify your BugBrief email',
               'reset': 'Reset your BugBrief password'}[kind]
    body = f'{subject}\n\nOpen this one-use link:\n{url}\n\nThis link expires in {ttl//3600} hours. If you did not request this, you can ignore it.'
    mail = MailMessage(recipient=email, subject=subject, body=body, delivery='local' if settings.mail_mode == 'local' else 'pending')
    db.add(mail)
    db.commit()
    deliver_mail(mail)
    db.commit()
    return mail


def deliver_mail(mail):
    email, subject, body = mail.recipient, mail.subject, mail.body
    if settings.mail_mode != 'local':
        # Never fall back to plaintext SMTP. Retain failures for an owner to retry by issuing a new link.
        try:
            if settings.mail_mode != 'smtp' or not settings.smtp_host or not settings.smtp_from:
                raise ValueError('Mail sender is not configured')
            message = EmailMessage()
            message['From'], message['To'], message['Subject'] = settings.smtp_from, email, subject
            message.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as sender:
                sender.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    sender.login(settings.smtp_username, settings.smtp_password)
                sender.send_message(message)
            mail.delivery = 'sent'
            # Production outbox retains delivery metadata, never reusable security links.
            mail.body = ''
        except (OSError, ValueError, smtplib.SMTPException):
            mail.delivery = 'failed'
            mail.body = ''
    return mail


def action_for(db, token, scope, kind):
    action = db.get(AccountAction, hashlib.sha256(token.encode()).hexdigest())
    if not action or action.scope != scope or action.kind != kind or action.used_at or action.expires_at <= time.time():
        raise HTTPException(400, 'This link is invalid, expired or already used. Request a new one.')
    return action


def consume_action(db, action):
    changed = db.execute(update(AccountAction).where(AccountAction.token_hash == action.token_hash,
        AccountAction.used_at.is_(None), AccountAction.expires_at > time.time()).values(used_at=now()))
    if changed.rowcount != 1:
        raise HTTPException(400, 'This link has already been used or expired.')


class EmailInput(StrictModel):
    email: str = Field(max_length=254)
    email_valid = field_validator('email')(Credentials.email_valid.__func__)


class FinishAction(StrictModel):
    token: SecretStr
    password: SecretStr | None = None


def model_for(scope):
    return CustomerAccount if scope == 'customer' else EmployeeAccount


@router.post('/api/auth/accounts/{scope}/recover')
def recover(scope: Literal['customer', 'employee'], data: EmailInput, request: Request, db: Session = Depends(get_db)):
    throttle(request, 'recover-' + scope, 5)
    model = model_for(scope)
    account = db.scalar(select(model).where(model.email == data.email))
    if account and not getattr(account, 'disabled_at', None):
        issue_action(db, scope, 'reset', account.email)
    return ACK


@router.post('/api/auth/accounts/{scope}/verification')
def request_verification(scope: Literal['customer', 'employee'], request: Request, db: Session = Depends(get_db)):
    throttle(request, 'verify-' + scope, 5)
    account = current_customer(request, db) if scope == 'customer' else current_employee(request, db)
    if not account:
        raise HTTPException(401, 'Sign in before verifying your email.')
    if not account.email_verified_at:
        issue_action(db, scope, 'verify', account.email)
    return ACK


@router.post('/api/auth/accounts/{scope}/{kind}/complete')
def complete(scope: Literal['customer', 'employee'], kind: Literal['reset', 'verify'], data: FinishAction,
             request: Request, db: Session = Depends(get_db)):
    throttle(request, 'complete-' + scope, 10)
    action = action_for(db, data.token.get_secret_value(), scope, kind)
    model = model_for(scope)
    account = db.scalar(select(model).where(model.email == action.email))
    if not account or getattr(account, 'disabled_at', None):
        raise HTTPException(400, 'This account is unavailable.')
    if kind == 'reset':
        password = data.password.get_secret_value() if data.password else ''
        if not 12 <= len(password) <= 128:
            raise HTTPException(400, 'Use a password between 12 and 128 characters.')
        digest = password_hash(password)
        consume_action(db, action)
        account.password_hash = digest
        sessions = CustomerSession if scope == 'customer' else EmployeeSession
        db.execute(delete(sessions).where(sessions.account_id == account.id))
    else:
        consume_action(db, action)
        if scope == 'customer' and not account.email_verified_at:
            from .models import CustomerMembership, Project, ProjectEvent
            project_ids = db.scalars(select(CustomerMembership.project_id).join(Project, Project.id == CustomerMembership.project_id)
                .where(CustomerMembership.account_id == account.id, CustomerMembership.revoked_at.is_(None), Project.customer_access == 'members')).all()
            for project_id in project_ids:
                db.add(ProjectEvent(project_id=project_id, actor_name=account.name, actor_role='customer',
                    label='Private invitation activated after email verification', note=account.name))
        account.email_verified_at = now()
    db.commit()
    return {'message': 'Password updated. Sign in with your new password.' if kind == 'reset' else 'Email verified. You can return to your account.'}


@router.get('/api/team')
def team(request: Request, db: Session = Depends(get_db)):
    from .auth import owner_allowed
    if not owner_allowed(request):
        return {'can_manage': False, 'employees': [], 'invitations': [], 'mail_mode': None}
    members = db.scalars(select(EmployeeAccount).order_by(EmployeeAccount.name)).all()
    invites = db.scalars(select(AccountAction).where(AccountAction.kind == 'invite', AccountAction.used_at.is_(None),
        AccountAction.expires_at > time.time()).order_by(AccountAction.created_at.desc())).all()
    return {'can_manage': True, 'mail_mode': settings.mail_mode,
        'employees': [{'id': m.id, 'name': m.name, 'email': m.email, 'disabled_at': m.disabled_at,
                       'email_verified': bool(m.email_verified_at)} for m in members],
        'invitations': [{'id': i.token_hash, 'email': i.email, 'expires_at': i.expires_at} for i in invites]}


@router.post('/api/team/invitations', status_code=201, dependencies=[Depends(require_owner)])
def invite(data: EmailInput, request: Request, db: Session = Depends(get_db)):
    throttle(request, 'invite', 20)
    if db.scalar(select(EmployeeAccount.id).where(EmployeeAccount.email == data.email)):
        raise HTTPException(409, 'This employee already has an account. Removed access must be restored by the owner.')
    mail = issue_action(db, 'employee', 'invite', data.email)
    return {'delivery': mail.delivery}


@router.delete('/api/team/invitations/{invitation_id}', dependencies=[Depends(require_owner)])
def revoke_invitation(invitation_id: str, db: Session = Depends(get_db)):
    action = db.get(AccountAction, invitation_id)
    if not action or action.kind != 'invite':
        raise HTTPException(404, 'Invitation not found.')
    action.used_at = now()
    db.commit()
    return {'revoked': True}


@router.delete('/api/team/employees/{employee_id}', dependencies=[Depends(require_owner)])
def remove_employee(employee_id: str, request: Request, db: Session = Depends(get_db)):
    employee = db.get(EmployeeAccount, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found.')
    if not employee.disabled_at:
        from .models import EmployeeProject
        for project_id in db.scalars(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == employee_id)):
            project_event(db, request, project_id, 'Employee workspace access removed', employee.name)
        employee.disabled_at = now()
        db.execute(delete(EmployeeSession).where(EmployeeSession.account_id == employee_id))
        db.execute(update(AccountAction).where(AccountAction.scope == 'employee', AccountAction.email == employee.email,
            AccountAction.used_at.is_(None)).values(used_at=now()))
        for progress in db.scalars(select(IssueProgress).where(IssueProgress.assigned_employee_id == employee_id)).all():
            progress.assigned_employee_id = None
            progress.version += 1
            progress.updated_at = now()
            db.add(IssueEvent(feedback_id=progress.feedback_id, label='Assignment removed', note='The team will assign a new employee.', **actor_details(request, db)))
    db.commit()
    return {'removed': True}


@router.post('/api/team/employees/{employee_id}/restore', dependencies=[Depends(require_owner)])
def restore_employee(employee_id: str, request: Request, db: Session = Depends(get_db)):
    employee = db.get(EmployeeAccount, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found.')
    if employee.disabled_at:
        from .models import EmployeeProject
        for project_id in db.scalars(select(EmployeeProject.project_id).where(EmployeeProject.employee_id == employee_id)):
            project_event(db, request, project_id, 'Employee workspace access restored', employee.name)
        employee.disabled_at = None
    db.commit()
    return {'restored': True}


@router.get('/api/team/outbox', dependencies=[Depends(require_owner)])
def outbox(db: Session = Depends(get_db)):
    return [{'id': m.id, 'recipient': m.recipient, 'subject': m.subject, 'body': m.body if settings.mail_mode == 'local' else '',
             'delivery': m.delivery, 'created_at': m.created_at} for m in db.scalars(
                 select(MailMessage).order_by(MailMessage.created_at.desc()).limit(50)).all()]
