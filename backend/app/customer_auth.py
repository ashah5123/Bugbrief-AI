"""Customer credentials and server-side, independently revocable sessions."""
import hashlib
import hmac
import re
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import CustomerAccount, CustomerSession
from .schemas import StrictModel

router = APIRouter(prefix='/api/customer')
COOKIE = 'bugbrief_customer'
SESSION_SECONDS = 7 * 86400
_attempts = {}


def throttle(request, action, limit):
    now = time.time()
    # Bound this single-process development limiter; never trust forwarded headers.
    for key in list(_attempts):
        _attempts[key] = [stamp for stamp in _attempts[key] if stamp > now - 600]
        if not _attempts[key]:
            del _attempts[key]
    key = (request.client.host if request.client else 'local', action)
    recent = _attempts.get(key, [])
    if len(recent) >= limit:
        raise HTTPException(429, 'Too many attempts. Try again in ten minutes.')
    _attempts[key] = [*recent, now]


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    # OWASP's 32 MiB scrypt configuration; no additional dependency.
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**15, r=8, p=3,
                            maxmem=64*1024*1024, dklen=32).hex()
    return f'scrypt$32768$8$3${salt}${digest}'


def password_matches(password, stored):
    try:
        algorithm, n, r, p, salt, digest = stored.split('$')
        if (algorithm, n, r, p) != ('scrypt', '32768', '8', '3'):
            return False
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def current_customer(request, db):
    token = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    session = db.get(CustomerSession, hashlib.sha256(token.encode()).hexdigest())
    if session is None or session.expires_at <= time.time():
        return None
    return db.get(CustomerAccount, session.account_id)


def require_customer(request: Request, db: Session = Depends(get_db)):
    account = current_customer(request, db)
    if account is None:
        raise HTTPException(401, 'Sign in to your customer account to continue.')
    return account


def profile(account):
    return {'id': account.id, 'name': account.name, 'email': account.email, 'email_verified': bool(account.email_verified_at)}


def end_session(request, db):
    token = request.cookies.get(COOKIE, '')
    if token:
        db.execute(delete(CustomerSession).where(CustomerSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))


def start_session(account, request, response, db):
    end_session(request, db)
    db.execute(delete(CustomerSession).where(CustomerSession.expires_at <= time.time()))
    token = secrets.token_urlsafe(32)
    db.add(CustomerSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                           account_id=account.id, expires_at=time.time()+SESSION_SECONDS))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == 'https',
                        samesite='strict', max_age=SESSION_SECONDS, path='/')
    return {'authenticated': True, 'customer': profile(account)}


class Credentials(StrictModel):
    email: str = Field(max_length=254)
    password: SecretStr

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value


class Register(Credentials):
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError('Enter your name.')
        return value.strip()


@router.get('/session')
def session(request: Request, db: Session = Depends(get_db)):
    account = current_customer(request, db)
    return {'authenticated': True, 'customer': profile(account)} if account else {'authenticated': False}


@router.post('/register', status_code=201)
def register(data: Register, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(request, 'register', 5)
    password = data.password.get_secret_value()
    if not 12 <= len(password) <= 128:
        raise HTTPException(400, 'Use a password between 12 and 128 characters.')
    if db.scalar(select(CustomerAccount.id).where(CustomerAccount.email == data.email)):
        raise HTTPException(409, 'An account already uses this email. Sign in instead.')
    account = CustomerAccount(email=data.email, name=data.name, password_hash=password_hash(password))
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account already uses this email. Sign in instead.')
    from .account_management import issue_action
    issue_action(db, 'customer', 'verify', account.email)
    return start_session(account, request, response, db)


@router.post('/login')
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(request, 'login', 8)
    password = data.password.get_secret_value()
    if len(password) > 128:
        raise HTTPException(401, 'Email or password is incorrect.')
    account = db.scalar(select(CustomerAccount).where(CustomerAccount.email == data.email))
    # An unknown email still performs the same expensive password operation.
    stored = account.password_hash if account else 'scrypt$32768$8$3$' + '00'*16 + '$' + '00'*32
    valid = password_matches(password, stored)
    if account is None or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    return start_session(account, request, response, db)


@router.post('/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(request, db)
    db.commit()
    response.delete_cookie(COOKIE, path='/')
    return {'authenticated': False}
