"""Reply screenshots share a message's access rules; they are never report-generation evidence."""
import base64
import binascii
import hashlib
import json
from contextlib import suppress
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import HTTPException, Response
from pydantic import Field
from sqlalchemy import select, func
from .schemas import StrictModel
from .models import MessageAttachment, ReportMessage, now
from .evidence import normalize_image, MAX_BYTES

MAX_IMAGES = 3
MAX_REPORT_IMAGES = 30
MAX_BASE64 = ((MAX_BYTES + 2) // 3) * 4
MAX_REPLY_BODY = 9 * 1024 * 1024


class ReplyImage(StrictModel):
    filename: str = Field(min_length=1, max_length=200)
    mime_type: Literal['image/png', 'image/jpeg']
    content_base64: str = Field(min_length=1, max_length=MAX_BASE64)
    caption: str = Field(default='', max_length=500)
    reviewed: Literal[True]


def image_metadata(image):
    return {key: getattr(image, key) for key in ('id', 'filename', 'caption', 'mime_type', 'size', 'width', 'height')}


def message_images(db, message_id):
    return [image_metadata(image) for image in db.scalars(select(MessageAttachment).where(
        MessageAttachment.message_id == message_id).order_by(MessageAttachment.id)).all()]


def fingerprint(data):
    # Only a fingerprint is persisted for retry detection, never the base64 payload.
    return hashlib.sha256(json.dumps(data.model_dump(mode='json', exclude={'request_id'}), sort_keys=True).encode()).hexdigest()


def prior_message(db, data, feedback_id, actor):
    if not data.request_id:
        return False
    previous = db.scalar(select(ReportMessage).where(ReportMessage.request_id == str(data.request_id)))
    if previous:
        if previous.feedback_id != feedback_id or previous.request_actor != actor or previous.request_fingerprint != fingerprint(data):
            raise HTTPException(409, 'This reply request was already used. Edit the reply before sending it as a new message.')
        return True
    return False


def save_reply(db, request, data, feedback_id, actor, role, name, notify):
    """Commit the message, normalized files, metadata and notifications together."""
    count = db.scalar(select(func.count()).select_from(MessageAttachment).join(ReportMessage,
        ReportMessage.id == MessageAttachment.message_id).where(ReportMessage.feedback_id == feedback_id))
    if count + len(data.attachments) > MAX_REPORT_IMAGES:
        raise HTTPException(409, 'This report has reached its reply screenshot storage limit. Contact the team before adding more images.')
    prepared = []
    for image in data.attachments:
        try:
            raw = base64.b64decode(image.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, 'Screenshot data is invalid. Review the image again.')
        clean, width, height = normalize_image(raw, image.mime_type)
        name_clean = Path(image.filename.replace('\\', '/')).name
        name_clean = ''.join(c for c in name_clean if c.isprintable())[:150] or 'screenshot.png'
        image_id = str(uuid4())
        key = 'reply-' + image_id + ('.png' if image.mime_type == 'image/png' else '.jpg')
        prepared.append((image, image_id, key, name_clean, clean, width, height))
    keys = []
    try:
        message = ReportMessage(feedback_id=feedback_id, visibility=data.visibility, author_role=role,
            author_name=name, body=data.body, request_id=str(data.request_id) if data.request_id else None,
            request_actor=actor if data.request_id else None, request_fingerprint=fingerprint(data) if data.request_id else None)
        db.add(message); db.flush()
        for image, image_id, key, filename, clean, width, height in prepared:
            keys.append(key)
            request.app.state.storage.put(key, clean)
            db.add(MessageAttachment(id=image_id, message_id=message.id, filename=filename, caption=image.caption.strip(),
                storage_key=key, mime_type=image.mime_type, size=len(clean), width=width, height=height,
                sha256=hashlib.sha256(clean).hexdigest(), reviewed_at=now()))
        notify()
        db.commit()
    except Exception:
        db.rollback()
        for key in keys:
            with suppress(OSError):
                request.app.state.storage.delete(key)
        raise


def image_content(db, request, feedback_id, message_id, image_id, public=False):
    query = select(MessageAttachment).join(ReportMessage, ReportMessage.id == MessageAttachment.message_id).where(
        MessageAttachment.id == image_id, ReportMessage.id == message_id, ReportMessage.feedback_id == feedback_id)
    if public:
        query = query.where(ReportMessage.visibility == 'public')
    image = db.scalar(query)
    if not image:
        raise HTTPException(404, 'Reply screenshot not found.')
    try:
        content = request.app.state.storage.get(image.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, 'Reply screenshot file is missing. Contact the team.')
    return Response(content, media_type=image.mime_type, headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'})
