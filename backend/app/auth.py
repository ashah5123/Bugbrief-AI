"""Single-agency development access; customer capabilities are separate."""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from sqlalchemy.orm import Session
from .db import get_db
from .employee_auth import current_employee, end_employee_session, profile, COOKIE as EMPLOYEE_COOKIE
from pydantic import BaseModel, Field
from .config import settings

router = APIRouter(prefix='/api/auth')
COOKIE = 'bugbrief_agency'
LOGIN_WINDOW = 600
_failures = {}

def access_code():
    if settings.agency_access_code:
        return settings.agency_access_code
    path = settings.agency_code_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as file:
                file.write(secrets.token_urlsafe(24) + '\n')
        except FileExistsError:
            pass
    code = path.read_text().strip()
    if len(code) < 16:
        raise RuntimeError('The local workspace access code must contain at least 16 characters. Restore or regenerate the access-code file.')
    return code

def signed_session():
    payload = base64.urlsafe_b64encode(json.dumps({'expires': int(time.time()) + 43200, 'nonce': secrets.token_hex(12)}).encode()).decode()
    signature = hmac.new(access_code().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature

def agency_allowed(request):
    if current_employee(request) is not None:
        return True
    secret = access_code()
    provided = request.headers.get('x-agency-key', '')
    if provided and hmac.compare_digest(provided.encode(), secret.encode()):
        return True
    try:
        payload, signature = request.cookies.get(COOKIE, '').split('.')
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected) and json.loads(base64.urlsafe_b64decode(payload))['expires'] > time.time()
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return False

class LoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=256)

@router.get('/session')
def session(request: Request, db: Session = Depends(get_db)):
    employee = current_employee(request, db)
    if employee:
        return {'authenticated': True, 'employee': profile(employee)}
    return {'authenticated': bool(agency_allowed(request))}

@router.post('/login')
async def login(data: LoginIn, request: Request, response: Response):
    address = request.client.host if request.client else 'local'
    recent = [t for t in _failures.get(address, []) if t > time.time() - LOGIN_WINDOW]
    if len(recent) >= 5:
        raise HTTPException(429, 'Too many attempts. Wait ten minutes before trying again.')
    if not hmac.compare_digest(data.code.encode(), access_code().encode()):
        _failures[address] = [*recent, time.time()]
        raise HTTPException(401, 'The workspace access code is incorrect.')
    _failures.pop(address, None)
    response.set_cookie(COOKIE, signed_session(), httponly=True, secure=request.url.scheme == 'https', samesite='strict', max_age=43200, path='/')
    return {'authenticated': True}

@router.post('/logout')
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_employee_session(request, db)
    db.commit()
    response.delete_cookie(COOKIE, path='/')
    response.delete_cookie(EMPLOYEE_COOKIE, path='/')
    return {'authenticated': False}

class CapabilityLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str):
                args[2] = args[2].split('?', 1)[0]
                args[2] = re.sub(r'(/api/public/(?:submissions|intake)/)[A-Za-z0-9_-]+', r'\1[redacted]', args[2])
                args[2] = re.sub(r'(/(?:c|s)/)[A-Za-z0-9_-]+', r'\1[redacted]', args[2])
            record.args = tuple(args)
        return True

logging.getLogger('uvicorn.access').addFilter(CapabilityLogFilter())
