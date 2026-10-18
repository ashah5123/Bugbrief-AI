"""Disposable real SQLite backend for browser tests. AI deliberately unconfigured."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='bugbrief-e2e-') as directory:
    env = {**os.environ, 'DATABASE_URL':f'sqlite:///{directory}/test.db','ATTACHMENTS_DIR':str(Path(directory)/'attachments'),'AGENCY_ACCESS_CODE':'e2e-agency-access-code','GEMINI_API_KEY':'','FREE_TIER_CONFIRMED':'false','MAIL_MODE':'local','PUBLIC_BASE_URL':'http://127.0.0.1:15173'}
    subprocess.run([sys.executable,'-m','alembic','-c',str(root/'backend/alembic.ini'),'upgrade','head'],cwd=root,env=env,check=True)
    # Explicit disposable identities for assignment/tracking tests. Never uses the operator database.
    seed = """
from app.db import SessionLocal
from app.models import CustomerAccount,EmployeeAccount,CustomerSession,EmployeeSession
from app.customer_auth import password_hash
import hashlib,base64,time
with SessionLocal() as s:
    hashed=password_hash('Workflow test phrase 42!')
    identities=[
        (CustomerAccount,CustomerSession,'Workflow Customer','workflow-customer@example.com',b'c'),
        (EmployeeAccount,EmployeeSession,'Workflow Employee','workflow-employee@example.com',b'e'),
        (CustomerAccount,CustomerSession,'Audit Customer','audit-customer@example.com',b'd'),
        (EmployeeAccount,EmployeeSession,'Audit Employee','audit-employee@example.com',b'a'),
        (EmployeeAccount,EmployeeSession,'Personal desktop','experience-desktop@example.test',b'f'),
        (EmployeeAccount,EmployeeSession,'Personal mobile','experience-mobile@example.test',b'g'),
        (CustomerAccount,CustomerSession,'Guided Customer','guided-desktop@example.test',b'h'),
        (CustomerAccount,CustomerSession,'Guided Customer','guided-mobile@example.test',b'i'),
        (CustomerAccount,CustomerSession,'Returning Customer','returning-desktop@example.test',b'j'),
        (CustomerAccount,CustomerSession,'Returning Customer','returning-mobile@example.test',b'k'),
    ]
    for model,sessions,name,email,seed_byte in identities:
        account=model(name=name,email=email,password_hash=hashed)
        s.add(account);s.flush()
        token=base64.urlsafe_b64encode(seed_byte*32).rstrip(b'=')
        s.add(sessions(token_hash=hashlib.sha256(token).hexdigest(),account_id=account.id,expires_at=time.time()+3600))
    account=s.query(EmployeeAccount).filter_by(email='audit-employee@example.com').one()
    # Separate disposable Audit Employee sessions let each viewport test sign out independently.
    token=base64.urlsafe_b64encode(b'b'*32).rstrip(b'=')
    s.add(EmployeeSession(token_hash=hashlib.sha256(token).hexdigest(),account_id=account.id,expires_at=time.time()+3600))
    s.commit()
"""
    subprocess.run([sys.executable, '-c', seed], cwd=root/'backend', env=env, check=True)
    try:
        subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(root/'backend'),'--host','127.0.0.1','--port','18000'],cwd=root,env=env,check=True)
    except KeyboardInterrupt:
        pass
