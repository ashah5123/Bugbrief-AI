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

def test_phase_one_upgrade_and_phase_two_restart(tmp_path):
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path / "upgrade.db"}', 'ATTACHMENTS_DIR':str(tmp_path/'files')}
    def migration(target):
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade',target],cwd=root,env=env,check=True,capture_output=True)
    def process(code):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)
    migration('0001')
    process("from app.db import SessionLocal; from app.models import Project,Feedback; s=SessionLocal(); s.add(Project(id='p',name='Existing project',url='')); s.commit(); s.add(Feedback(id='f',project_id='p',text='Existing original feedback',report={'title':'Saved manual edit'})); s.commit(); s.close()")
    migration('head')
    process("from app.db import SessionLocal; from app.models import Attachment,Clarification,AIJob; from app.jobs import day; from app.config import settings; from app.storage import LocalStorage; from PIL import Image; from io import BytesIO; b=BytesIO(); Image.new('RGB',(10,10),'black').save(b,format='PNG'); raw=b.getvalue(); LocalStorage(settings.attachments_dir).put('reviewed.png',raw); s=SessionLocal(); s.add(Attachment(id='a',feedback_id='f',filename='reviewed.png',storage_key='reviewed.png',mime_type='image/png',size=len(raw),width=10,height=10,sha256='test',reviewed_at='test',analysis={'observations':[],'limitations':['Still image only.']})); s.add(Clarification(feedback_id='f',question='Which browser?',answer='Safari')); s.add(AIJob(feedback_id='f',day=day(),model='test-model',kind='vision',outcome='quota')); s.commit(); s.close()")
    process("from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); r=c.get('/api/feedback/f').json(); assert r['text']=='Existing original feedback'; assert r['report']['title']=='Saved manual edit'; assert r['clarifications'][0]['answer']=='Safari'; assert r['attachments'][0]['analysis']['limitations']==['Still image only.']; assert c.get('/api/feedback/f/attachments/a/content').status_code==200; assert c.get('/api/health').json()['usage']['paused'] is True; assert c.get('/api/health').json()['usage']['attempts']==1")
