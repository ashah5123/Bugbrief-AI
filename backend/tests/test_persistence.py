import os
import subprocess
import sys
from pathlib import Path

def test_alembic_and_restart_persistence(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path / "restart.db"}'}
    subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=root,env=env,check=True,capture_output=True)
    create = "from app.db import SessionLocal; from app.models import Project; s=SessionLocal(); s.add(Project(name='Survives restart',url='')); s.commit(); s.close()"
    read = "from app.db import SessionLocal; from app.models import Project; from sqlalchemy import select; s=SessionLocal(); assert s.scalar(select(Project)).name == 'Survives restart'; s.close()"
    for code in (create,read):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)
