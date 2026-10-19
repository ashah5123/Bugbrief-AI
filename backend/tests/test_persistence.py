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
    process("from app.db import SessionLocal; from app.models import Project,Feedback; s=SessionLocal(); s.execute(__import__('sqlalchemy').text(\"INSERT INTO projects (id,name,url,created_at) VALUES ('p','Existing project','','old')\")); s.commit(); s.execute(__import__('sqlalchemy').text(\"INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,report,version,created_at,updated_at) VALUES ('f','p','Existing original feedback','','','','review',:report,1,'old','old')\"), {'report':__import__('json').dumps({'title':'Saved manual edit'})}); s.commit(); s.close()")
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


def test_employee_account_and_session_survive_restart(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{tmp_path/"employees.db"}',
           'EMPLOYEE_MANIFEST': str(tmp_path/'employee-manifest.json'), 'AGENCY_ACCESS_CODE': 'employee-restart-code'}
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'],
                   cwd=root, env=env, check=True, capture_output=True)
    create = """
import json,os
from fastapi.testclient import TestClient
from app.main import app
from app.employee_auth import COOKIE
with TestClient(app) as c:
    assert c.post('/api/auth/employee/register',json={'name':'Persistent employee','email':'employee@example.com','password':'Persistent employee phrase 42!','workspace_code':'employee-restart-code'}).status_code==201
    assert c.post('/api/projects',json={'name':'Employee shared project'}).status_code==201
    open(os.environ['EMPLOYEE_MANIFEST'],'w').write(json.dumps({'cookie':c.cookies.get(COOKIE)}))
"""
    read = """
import json,os
from fastapi.testclient import TestClient
from app.main import app
from app.employee_auth import COOKIE
manifest=json.load(open(os.environ['EMPLOYEE_MANIFEST']))
with TestClient(app) as c:
    assert c.get('/api/projects').status_code==401
    c.cookies.set(COOKIE,manifest['cookie'])
    assert c.get('/api/auth/session').json()['employee']['name']=='Persistent employee'
    assert c.get('/api/projects').json()[0]['name']=='Employee shared project'
    assert c.get('/api/customer/reports').status_code==401
    assert c.post('/api/auth/logout').status_code==200
    c.cookies.set(COOKIE,manifest['cookie'])
    assert c.get('/api/projects').status_code==401
    assert c.post('/api/auth/employee/login',json={'email':'employee@example.com','password':'Persistent employee phrase 42!'}).status_code==200
    assert c.get('/api/projects').status_code==200
"""
    for code in (create, read):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)


def test_issue_progress_and_customer_history_survive_restart(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{tmp_path/"progress.db"}',
           'PROGRESS_MANIFEST': str(tmp_path/'progress-manifest.json'), 'AGENCY_ACCESS_CODE': 'progress-restart-code'}
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'], cwd=root, env=env, check=True, capture_output=True)
    create = """
import os,json
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import EmployeeAccount
with SessionLocal() as db:
    employee=EmployeeAccount(name='Persistent assignee',email='progress@example.com',password_hash='unused')
    db.add(employee);db.commit();employee_id=employee.id
with TestClient(app) as c:
    c.headers['X-Agency-Key']='progress-restart-code'
    project=c.post('/api/projects',json={'name':'Progress project'}).json()
    assert c.post('/api/projects/'+project['id']+'/members/employee',json={'email':'progress@example.com'}).status_code==200
    link=c.post('/api/projects/'+project['id']+'/intake-link',json={}).json()['token']
    customer=c.post('/api/public/intake/'+link+'/submissions',json={'client_nonce':'persistent-progress-nonce-123','text':'Keep this progress.'}).json()
    c.post('/api/public/submissions/'+customer['access_token']+'/submit',json={})
    feedback=c.get('/api/feedback').json()[0]
    assert c.patch('/api/feedback/'+feedback['id']+'/workflow',json={'version':0,'status':'in_progress','assigned_employee_id':employee_id,'note':'Persist this public update.'}).status_code==200
    open(os.environ['PROGRESS_MANIFEST'],'w').write(json.dumps({'id':feedback['id'],'token':customer['access_token']}))
"""
    read = """
import os,json
from fastapi.testclient import TestClient
from app.main import app
manifest=json.load(open(os.environ['PROGRESS_MANIFEST']))
with TestClient(app) as c:
    public=c.get('/api/public/submissions/'+manifest['token']).json()['workflow']
    assert public['status']=='in_progress' and public['assigned_to']['name']=='Persistent assignee'
    assert public['events'][-1]['note']=='Persist this public update.'
    assert 'version' not in public and 'assigned_employee_id' not in public
    c.headers['X-Agency-Key']='progress-restart-code'
    private=c.get('/api/feedback/'+manifest['id']+'/workflow').json()
    assert private['version']==1 and private['status']=='in_progress'
    assert c.delete('/api/feedback/'+manifest['id']).status_code==200
    assert c.get('/api/public/submissions/'+manifest['token']).status_code==404
"""
    for code in (create, read):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)


