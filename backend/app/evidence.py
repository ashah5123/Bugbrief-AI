"""Bounded, local screenshot storage and append-only user clarification evidence."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import get_db
from .models import Attachment, Clarification, Feedback, CustomerSubmission, now
from .schemas import ClarificationIn, GenerateIn
from .jobs import ensure_idle, evidence_changed, run_job
from .workflow import progress_snapshot

router = APIRouter(prefix='/api/feedback')
MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 4_000_000
MAX_ATTACHMENTS = 3

def get_feedback(db, feedback_id):
    item = db.get(Feedback, feedback_id)
    if item is None or item.deleted_at is not None:
        raise HTTPException(404, 'Feedback not found')
    return item

def attachments(db, feedback_id):
    return db.scalars(select(Attachment).where(Attachment.feedback_id == feedback_id, Attachment.deleted_at.is_(None)).order_by(Attachment.created_at)).all()

def clarifications(db, feedback_id):
    return db.scalars(select(Clarification).where(Clarification.feedback_id == feedback_id).order_by(Clarification.created_at)).all()

def serialize(item, db=None):
    result = {c.name: getattr(item, c.name) for c in item.__table__.columns if c.name != 'storage_key'}
    if isinstance(item, Feedback) and db is not None:
        from .duplicates import group_summary
        result['duplicate_group'] = group_summary(db, item.id)
        result['workflow'] = progress_snapshot(db, item)
        result['attachments'] = [serialize(a) for a in attachments(db, item.id)]
        result['clarifications'] = [serialize(c) for c in clarifications(db, item.id)]
        customer = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == item.id))
        result['customer'] = {'id': customer.account_id or customer.id, 'reporter_name': customer.reporter_name, 'stage': customer.stage, 'context': customer.context, 'submitted_at': customer.submitted_at} if customer else None
    return result

def report_evidence(db, item):
    evidence = {'feedback': item.text, 'page_url': item.page_url, 'device': item.device, 'browser': item.browser}
    customer = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == item.id))
    if customer and customer.context:
        import json
        qualifier = 'Customer confirmed this is the issue browser.' if customer.context.get('same_browser_confirmed') else 'Captured in the submission browser only; NOT confirmed as the issue browser or original issue viewport.'
        evidence['captured_context'] = qualifier + ' ' + json.dumps(customer.context, ensure_ascii=False)
    for answer in clarifications(db, item.id):
        evidence[f'clarification:{answer.id}'] = answer.answer
        evidence[f'question_context:{answer.id}'] = answer.question
    images = attachments(db, item.id)
    if any(image.analysis is None for image in images):
        raise HTTPException(409, 'Analyze or delete each screenshot before generating a report. Screenshots are never sent automatically.')
    for image in images:
        for index, observation in enumerate(image.analysis['observations']):
            evidence[f'screenshot:{image.id}:{index}'] = observation['description']
        evidence[f'image_limitations:{image.id}'] = '\n'.join(image.analysis['limitations'])
    if not item.text.strip() and not any(key.startswith(('clarification:', 'screenshot:')) for key in evidence):
        raise HTTPException(400, 'Add written feedback, a clarification answer, or an analyzed screenshot with visible observations first.')
    return evidence

def normalize_image(content, mime_type):
    formats = {'image/png': 'PNG', 'image/jpeg': 'JPEG'}
    if mime_type not in formats:
        raise HTTPException(415, 'Only PNG and JPEG screenshots are supported.')
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(413, 'Screenshots must be nonempty and no larger than 2 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != formats[mime_type] or getattr(image, 'n_frames', 1) != 1:
                    raise HTTPException(415, 'Image contents must match the PNG/JPEG type. Animated images are not accepted.')
                if image.width * image.height > MAX_PIXELS or image.width < 1 or image.height < 1:
                    raise HTTPException(413, 'Screenshots must contain no more than 4 megapixels. Resize or crop the image first.')
                image.load()
                clean = ImageOps.exif_transpose(image).convert('RGBA')
                # New pixel-only image drops EXIF, comments and other metadata.
                pixels = Image.new('RGB', clean.size, 'white')
                pixels.paste(clean, mask=clean.getchannel('A'))
                output = BytesIO()
                pixels.save(output, format=formats[mime_type], **({'quality': 90} if mime_type == 'image/jpeg' else {}))
                result = output.getvalue()
                if len(result) > MAX_BYTES:
                    raise HTTPException(413, 'The normalized image exceeds 2 MiB. Resize or redact a smaller crop.')
                return result, pixels.width, pixels.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(415, 'This screenshot is corrupt, unsafe to decode, or not a supported image.')

def get_attachment(db, feedback_id, attachment_id):
    get_feedback(db, feedback_id)
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.feedback_id != feedback_id or attachment.deleted_at is not None:
        raise HTTPException(404, 'Screenshot not found')
    return attachment

@router.get('/{feedback_id}')
def detail(feedback_id: str, db: Session = Depends(get_db)):
    return serialize(get_feedback(db, feedback_id), db)

@router.post('/{feedback_id}/attachments', status_code=201)
async def upload(feedback_id: str, request: Request, filename: str = 'screenshot.png', reviewed: bool = False, db: Session = Depends(get_db)):
    content = await request.body()
    item = get_feedback(db, feedback_id)
    ensure_idle(request.app, feedback_id)
    if not reviewed:
        raise HTTPException(400, 'Review and redact the screenshot before saving it. Explicit review confirmation is required.')
    if len(attachments(db, feedback_id)) >= MAX_ATTACHMENTS:
        raise HTTPException(409, 'Maximum three screenshots per feedback item. Delete one before adding another.')
    mime_type = request.headers.get('content-type', '').split(';')[0].lower()
    clean, width, height = normalize_image(content, mime_type)
    attachment_id = str(uuid4())
    key = attachment_id + ('.png' if mime_type == 'image/png' else '.jpg')
    safe_name = Path(filename.replace('\\', '/')).name
    safe_name = ''.join(c for c in safe_name if c.isprintable())[:150] or 'screenshot.png'
    attachment = Attachment(id=attachment_id, feedback_id=feedback_id, filename=safe_name, storage_key=key,
                            mime_type=mime_type, size=len(clean), width=width, height=height,
                            sha256=sha256(clean).hexdigest(), reviewed_at=now())
    try:
        request.app.state.storage.put(key, clean)
        db.add(attachment)
        evidence_changed(item)
        db.commit()
    except Exception:
        db.rollback()
        request.app.state.storage.delete(key)
        raise
    return serialize(item, db)

@router.get('/{feedback_id}/attachments/{attachment_id}/content')
def content(feedback_id: str, attachment_id: str, request: Request, db: Session = Depends(get_db)):
    image = get_attachment(db, feedback_id, attachment_id)
    try:
        content = request.app.state.storage.get(image.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, 'Screenshot file is missing. Restore the attachment backup or delete this entry.')
    return Response(content, media_type=image.mime_type, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'})

@router.delete('/{feedback_id}/attachments/{attachment_id}')
async def delete(feedback_id: str, attachment_id: str, request: Request, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    image = get_attachment(db, feedback_id, attachment_id)
    ensure_idle(request.app, feedback_id)
    request.app.state.storage.delete(image.storage_key)
    image.deleted_at = now()  # Tombstone preserves old report provenance; bytes are removed.
    image.analysis = None
    image.error = None
    evidence_changed(item)
    db.commit()
    return serialize(item, db)

@router.post('/{feedback_id}/attachments/{attachment_id}/analyze')
async def analyze(feedback_id: str, attachment_id: str, data: GenerateIn, request: Request, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    image = get_attachment(db, feedback_id, attachment_id)
    if not data.consent or not image.reviewed_at:
        raise HTTPException(400, 'Confirm that this reviewed screenshot can be sent to the hosted vision provider.')
    if image.analysis is not None:
        raise HTTPException(409, 'This screenshot already has observations. Add a new reviewed screenshot to preserve existing evidence references.')
    try:
        content = request.app.state.storage.get(image.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, 'Screenshot file is missing; nothing was sent.')
    def save(result):
        image.analysis = result.analysis.model_dump()
        image.analyzed_at = now()
        evidence_changed(item)
    await run_job(request.app, db, item, 'vision', lambda: request.app.state.image_analyzer.analyze(content, image.mime_type), save, image)
    return serialize(item, db)

@router.post('/{feedback_id}/clarifications', status_code=201)
async def answer(feedback_id: str, data: ClarificationIn, request: Request, db: Session = Depends(get_db)):
    item = get_feedback(db, feedback_id)
    ensure_idle(request.app, feedback_id)
    count = db.scalar(select(func.count()).select_from(Clarification).where(Clarification.feedback_id == feedback_id))
    if count >= 20:
        raise HTTPException(409, 'Maximum 20 clarification entries per feedback item.')
    db.add(Clarification(feedback_id=feedback_id, **data.model_dump()))
    evidence_changed(item)
    db.commit()
    return serialize(item, db)
