from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, JSON, ForeignKey, Integer, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc).isoformat()

class Project(Base):
    __tablename__ = 'projects'
    team_name: Mapped[str] = mapped_column(String(100), default='', server_default='')
    customer_access: Mapped[str] = mapped_column(String, default='link', server_default='link')
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2000), default='')
    created_at: Mapped[str] = mapped_column(String, default=now)

class Feedback(Base):
    __tablename__ = 'feedback'
    archived_at: Mapped[str | None] = mapped_column(String, nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    text: Mapped[str] = mapped_column(Text)
    page_url: Mapped[str] = mapped_column(String(2000), default='')
    device: Mapped[str] = mapped_column(String(200), default='')
    browser: Mapped[str] = mapped_column(String(200), default='')
    status: Mapped[str] = mapped_column(String, default='draft')
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)

class AIJob(Base):
    __tablename__ = 'ai_jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'))
    day: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, default='report', server_default='report')
    outcome: Mapped[str] = mapped_column(String, default='started')
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String)

class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), index=True)
    filename: Mapped[str] = mapped_column(String(150))
    storage_key: Mapped[str] = mapped_column(String)
    mime_type: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    reviewed_at: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analyzed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)

class Clarification(Base):
    __tablename__ = 'clarifications'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), index=True)
    question: Mapped[str] = mapped_column(String(500))
    answer: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String, default=now)


class IntakeLink(Base):
    __tablename__ = 'intake_links'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)

class CustomerSubmission(Base):
    __tablename__ = 'customer_submissions'
    draft_version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    archived_at: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (UniqueConstraint('link_id', 'client_nonce'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    link_id: Mapped[str] = mapped_column(ForeignKey('intake_links.id'), index=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), unique=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey('customer_accounts.id'), nullable=True, index=True)
    access_token: Mapped[str] = mapped_column(String, unique=True)
    client_nonce: Mapped[str] = mapped_column(String)
    reporter_name: Mapped[str] = mapped_column(String(80), default='')
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    guided_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stage: Mapped[str] = mapped_column(String, default='draft')
    processing_started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(String, nullable=True)
    consented_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    submitted_at: Mapped[str | None] = mapped_column(String, nullable=True)


class CustomerAccount(Base):
    __tablename__ = 'customer_accounts'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String)
    email_verified_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class CustomerSession(Base):
    __tablename__ = 'customer_sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('customer_accounts.id'), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class CustomerMembership(Base):
    __tablename__ = 'customer_memberships'
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (UniqueConstraint('account_id', 'project_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('customer_accounts.id'), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    link_id: Mapped[str] = mapped_column(ForeignKey('intake_links.id'))
    created_at: Mapped[str] = mapped_column(String, default=now)


class EmployeeAccount(Base):
    __tablename__ = 'employee_accounts'
    disabled_at: Mapped[str | None] = mapped_column(String, nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String)
    email_verified_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class EmployeeSession(Base):
    __tablename__ = 'employee_sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('employee_accounts.id'), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class IssueProgress(Base):
    __tablename__ = 'issue_progress'
    fix_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retest_requested_at: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String, default='normal', server_default='normal')
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String, default='new')
    assigned_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employee_accounts.id'), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class IssueEvent(Base):
    __tablename__ = 'issue_events'
    actor_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    visibility: Mapped[str] = mapped_column(String, default='public', server_default='public')
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), index=True)
    label: Mapped[str] = mapped_column(String(250))
    note: Mapped[str] = mapped_column(String(1000), default='')
    created_at: Mapped[str] = mapped_column(String, default=now)


class ReportMessage(Base):
    __tablename__ = 'report_messages'
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    request_actor: Mapped[str | None] = mapped_column(String, nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), index=True)
    visibility: Mapped[str] = mapped_column(String)
    author_role: Mapped[str] = mapped_column(String)
    author_name: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[str] = mapped_column(String, default=now)


class AccountAction(Base):
    __tablename__ = 'account_actions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String(254))
    expires_at: Mapped[float] = mapped_column(Float)
    used_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class MailMessage(Base):
    __tablename__ = 'mail_messages'
    notification_id: Mapped[str | None] = mapped_column(ForeignKey('notifications.id'), nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)


class EmployeeProject(Base):
    __tablename__ = 'employee_projects'
    role: Mapped[str] = mapped_column(String, default='contributor', server_default='contributor')
    can_delete: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    employee_id: Mapped[str] = mapped_column(ForeignKey('employee_accounts.id'), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), primary_key=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class ProjectEvent(Base):
    __tablename__ = 'project_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    actor_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String, default=now)


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    scope: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    email_enabled: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Base):
    __tablename__ = 'notifications'
    reminder_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    reminder_episode: Mapped[str | None] = mapped_column(String, nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    scope: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), index=True)
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String, default=now)
    read_at: Mapped[str | None] = mapped_column(String, nullable=True)


class ReminderPolicy(Base):
    __tablename__ = 'reminder_policy'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    reply_hours: Mapped[int] = mapped_column(Integer, default=24)
    retest_hours: Mapped[int] = mapped_column(Integer, default=48)
    timezone: Mapped[str] = mapped_column(String(100), default='UTC')
    version: Mapped[int] = mapped_column(Integer, default=1)


class OwnerSession(Base):
    __tablename__ = 'owner_sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    credential_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[float] = mapped_column(Float)


class DuplicateGroup(Base):
    __tablename__ = 'duplicate_groups'
    work_status: Mapped[str] = mapped_column(String, default='new', server_default='new')
    assigned_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employee_accounts.id'), nullable=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    main_feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, default=now)


class DuplicateMember(Base):
    __tablename__ = 'duplicate_members'
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey('duplicate_groups.id'), index=True)
    created_at: Mapped[str] = mapped_column(String, default=now)


class DuplicateAction(Base):
    __tablename__ = 'duplicate_actions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey('duplicate_groups.id'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    count: Mapped[int] = mapped_column(Integer)


class MessageAttachment(Base):
    __tablename__ = 'message_attachments'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey('report_messages.id'), index=True)
    filename: Mapped[str] = mapped_column(String(150))
    caption: Mapped[str] = mapped_column(String(500), default='')
    storage_key: Mapped[str] = mapped_column(String, unique=True)
    mime_type: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    reviewed_at: Mapped[str] = mapped_column(String, default=now)
