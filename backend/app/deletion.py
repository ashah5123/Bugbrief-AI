"""Erase report content and evidence; retain minimal quota/idempotency tombstones."""
from sqlalchemy import select, delete
from .models import Attachment, Clarification, CustomerSubmission, IssueProgress, IssueEvent, ReportMessage, MessageAttachment, Notification, MailMessage, now
from .jobs import ensure_idle


def erase_feedback(db, app, feedback):
    ensure_idle(app, feedback.id)
    # Remove files first: a storage error leaves a retryable, visible report.
    images = db.scalars(select(Attachment).where(Attachment.feedback_id == feedback.id)).all()
    for image in images:
        app.state.storage.delete(image.storage_key)
    reply_images = db.scalars(select(MessageAttachment).join(ReportMessage, ReportMessage.id == MessageAttachment.message_id)
        .where(ReportMessage.feedback_id == feedback.id)).all()
    for image in reply_images:
        app.state.storage.delete(image.storage_key)
    db.execute(delete(MessageAttachment).where(MessageAttachment.message_id.in_(
        select(ReportMessage.id).where(ReportMessage.feedback_id == feedback.id))))
    db.execute(delete(Attachment).where(Attachment.feedback_id == feedback.id))
    db.execute(delete(Clarification).where(Clarification.feedback_id == feedback.id))
    notification_ids = select(Notification.id).where(Notification.feedback_id == feedback.id)
    db.execute(delete(MailMessage).where(MailMessage.notification_id.in_(notification_ids)))
    db.execute(delete(Notification).where(Notification.feedback_id == feedback.id))
    db.execute(delete(ReportMessage).where(ReportMessage.feedback_id == feedback.id))
    db.execute(delete(IssueEvent).where(IssueEvent.feedback_id == feedback.id))
    db.execute(delete(IssueProgress).where(IssueProgress.feedback_id == feedback.id))
    from .duplicates import detach_for_deletion
    detach_for_deletion(db, feedback.id)
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
