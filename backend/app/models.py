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
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2000), default='')
    created_at: Mapped[str] = mapped_column(String, default=now)

class Feedback(Base):
    __tablename__ = 'feedback'
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
    __table_args__ = (UniqueConstraint('link_id', 'client_nonce'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    link_id: Mapped[str] = mapped_column(ForeignKey('intake_links.id'), index=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'), unique=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey('customer_accounts.id'), nullable=True, index=True)
    access_token: Mapped[str] = mapped_column(String, unique=True)
    client_nonce: Mapped[str] = mapped_column(String)
    reporter_name: Mapped[str] = mapped_column(String(80), default='')
    context: Mapped[dict] = mapped_column(JSON, default=dict)
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
    created_at: Mapped[str] = mapped_column(String, default=now)


class CustomerSession(Base):
    __tablename__ = 'customer_sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('customer_accounts.id'), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class CustomerMembership(Base):
    __tablename__ = 'customer_memberships'
    __table_args__ = (UniqueConstraint('account_id', 'project_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('customer_accounts.id'), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    link_id: Mapped[str] = mapped_column(ForeignKey('intake_links.id'))
    created_at: Mapped[str] = mapped_column(String, default=now)
