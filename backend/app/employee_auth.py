"""Invited company employees, isolated from customer credentials and sessions."""
import hashlib
import hmac
import re
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import SecretStr
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import EmployeeAccount, EmployeeSession
from .customer_auth import Credentials, Register, password_hash, password_matches, throttle

router = APIRouter(prefix='/api/auth/employee')
COOKIE = 'bugbrief_employee'
SESSION_SECONDS = 12 * 3600


def current_employee(request, db=None):
    token = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    if db is None:
        # Middleware and route dependencies share the configured database.
        with request.app.state.session_factory() as session:
            return current_employee(request, session)
    session = db.get(EmployeeSession, hashlib.sha256(token.encode()).hexdigest())
    if session is None or session.expires_at <= time.time():
        return None
    return db.get(EmployeeAccount, session.account_id)


def profile(account):
    return {'id': account.id, 'name': account.name, 'email': account.email}


def end_employee_session(request, db):
    token = request.cookies.get(COOKIE, '')
    if token:
        db.execute(delete(EmployeeSession).where(EmployeeSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))


def start_employee_session(account, request, response, db):
    from .auth import COOKIE as OWNER_COOKIE
    end_employee_session(request, db)
    db.execute(delete(EmployeeSession).where(EmployeeSession.expires_at <= time.time()))
    token = secrets.token_urlsafe(32)
    db.add(EmployeeSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                           account_id=account.id, expires_at=time.time()+SESSION_SECONDS))
    db.commit()
    # Switching to a named employee must not leave the owner-cookie fallback active.
    response.delete_cookie(OWNER_COOKIE, path='/')
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == 'https',
                        samesite='strict', max_age=SESSION_SECONDS, path='/')
    return {'authenticated': True, 'employee': profile(account)}


class EmployeeRegister(Register):
    workspace_code: SecretStr


@router.post('/register', status_code=201)
def register(data: EmployeeRegister, request: Request, response: Response, db: Session = Depends(get_db)):
    from .auth import access_code
    throttle(request, 'employee-register', 5)
    code = data.workspace_code.get_secret_value()
    if not hmac.compare_digest(code.encode(), access_code().encode()):
        raise HTTPException(403, 'The workspace invitation code is incorrect. Ask your workspace owner for the code.')
    password = data.password.get_secret_value()
    if not 12 <= len(password) <= 128:
        raise HTTPException(400, 'Use a password between 12 and 128 characters.')
    if db.scalar(select(EmployeeAccount.id).where(EmployeeAccount.email == data.email)):
        raise HTTPException(409, 'An employee account already uses this email. Sign in instead.')
    employee = EmployeeAccount(email=data.email, name=data.name, password_hash=password_hash(password))
    db.add(employee)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An employee account already uses this email. Sign in instead.')
    return start_employee_session(employee, request, response, db)


@router.post('/login')
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(request, 'employee-login', 8)
    password = data.password.get_secret_value()
    if len(password) > 128:
        raise HTTPException(401, 'Email or password is incorrect.')
    employee = db.scalar(select(EmployeeAccount).where(EmployeeAccount.email == data.email))
    stored = employee.password_hash if employee else 'scrypt$32768$8$3$' + '00'*16 + '$' + '00'*32
    valid = password_matches(password, stored)
    if employee is None or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    return start_employee_session(employee, request, response, db)
