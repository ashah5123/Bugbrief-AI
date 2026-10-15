from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, JSON, ForeignKey, Integer, Float
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

class AIJob(Base):
    __tablename__ = 'ai_jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedback.id'))
    day: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String, default='started')
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String)
