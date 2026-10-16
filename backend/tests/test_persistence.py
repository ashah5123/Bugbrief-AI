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
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path / "upgrade.db"}', 'ATTACHMENTS_DIR':str(tmp_path/'files'),'AGENCY_ACCESS_CODE':'restart-test-access-code'}
    def migration(target):
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade',target],cwd=root,env=env,check=True,capture_output=True)
    def process(code):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)
    migration('0001')
    process("from app.db import SessionLocal; from app.models import Project,Feedback; s=SessionLocal(); s.add(Project(id='p',name='Existing project',url='')); s.commit(); s.execute(__import__('sqlalchemy').text(\"INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,report,version,created_at,updated_at) VALUES ('f','p','Existing original feedback','','','','review',:report,1,'old','old')\"), {'report':__import__('json').dumps({'title':'Saved manual edit'})}); s.commit(); s.close()")
    migration('head')
    process("from app.db import SessionLocal; from app.models import Attachment,Clarification,AIJob; from app.jobs import day; from app.config import settings; from app.storage import LocalStorage; from PIL import Image; from io import BytesIO; b=BytesIO(); Image.new('RGB',(10,10),'black').save(b,format='PNG'); raw=b.getvalue(); LocalStorage(settings.attachments_dir).put('reviewed.png',raw); s=SessionLocal(); s.add(Attachment(id='a',feedback_id='f',filename='reviewed.png',storage_key='reviewed.png',mime_type='image/png',size=len(raw),width=10,height=10,sha256='test',reviewed_at='test',analysis={'observations':[],'limitations':['Still image only.']})); s.add(Clarification(feedback_id='f',question='Which browser?',answer='Safari')); s.add(AIJob(feedback_id='f',day=day(),model='test-model',kind='vision',outcome='quota')); s.commit(); s.close()")
    process("from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); c.headers['X-Agency-Key']='restart-test-access-code'; r=c.get('/api/feedback/f').json(); assert r['text']=='Existing original feedback'; assert r['report']['title']=='Saved manual edit'; assert r['clarifications'][0]['answer']=='Safari'; assert r['attachments'][0]['analysis']['limitations']==['Still image only.']; assert c.get('/api/feedback/f/attachments/a/content').status_code==200; assert c.get('/api/health').json()['usage']['paused'] is True; assert c.get('/api/health').json()['usage']['attempts']==1")

def test_customer_submission_and_access_code_survive_restart(tmp_path):
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp_path/"customer.db"}','AGENCY_ACCESS_CODE':'','AGENCY_CODE_PATH':str(tmp_path/'agency-code.txt'),'CUSTOMER_MANIFEST':str(tmp_path/'manifest.json')}
    subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=root,env=env,check=True,capture_output=True)
    create="""
import os,json,hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.auth import access_code
with TestClient(app) as c:
    c.headers['X-Agency-Key']=access_code()
    p=c.post('/api/projects',json={'name':'Persistent customer project'}).json()
    token=c.post('/api/projects/'+p['id']+'/intake-link',json={}).json()['token']
    item=c.post('/api/public/intake/'+token+'/submissions',json={'client_nonce':'persistence-nonce-123456789','text':'Checkout button does nothing.','context':{'viewport_width':390,'viewport_height':844}}).json()
    c.post('/api/public/submissions/'+item['access_token']+'/submit',json={})
    open(os.environ['CUSTOMER_MANIFEST'],'w').write(json.dumps({'token':item['access_token'],'code_hash':hashlib.sha256(access_code().encode()).hexdigest()}))
"""
    read="""
import os,json,hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.auth import access_code
manifest=json.load(open(os.environ['CUSTOMER_MANIFEST']))
with TestClient(app) as c:
    assert c.get('/api/projects').status_code==401
    item=c.get('/api/public/submissions/'+manifest['token']).json()
    assert item['stage']=='submitted' and item['context']['viewport_width']==390
    assert 'report' not in item
    assert hashlib.sha256(access_code().encode()).hexdigest()==manifest['code_hash']
    c.headers['X-Agency-Key']=access_code()
    assert len(c.get('/api/feedback').json())==1
"""
    for code in (create,read):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)


def test_deletion_upgrade_and_erasure_survive_restart(tmp_path):
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'deletion.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'deletion-restart-code'}
    def migrate(target):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', target],
                       cwd=root, env=env, check=True, capture_output=True)
    def process(code):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)
    migrate('0003')
    import sqlite3
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Existing project','','old')")
        db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Original content','','','','draft',1,'old','old')")
    migrate('head')
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    client.headers['X-Agency-Key'] = 'deletion-restart-code'
    assert client.get('/api/feedback/f').json()['text'] == 'Original content'
    assert client.delete('/api/feedback/f').status_code == 200
""")
    process("""
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Feedback
with TestClient(app) as client:
    client.headers['X-Agency-Key'] = 'deletion-restart-code'
    assert client.get('/api/feedback').json() == []
    assert client.get('/api/feedback/f').status_code == 404
with SessionLocal() as db:
    erased = db.get(Feedback, 'f')
    assert erased.deleted_at and erased.text == '' and erased.report is None
""")


def test_customer_account_session_and_report_survive_restart(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{tmp_path/"accounts.db"}',
           'ACCOUNT_MANIFEST': str(tmp_path/'account-manifest.json'), 'AGENCY_ACCESS_CODE': 'account-restart-agency-code'}
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'],
                   cwd=root, env=env, check=True, capture_output=True)
    create = """
import json,os
from fastapi.testclient import TestClient
from app.main import app
from app.customer_auth import COOKIE
with TestClient(app) as c:
    c.headers['X-Agency-Key']='account-restart-agency-code'
    project=c.post('/api/projects',json={'name':'Persistent account project'}).json()
    token=c.post('/api/projects/'+project['id']+'/intake-link',json={}).json()['token']
    assert c.post('/api/customer/register',json={'name':'Persistent customer','email':'persistent@example.com','password':'Persistent customer phrase 42!'}).status_code==201
    item=c.post('/api/public/intake/'+token+'/submissions',json={'client_nonce':'persistent-account-nonce-12345','text':'Keep my customer feedback.'}).json()
    open(os.environ['ACCOUNT_MANIFEST'],'w').write(json.dumps({'cookie':c.cookies.get(COOKIE),'token':item['access_token']}))
"""
    read = """
import json,os
from fastapi.testclient import TestClient
from app.main import app
from app.customer_auth import COOKIE
manifest=json.load(open(os.environ['ACCOUNT_MANIFEST']))
with TestClient(app) as c:
    assert c.get('/api/customer/reports').status_code==401
    c.cookies.set(COOKIE,manifest['cookie'])
    assert c.get('/api/customer/session').json()['customer']['email']=='persistent@example.com'
    assert c.get('/api/customer/reports').json()[0]['access_token']==manifest['token']
    assert c.get('/api/customer/projects').json()[0]['name']=='Persistent account project'
    assert c.get('/api/public/submissions/'+manifest['token']).json()['text']=='Keep my customer feedback.'
    c.post('/api/customer/logout')
    c.cookies.set(COOKIE,manifest['cookie'])
    assert c.get('/api/customer/reports').status_code==401
"""
    for code in (create, read):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)
