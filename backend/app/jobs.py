"""One shared job boundary for report and vision calls. No automatic retry."""
import time
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from .config import settings
from .models import AIJob, now
from .providers.base import ProviderError

def day():
    return datetime.now(timezone.utc).date().isoformat()

def usage(db):
    jobs = db.scalars(select(AIJob).where(AIJob.day == day())).all()
    return {'attempts': len(jobs), 'limit': settings.ai_daily_limit,
            'paused': any(j.outcome == 'quota' for j in jobs),
            'input_tokens': sum(j.input_tokens for j in jobs),
            'output_tokens': sum(j.output_tokens for j in jobs),
            'successful': sum(j.outcome == 'success' and j.kind == 'report' for j in jobs),
            'vision_successful': sum(j.outcome == 'success' and j.kind == 'vision' for j in jobs),
            'average_latency_ms': round(sum(j.latency_ms for j in jobs) / len(jobs)) if jobs else 0,
            'resets': '00:00 UTC'}

def ensure_idle(app, feedback_id=None):
    active = getattr(app.state, 'active_feedback_id', None)
    if app.state.job_lock.locked() and (feedback_id is None or active is None or feedback_id == active):
        raise HTTPException(409, 'Wait for the current processing job to finish before changing evidence or reports.')

def evidence_changed(item):
    item.version += 1
    item.updated_at = now()
    item.status = 'draft'
    item.proposal = None
    item.error = None

async def run_job(app, db, item, kind, operation, on_success, error_target=None, before_reserve=None):
    if not settings.gemini_api_key:
        raise HTTPException(503, 'Add GEMINI_API_KEY to backend/.env and restart. Your feedback is saved.')
    if not settings.free_tier_confirmed:
        raise HTTPException(503, 'Confirm billing is disabled and set FREE_TIER_CONFIRMED=true. Your feedback is saved.')
    ensure_idle(app)
    async with app.state.job_lock:
        current = usage(db)
        if current['paused'] or current['attempts'] >= settings.ai_daily_limit:
            raise HTTPException(429, 'Processing is paused until 00:00 UTC. Your feedback, screenshots and edits are safe.')
        if before_reserve is not None:
            before_reserve()
        job = AIJob(feedback_id=item.id, day=day(), model=settings.gemini_model, kind=kind)
        db.add(job)
        db.commit()
        app.state.active_feedback_id = item.id
        start = time.monotonic()
        try:
            result = await operation()
            on_success(result)
            item.error = None
            if error_target is not None:
                error_target.error = None
            job.outcome = 'success'
            job.input_tokens, job.output_tokens = result.input_tokens, result.output_tokens
        except ProviderError as exc:
            job.outcome = exc.code
            item.error = exc.message
            if error_target is not None:
                error_target.error = exc.message
            job.latency_ms = (time.monotonic() - start) * 1000
            db.commit()
            raise HTTPException(exc.status, exc.message)
        finally:
            app.state.active_feedback_id = None
            job.latency_ms = (time.monotonic() - start) * 1000
        db.commit()
