"""Erase report content and evidence; retain minimal quota/idempotency tombstones."""
from sqlalchemy import select, delete
from .models import Attachment, Clarification, CustomerSubmission, now
from .jobs import ensure_idle


def erase_feedback(db, app, feedback):
    ensure_idle(app, feedback.id)
    # Remove files first: a storage error leaves a retryable, visible report.
    images = db.scalars(select(Attachment).where(Attachment.feedback_id == feedback.id)).all()
    for image in images:
        app.state.storage.delete(image.storage_key)
    db.execute(delete(Attachment).where(Attachment.feedback_id == feedback.id))
    db.execute(delete(Clarification).where(Clarification.feedback_id == feedback.id))
    customer = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == feedback.id))
    if customer:
        customer.reporter_name = ''
        customer.context = {}
        customer.stage = 'deleted'
        customer.processing_started_at = None
        customer.processing_error = None
        customer.consented_at = None
        customer.submitted_at = None
    feedback.text = ''
    feedback.page_url = ''
    feedback.device = ''
    feedback.browser = ''
    feedback.report = None
    feedback.proposal = None
    feedback.error = None
    feedback.status = 'deleted'
    feedback.deleted_at = now()
    feedback.updated_at = feedback.deleted_at
    feedback.version += 1
    db.commit()
    return {'deleted': True}