def test_project_access_upgrade_preserves_existing_mail_and_notification_state(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'project-upgrade.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'project-persistence-owner-code', 'MAIL_MODE': 'local'}
    def migrate(version):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', version], cwd=root, env=env, check=True, capture_output=True)
    def process(code):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)
    migrate('0008')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Existing private project','','old')")
        db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Preserved feedback','','','','draft',1,'old','old')")
        db.execute("INSERT INTO employee_accounts (id,email,name,password_hash,created_at) VALUES ('active','active@example.test','Active employee','test-hash','old')")
        db.execute("INSERT INTO employee_accounts (id,email,name,password_hash,created_at,disabled_at) VALUES ('disabled','disabled@example.test','Former employee','test-hash','old','old')")
        db.execute("INSERT INTO mail_messages (id,recipient,subject,body,delivery,created_at) VALUES ('mail','active@example.test','Existing verification','Preserved security message','local','old')")
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT employee_id,project_id FROM employee_projects').fetchall() == [('active','p')]
        assert db.execute('SELECT customer_access FROM projects').fetchone()[0] == 'link'
        assert db.execute('SELECT body,notification_id FROM mail_messages').fetchone() == ('Preserved security message',None)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    process("""
from app.db import SessionLocal
from app.models import Notification,NotificationPreference
with SessionLocal() as db:
    db.add(Notification(id='notice',scope='owner',account_id='owner',feedback_id='f',kind='customer_reply',title='Persistent alert'))
    db.add(NotificationPreference(scope='employee',account_id='active',email_enabled=1))
    db.commit()
""")
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    client.headers['X-Agency-Key']='project-persistence-owner-code'
    inbox=client.get('/api/auth/notifications/company').json()
    assert inbox['unread_count']==1 and inbox['items'][0]['title']=='Persistent alert'
    assert client.post('/api/auth/notifications/company/read-report',json={'report':'f'}).json()['changed'] is True
""")
    process("""
from app.db import SessionLocal
from app.models import Notification,NotificationPreference,MailMessage
with SessionLocal() as db:
    assert db.get(Notification,'notice').read_at
    assert db.get(NotificationPreference,('employee','active')).email_enabled==1
    assert db.get(MailMessage,'mail').body=='Preserved security message'
""")


def test_owner_session_survives_restart_and_logout_revokes_replay(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{tmp_path/"owners.db"}',
           'OWNER_MANIFEST': str(tmp_path/'owner-session.txt'), 'AGENCY_ACCESS_CODE':'owner-session-restart-code', 'MAIL_MODE':'local'}
    subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=root,env=env,check=True,capture_output=True)
    create = """
import os
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.post('/api/auth/login',json={'code':'owner-session-restart-code'}).status_code==200
    open(os.environ['OWNER_MANIFEST'],'w').write(client.cookies.get('bugbrief_agency'))
"""
    logout = """
import os
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    client.cookies.set('bugbrief_agency',open(os.environ['OWNER_MANIFEST']).read())
    assert client.get('/api/team').json()['can_manage'] is True
    assert client.post('/api/auth/logout').status_code==200
"""
    replay = """
