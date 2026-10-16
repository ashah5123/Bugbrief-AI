"""Scoped customer flows. Hosted inference below uses explicitly labelled test doubles."""
from io import BytesIO
import logging
import secrets
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.config import settings
from app.auth import CapabilityLogFilter, _failures
from app.providers.base import Generation, ProviderError
from app.schemas import BugReport

@pytest.fixture
def anonymous(client):
    _failures.clear()
    with TestClient(app) as customer:
        yield customer

@pytest.fixture
def link(client):
    project=client.post('/api/projects',json={'name':'Customer site','url':'https://example.com'}).json()
    share=client.post(f'/api/projects/{project["id"]}/intake-link',json={}).json()
    return {**share,'project_id':project['id']}

def create(customer,link,**kwargs):
    return customer.post(f'/api/public/intake/{link["token"]}/submissions',json={'client_nonce':secrets.token_urlsafe(24),'text':'I clicked Pay now. Nothing happened.',**kwargs})

def image():
    output=BytesIO();Image.new('RGB',(120,80),'white').save(output,format='PNG');return output.getvalue()

class ReportDouble:
    def __init__(self,data):self.data=data;self.evidence=[]
    async def generate(self,evidence):
        self.evidence.append(evidence)
        return Generation(BugReport.model_validate(self.data),10,20)

def test_agency_endpoints_require_access(anonymous):
    for path in ['/api/projects','/api/feedback','/api/feedback/unknown','/api/feedback/a/attachments/b/content']:
        assert anonymous.get(path).status_code==401
    assert anonymous.post('/api/projects',json={'name':'Forbidden'}).status_code==401
    assert anonymous.get('/api/auth/session').json()=={'authenticated':False}
    assert set(anonymous.get('/api/health').json())=={'status','version'}

def test_signed_cookie_login_and_logout(anonymous):
    assert anonymous.post('/api/auth/login',json={'code':'wrong'}).status_code==401
    response=anonymous.post('/api/auth/login',json={'code':'test-agency-access-code'})
    assert response.status_code==200
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert anonymous.get('/api/projects').status_code==200
    assert anonymous.post('/api/auth/logout',json={}).status_code==200
    assert anonymous.get('/api/projects').status_code==401

def test_login_attempt_cap(anonymous):
    for _ in range(5):assert anonymous.post('/api/auth/login',json={'code':'bad'}).status_code==401
    assert anonymous.post('/api/auth/login',json={'code':'test-agency-access-code'}).status_code==429

def test_tampered_cookie_denied(anonymous):
    anonymous.cookies.set('bugbrief_agency','eyJleHBpcmVzIjo5OTk5OTk5OTk5fQ==.forged')
    assert anonymous.get('/api/projects').status_code==401

def test_project_config_is_minimal(anonymous,link):
    response=anonymous.get(f'/api/public/intake/{link["token"]}')
    assert response.json()=={'project_name':'Customer site','project_url':'https://example.com','allowed_origin':'https://example.com'}
    assert anonymous.get('/api/public/intake/nonexistent').status_code==404
    assert anonymous.delete(f'/api/projects/{link["project_id"]}/intake-link').status_code==401

def test_link_reuse_revocation_and_new_token(client,anonymous,link):
    first=create(anonymous,link).json()
    same=client.post(f'/api/projects/{link["project_id"]}/intake-link',json={}).json()
    assert same['token']==link['token']
    assert client.delete(f'/api/projects/{link["project_id"]}/intake-link').status_code==200
    assert anonymous.get(f'/api/public/intake/{link["token"]}').status_code==404
    assert anonymous.get(f'/api/public/submissions/{first["access_token"]}').status_code==404
    newer=client.post(f'/api/projects/{link["project_id"]}/intake-link',json={}).json()
    assert newer['token']!=link['token']

def test_idempotent_create_and_private_resume(anonymous,link):
    nonce=secrets.token_urlsafe(24)
    first=create(anonymous,link,client_nonce=nonce).json()
    again=create(anonymous,link,client_nonce=nonce).json()
    other=create(anonymous,link).json()
    assert again['access_token']==first['access_token'] and again['reference']==first['reference']
    assert first['access_token']!=other['access_token']
    assert anonymous.get(f'/api/public/submissions/{link["token"]}').status_code==404
    resumed=anonymous.get(f'/api/public/submissions/{first["access_token"]}').json()
    assert resumed['text']==first['text'] and 'report' not in resumed and 'proposal' not in resumed
    assert 'feedback_id' not in resumed and 'project_id' not in resumed

def test_pending_drafts_hidden_then_submitted_once(client,anonymous,link):
    item=create(anonymous,link,reporter_name='Customer A').json();token=item['access_token']
    assert client.get('/api/feedback').json()==[]
    first=anonymous.post(f'/api/public/submissions/{token}/submit',json={})
    assert first.status_code==200 and first.json()['stage']=='submitted'
    assert anonymous.post(f'/api/public/submissions/{token}/submit',json={}).json()['reference']==item['reference']
    inbox=client.get('/api/feedback').json()
    assert len(inbox)==1 and inbox[0]['customer']['reporter_name']=='Customer A'
    assert inbox[0]['project_id']==link['project_id']
    assert inbox[0]['customer']['submitted_at']

