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
    try:
        subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(root/'backend'),'--host','127.0.0.1','--port','18000'],cwd=root,env=env,check=True)
    except KeyboardInterrupt:
        pass