import os
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    client.cookies.set('bugbrief_agency',open(os.environ['OWNER_MANIFEST']).read())
    assert client.get('/api/projects').status_code==401
"""
    for code in (create,logout,replay):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)


def test_triage_upgrade_and_restart_preserve_existing_workflow(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'triage.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'triage-restart-owner-code', 'MAIL_MODE': 'local'}
    def migrate(version):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', version], cwd=root, env=env, check=True, capture_output=True)
    migrate('0010')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Existing project','','old')")
        db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Keep original feedback','','','','draft',3,'old','old')")
        db.execute("INSERT INTO issue_progress (feedback_id,status,version,updated_at) VALUES ('f','needs_information',7,'old')")
        db.execute("INSERT INTO issue_events (id,feedback_id,label,note,created_at) VALUES ('e','f','Update from the company','Which browser?','old')")
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status,version,updated_at,priority,due_date FROM issue_progress').fetchone() == ('needs_information',7,'old','normal',None)
        assert db.execute('SELECT note FROM issue_events').fetchone() == ('Which browser?',)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    write = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='triage-restart-owner-code'
    r=c.patch('/api/feedback/f/triage',json={'version':7,'priority':'urgent','due_date':'2027-01-01'})
    assert r.status_code==200 and r.json()['status']=='needs_information'
"""
    read = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='triage-restart-owner-code'
    r=c.get('/api/feedback/f').json()
    assert r['workflow']['priority']=='urgent' and r['workflow']['due_date']=='2027-01-01'
    assert r['workflow']['version']==8 and r['version']==3
    assert r['workflow']['events'][-1]['note']=='Which browser?'
"""
    for code in (write, read):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)


def test_project_team_name_upgrade_defaults_and_survives_restart(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'team-name.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'team-name-owner-code', 'MAIL_MODE': 'local'}
    def migrate(version):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', version], cwd=root, env=env, check=True, capture_output=True)
    migrate('0011')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Preserved project','https://example.test','old')")
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT name,url,created_at,team_name FROM projects').fetchone() == ('Preserved project','https://example.test','old','')
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    for code in ("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='team-name-owner-code'
    assert c.put('/api/projects/p',json={'name':'Preserved project','url':'https://example.test','team_name':'Persistent support team'}).status_code==200
""", """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='team-name-owner-code'
    assert c.get('/api/projects').json()[0]['team_name']=='Persistent support team'
"""):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)


