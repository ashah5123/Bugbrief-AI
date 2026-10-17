"""Disposable real SQLite backend for browser tests. AI deliberately unconfigured."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='bugbrief-e2e-') as directory:
    env = {**os.environ, 'DATABASE_URL':f'sqlite:///{directory}/test.db','ATTACHMENTS_DIR':str(Path(directory)/'attachments'),'AGENCY_ACCESS_CODE':'e2e-agency-access-code','GEMINI_API_KEY':'','FREE_TIER_CONFIRMED':'false'}
    subprocess.run([sys.executable,'-m','alembic','-c',str(root/'backend/alembic.ini'),'upgrade','head'],cwd=root,env=env,check=True)
    # Explicit disposable identities for assignment/tracking tests. Never uses the operator database.
    seed = "from app.db import SessionLocal; from app.models import CustomerAccount,EmployeeAccount; from app.customer_auth import password_hash; s=SessionLocal(); hashed=password_hash('Workflow test phrase 42!'); s.add(CustomerAccount(name='Workflow Customer',email='workflow-customer@example.com',password_hash=hashed)); s.add(EmployeeAccount(name='Workflow Employee',email='workflow-employee@example.com',password_hash=hashed)); s.commit(); s.close()"
    subprocess.run([sys.executable, '-c', seed], cwd=root/'backend', env=env, check=True)
    try:
        subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(root/'backend'),'--host','127.0.0.1','--port','18000'],cwd=root,env=env,check=True)
    except KeyboardInterrupt:
        pass