@pytest.mark.parametrize('field,value',[('project_id','elsewhere'),('report',{'title':'Injected'}),('status','approved')])
def test_customer_cannot_set_agency_fields(anonymous,link,field,value):
    assert create(anonymous,link,**{field:value}).status_code==422

def test_create_limit_keeps_existing_resume(anonymous,link,monkeypatch):
    monkeypatch.setattr(settings,'public_submissions_daily_limit',1)
    nonce=secrets.token_urlsafe(24)
    first=create(anonymous,link,client_nonce=nonce).json()
    assert create(anonymous,link).status_code==429
    assert create(anonymous,link,client_nonce=nonce).json()['access_token']==first['access_token']

def test_context_is_not_assumed_to_be_issue_browser(client,anonymous,link,report_data):
    context={'user_agent':'Test browser 1.0','viewport_width':390,'viewport_height':844,'source':'embedded','same_browser_confirmed':False}
    item=create(anonymous,link,context=context,reporter_name='Name not for provider').json()
    double=ReportDouble(report_data);app.state.generator=double
    response=anonymous.post(f'/api/public/submissions/{item["access_token"]}/process',json={'consent':True})
    assert response.status_code==200 and response.json()['questions']
    evidence=double.evidence[0]
    assert evidence['browser']=='' and evidence['device']==''
    assert 'NOT confirmed' in evidence['captured_context']
    assert '390' in evidence['captured_context']
    assert all('Name not for provider' not in value for value in evidence.values())
    anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit',json={})
    received=client.get('/api/feedback').json()[0]
    assert received['customer']['context']['viewport_width']==390 and received['browser']==''

def test_confirmed_browser_is_explicitly_labelled(anonymous,link,report_data):
    item=create(anonymous,link,context={'user_agent':'Test browser 1.0','same_browser_confirmed':True}).json()
    double=ReportDouble(report_data);app.state.generator=double
    anonymous.post(f'/api/public/submissions/{item["access_token"]}/process',json={'consent':True})
    assert double.evidence[0]['browser']=='Customer-confirmed issue browser: Test browser 1.0'
    assert 'Customer confirmed' in double.evidence[0]['captured_context']

@pytest.mark.parametrize('context',[{'viewport_width':20001},{'user_agent':'x'*501},{'source':'unknown'},{'extra':'secret'}])
def test_context_validation(anonymous,link,context):
    assert create(anonymous,link,context=context).status_code==422

def test_unsafe_url_rejected(anonymous,link):
    assert create(anonymous,link,page_url='javascript:alert(1)').status_code==422

def test_missing_key_still_allows_sending_without_leaking_setup(client,anonymous,link,monkeypatch):
    item=create(anonymous,link).json()
    monkeypatch.setattr(settings,'gemini_api_key','')
    checked=anonymous.post(f'/api/public/submissions/{item["access_token"]}/process',json={'consent':True}).json()
    assert checked['text']==item['text'] and checked['processing_error']
    assert '.env' not in checked['processing_error'] and 'GEMINI_API_KEY' not in checked['processing_error']
    assert anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit',json={}).status_code==200
    assert client.get('/api/feedback').json()[0]['report'] is None

def test_no_external_processing_without_consent(client,anonymous,link):
    item=create(anonymous,link).json()
    assert anonymous.post(f'/api/public/submissions/{item["access_token"]}/process',json={'consent':False}).status_code==400
    assert client.get('/api/health').json()['usage']['attempts']==0

def test_follow_up_answers_and_proposal_preserve_manual_report(client,anonymous,link,report_data):
    item=create(anonymous,link).json();token=item['access_token']
    double=ReportDouble(report_data);app.state.generator=double
    first=anonymous.post(f'/api/public/submissions/{token}/process',json={'consent':True}).json()
    assert first['questions']==report_data['questions']
    # Agency access can inspect by ID; ordinary pending drafts remain out of the inbox.
    from app.db import get_db
    from app.models import Feedback
    db=next(app.dependency_overrides[get_db]())
    feedback=db.query(Feedback).first();feedback_id=feedback.id
    db.close()
    stored=client.get(f'/api/feedback/{feedback_id}').json()
    manual={**report_data,'title':'Preserve agency manual edits'}
    assert client.put(f'/api/feedback/{feedback_id}/report',json={'version':stored['version'],'report':manual}).status_code==200
    answer={'question':report_data['questions'][0],'answer':'Chrome on Android'}
    saved=anonymous.post(f'/api/public/submissions/{token}/answers',json={'answers':[answer]}).json()
    assert len(saved['answers'])==1 and saved['questions']==[]
    # Network resubmission of the same answer is idempotent.
    assert len(anonymous.post(f'/api/public/submissions/{token}/answers',json={'answers':[answer]}).json()['answers'])==1
    revised={**report_data,'questions':[]}
    app.state.generator=ReportDouble(revised)
    second=anonymous.post(f'/api/public/submissions/{token}/process',json={'consent':True}).json()
    assert second['stage']=='ready'
    owner=client.get(f'/api/feedback/{feedback_id}').json()
    assert owner['report']['title']==manual['title'] and owner['proposal']['title']==report_data['title']
    assert any(key.startswith('clarification:') for key in app.state.generator.evidence[0])