def test_duplicate_groups_upgrade_restart_and_retry_safe_updates(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'duplicates.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'duplicates-restart-owner-code', 'MAIL_MODE': 'local'}
    def migrate(version):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', version], cwd=root, env=env, check=True, capture_output=True)
    migrate('0012')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Preserved project','','old')")
        for fid in ('main','child'):
            db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES (?,'p','Preserved original feedback','','','','draft',3,'old','old')", (fid,))
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT text,version FROM feedback').fetchall() == [('Preserved original feedback',3)]*2
        assert db.execute('SELECT count(*) FROM duplicate_groups').fetchone()[0] == 0
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    write = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='duplicates-restart-owner-code'
    assert c.post('/api/feedback/child/duplicates',json={'main_feedback_id':'main','version':0}).status_code==200
    data={'version':1,'request_id':'f8135995-58e4-49fe-8b58-62d36628c302','body':'Persistent shared update'}
    assert c.post('/api/feedback/main/duplicates/updates',json=data).status_code==200
"""
    read = """
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='duplicates-restart-owner-code'
    group=c.get('/api/feedback/main/duplicates').json()['group']
    assert group['version']==2 and len(group['members'])==2
    data={'version':1,'request_id':'f8135995-58e4-49fe-8b58-62d36628c302','body':'Persistent shared update'}
    assert c.post('/api/feedback/main/duplicates/updates',json=data).json()['updated_count']==2
    for fid in ('main','child'):
        assert len(c.get('/api/feedback/'+fid+'/messages').json())==1
    assert c.delete('/api/feedback/main').status_code==200
    assert c.get('/api/feedback/child/duplicates').json()['group'] is None
    assert c.get('/api/feedback/child').json()['text']=='Preserved original feedback'
"""
    for code in (write, read):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)


def test_reply_screenshot_upgrade_restart_idempotency_and_erasure(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    path = tmp_path / 'reply-images.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}', 'AGENCY_ACCESS_CODE': 'reply-images-owner-code',
           'ATTACHMENTS_DIR':str(tmp_path/'images'), 'MAIL_MODE':'local', 'REPLY_MANIFEST':str(tmp_path/'reply.json')}
    def migrate(version):
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade',version],cwd=root,env=env,check=True,capture_output=True)
    migrate('0013')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at) VALUES ('p','Existing project','','old')")
        db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Keep original feedback','','','','draft',4,'old','old')")
        db.execute("INSERT INTO report_messages (id,feedback_id,visibility,author_role,author_name,body,created_at) VALUES ('legacy','f','public','company','Original author','Preserved conversation','old')")
    migrate('head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT body,request_id FROM report_messages').fetchone() == ('Preserved conversation',None)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    write = """
import os,json,base64
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
out=BytesIO(); Image.new('RGB',(20,10),'white').save(out,format='PNG')
payload={'body':'A persistent screenshot reply','request_id':'235cb3eb-fce5-42a6-85d6-dd92b7bc51a5','attachments':[{'filename':'persistent.png','mime_type':'image/png','content_base64':base64.b64encode(out.getvalue()).decode(),'caption':'Persistent caption','reviewed':True}]}
with TestClient(app) as c:
    c.headers['X-Agency-Key']='reply-images-owner-code'
    response=c.post('/api/feedback/f/messages',json=payload)
    assert response.status_code==201
    message=next(m for m in response.json() if m['attachments'])
    json.dump({'payload':payload,'message':message},open(os.environ['REPLY_MANIFEST'],'w'))
"""
    read = """
import os,json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
saved=json.load(open(os.environ['REPLY_MANIFEST']))
with TestClient(app) as c:
    c.headers['X-Agency-Key']='reply-images-owner-code'
    assert len(c.post('/api/feedback/f/messages',json=saved['payload']).json())==2
    message=saved['message']; image=message['attachments'][0]
    path='/api/feedback/f/messages/'+message['id']+'/attachments/'+image['id']+'/content'
    assert c.get(path).status_code==200 and image['caption']=='Persistent caption'
    assert len(list(Path(os.environ['ATTACHMENTS_DIR']).iterdir()))==1
    assert c.get('/api/feedback/f').json()['version']==4
    assert c.delete('/api/feedback/f').status_code==200
    assert c.get(path).status_code==404
    assert list(Path(os.environ['ATTACHMENTS_DIR']).iterdir())==[]
"""
    for code in (write,read):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)


def test_guided_upgrade_preserves_legacy_answers_and_new_details_survive_restart(tmp_path):
    import sqlite3
    root = Path(__file__).resolve().parents[2]
    db_path = tmp_path/'guided.db'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{db_path}', 'AGENCY_ACCESS_CODE': 'guided-restart-code'}
    def migrate(target):
        subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', target],
                       cwd=root, env=env, check=True, capture_output=True)
    def process(code):
        subprocess.run([sys.executable, '-c', code], cwd=root/'backend', env=env, check=True, capture_output=True)
    migrate('0014')
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO projects (id,name,url,created_at,team_name,customer_access) VALUES ('p','Legacy project','','old','','link')")
        db.execute("INSERT INTO feedback (id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Original customer words','','','','draft',1,'old','old')")
        db.execute("INSERT INTO intake_links (id,project_id,token,created_at) VALUES ('l','p','legacy-project-link','old')")
        db.execute("INSERT INTO customer_submissions (id,link_id,feedback_id,access_token,client_nonce,reporter_name,context,stage,created_at) VALUES ('c','l','f','legacy-private-link','legacy-nonce-1234567890','Customer','{}','draft','old')")
    migrate('head')
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    base='/api/public/submissions/legacy-private-link'
    item=c.get(base).json()
    assert item['text']=='Original customer words' and item['guided_details'] is None
    r=c.put(base,json={'text':item['text'],'draft_version':item['draft_version'],'guided_details':{'goal':'Order dinner','expected':'Checkout opens','steps':'Open cart','frequency':'once'}})
    assert r.status_code==200 and r.json()['guided_details']['goal']=='Order dinner'
    assert c.post(base+'/submit',json={}).status_code==200
""")
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    item=c.get('/api/public/submissions/legacy-private-link').json()
    assert item['stage']=='submitted' and item['guided_details']['frequency']=='once'
    c.headers['X-Agency-Key']='guided-restart-code'
    report=c.get('/api/feedback/f').json()
    assert report['text']=='Original customer words'
    assert report['customer']['guided_details']['expected']=='Checkout opens'
    assert c.delete('/api/feedback/f').status_code==200
""")
    with sqlite3.connect(db_path) as db:
        import json
        assert json.loads(db.execute("SELECT guided_details FROM customer_submissions WHERE id='c'").fetchone()[0]) is None
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_safeguards_upgrade_preserves_rows_and_roles_archives_versions_survive_restart(tmp_path):
    import sqlite3
    root=Path(__file__).resolve().parents[2]
    path=tmp_path/'safeguards.db'
    env={**os.environ,'DATABASE_URL':f'sqlite:///{path}','AGENCY_ACCESS_CODE':'safeguards-restart-code'}
    def migrate(target):
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade',target],cwd=root,env=env,check=True,capture_output=True)
    def process(code):
        subprocess.run([sys.executable,'-c',code],cwd=root/'backend',env=env,check=True,capture_output=True)
    migrate('0015')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects(id,name,url,created_at,team_name,customer_access) VALUES ('p','Retained project','','old','','link')")
        db.execute("INSERT INTO feedback(id,project_id,text,page_url,device,browser,status,version,created_at,updated_at) VALUES ('f','p','Retained words','','','','draft',1,'old','old')")
        db.execute("INSERT INTO intake_links(id,project_id,token,created_at) VALUES ('l','p','legacy-link','old')")
        db.execute("INSERT INTO customer_submissions(id,link_id,feedback_id,access_token,client_nonce,reporter_name,context,stage,created_at,guided_details) VALUES ('s','l','f','legacy-token','legacy-nonce-1234567890','Customer','{}','draft','old',?)", ('{"expected":"Retained expectation"}',))
        db.execute("INSERT INTO employee_accounts(id,email,name,password_hash,created_at) VALUES ('e','employee@example.test','Employee','unused','old')")
        db.execute("INSERT INTO employee_projects(employee_id,project_id,created_at) VALUES ('e','p','old')")
    migrate('head')
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='safeguards-restart-code'
    item=c.get('/api/public/submissions/legacy-token').json()
    assert item['draft_version']==1 and item['guided_details']['expected']=='Retained expectation'
    access=c.get('/api/projects/p/access').json()['employees'][0]
    assert access['role']=='contributor' and access['can_delete'] is False
    r=c.put('/api/public/submissions/legacy-token',json={'text':'Updated words','draft_version':1})
    assert r.status_code==200 and r.json()['draft_version']==2
    assert c.post('/api/public/submissions/legacy-token/submit',json={}).status_code==200
    assert c.patch('/api/feedback/f/archive',json={'archived':True}).status_code==200
    assert c.patch('/api/public/submissions/legacy-token/archive',json={'archived':True}).status_code==200
    assert c.patch('/api/projects/p/members/employee/e',json={'role':'manager','can_delete':True}).status_code==200
""")
    process("""
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    c.headers['X-Agency-Key']='safeguards-restart-code'
    assert c.get('/api/feedback').json()==[]
    assert len(c.get('/api/feedback?include_archived=true').json())==1
    item=c.get('/api/public/submissions/legacy-token').json()
    assert item['draft_version']==2 and item['archived_at'] and item['text']=='Updated words'
    access=c.get('/api/projects/p/access').json()['employees'][0]
    assert access['role']=='manager' and access['can_delete'] is True
    assert c.patch('/api/feedback/f/archive',json={'archived':False}).status_code==200
    assert c.get('/api/public/submissions/legacy-token').json()['archived_at']
""")
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