def test_wrong_question_rejected(anonymous,link):
    item=create(anonymous,link).json()
    response=anonymous.post(f'/api/public/submissions/{item["access_token"]}/answers',json={'answers':[{'question':'Unrequested question','answer':'No'}]})
    assert response.status_code==422

def test_project_processing_cap_does_not_block_local_saves(client,anonymous,link,report_data,monkeypatch):
    monkeypatch.setattr(settings,'public_ai_daily_limit',1)
    first=create(anonymous,link).json();second=create(anonymous,link).json()
    double=ReportDouble(report_data);app.state.generator=double
    assert anonymous.post(f'/api/public/submissions/{first["access_token"]}/process',json={'consent':True}).json()['has_report']
    checked=anonymous.post(f'/api/public/submissions/{second["access_token"]}/process',json={'consent':True}).json()
    assert checked['processing_error'] and not checked['has_report']
    assert len(double.evidence)==1
    assert anonymous.post(f'/api/public/submissions/{second["access_token"]}/submit',json={}).status_code==200
    assert client.get('/api/health').json()['usage']['attempts']==1

def test_provider_failure_preserves_original_and_allows_send(anonymous,link):
    class Failure:
        async def generate(self,evidence):raise ProviderError('quota','Private provider details',429)
    app.state.generator=Failure()
    item=create(anonymous,link).json();token=item['access_token']
    failed=anonymous.post(f'/api/public/submissions/{token}/process',json={'consent':True}).json()
    assert failed['text']==item['text'] and failed['processing_error'] and 'Private' not in failed['processing_error']
    assert anonymous.post(f'/api/public/submissions/{token}/submit',json={}).status_code==200

def test_customer_screenshot_scope_and_review(anonymous,link):
    first=create(anonymous,link).json();second=create(anonymous,link).json()
    path=f'/api/public/submissions/{first["access_token"]}/attachments'
    assert anonymous.post(path,content=image(),headers={'Content-Type':'image/png'}).status_code==400
    uploaded=anonymous.post(path+'?reviewed=true',content=image(),headers={'Content-Type':'image/png'})
    assert uploaded.status_code==201
    image_id=uploaded.json()['attachments'][0]['id']
    assert 'analysis' not in uploaded.json()['attachments'][0]
    assert anonymous.get(f'{path}/{image_id}/content').status_code==200
    assert anonymous.get(f'/api/public/submissions/{second["access_token"]}/attachments/{image_id}/content').status_code==404
    assert anonymous.post(path+'?reviewed=true',content=b'a'*(2*1024*1024+1),headers={'Content-Type':'image/png'}).status_code==413
    assert anonymous.delete(f'{path}/{image_id}').json()['attachments']==[]

def test_submitted_submission_is_read_only(anonymous,link):
    item=create(anonymous,link).json();base=f'/api/public/submissions/{item["access_token"]}'
    anonymous.post(base+'/submit',json={})
    assert anonymous.put(base,json={'text':'Changed'}).status_code==409
    assert anonymous.post(base+'/process',json={'consent':True}).status_code==409
    assert anonymous.post(base+'/answers',json={'answers':[{'question':'Additional context','answer':'Changed'}]}).status_code==409
    assert anonymous.post(base+'/attachments?reviewed=true',content=image(),headers={'Content-Type':'image/png'}).status_code==409
    assert anonymous.get(base).json()['text']==item['text']

def test_empty_draft_cannot_be_submitted(anonymous,link):
    item=create(anonymous,link,text='').json()
    assert anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit',json={}).status_code==400

def test_capabilities_redacted_from_access_logs():
    record=logging.LogRecord('uvicorn.access',20,'',0,'x',('127.0.0.1','GET','/api/public/submissions/SECRET/attachments/a/content?filename=private.png','1.1',200),None)
    assert CapabilityLogFilter().filter(record)
    assert 'SECRET' not in record.args[2] and 'private.png' not in record.args[2]

def test_private_responses_are_not_cacheable(anonymous,link):
    item=create(anonymous,link).json()
    response=anonymous.get(f'/api/public/submissions/{item["access_token"]}')
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert response.headers['x-content-type-options']=='nosniff'

def test_agency_preserves_original_customer_feedback(client,anonymous,link):
    item=create(anonymous,link).json()
    anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit',json={})
    received=client.get('/api/feedback').json()[0]
    fields={key:received[key] for key in ['project_id','text','page_url','device','browser']}
    assert client.put(f'/api/feedback/{received["id"]}',json={**fields,'text':'An agency guess'}).status_code==409
    assert client.get(f'/api/feedback/{received["id"]}').json()['text']==item['text']
    assert client.put(f'/api/feedback/{received["id"]}',json=fields).status_code==200
