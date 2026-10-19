"""Final-send version binding and verified identity before private access."""
from concurrent.futures import ThreadPoolExecutor
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import CustomerSubmission, Notification, CustomerAccount
from test_intake import anonymous, link, create, image


def verify(customer, owner, email):
    messages=owner.get('/api/team/outbox').json()
    mail=next(mail for mail in messages if mail['recipient']==email and '/verify/' in mail['body'])
    token=re.search(r'/verify/([A-Za-z0-9_-]{43})',mail['body'])[1]
    return customer.post('/api/auth/accounts/customer/verify/complete',json={'token':token})


def test_final_send_requires_reviewed_version_and_never_sends_changed_draft(client,anonymous,link):
    item=create(anonymous,link).json();path='/api/public/submissions/'+item['access_token']
    assert anonymous.post(path+'/submit',json={}).status_code==428
    assert anonymous.post(path+'/submit',json={'draft_version':0}).status_code==422
    new=anonymous.put(path,json={'text':'Newer words not reviewed in the old tab','draft_version':item['draft_version']}).json()
    assert anonymous.post(path+'/submit',json={'draft_version':item['draft_version']}).status_code==409
    assert client.get('/api/feedback').json()==[]
    assert anonymous.get(path).json()['stage']=='draft'
    assert anonymous.get(path).json()['submitted_at'] is None
    assert client.get('/api/auth/notifications/company').json()['unread_count']==0
    sent=anonymous.post(path+'/submit',json={'draft_version':new['draft_version']})
    assert sent.status_code==200 and sent.json()['text']==new['text']
    retry=anonymous.post(path+'/submit',json={'draft_version':new['draft_version']})
    assert retry.status_code==200 and retry.json()['submitted_at']==sent.json()['submitted_at']
    assert anonymous.post(path+'/submit',json={'draft_version':item['draft_version']}).status_code==409
    assert client.get('/api/auth/notifications/company').json()['unread_count']==1


def test_screenshot_changed_after_review_cannot_be_sent_unreviewed(client,anonymous,link):
    item=create(anonymous,link).json();path='/api/public/submissions/'+item['access_token']
    saved=anonymous.post(path+'/attachments?reviewed=true',content=image(),headers={'Content-Type':'image/png'}).json()
    assert anonymous.post(path+'/submit',json={'draft_version':item['draft_version']}).status_code==409
    assert client.get('/api/feedback').json()==[]
    assert anonymous.post(path+'/submit',json={'draft_version':saved['draft_version']}).status_code==200
    assert client.get('/api/feedback').json()[0]['attachments']


def test_simultaneous_final_send_retries_only_emit_one_received_alert(client,anonymous,link):
    item=create(anonymous,link).json();path='/api/public/submissions/'+item['access_token']+'/submit'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: anonymous.post(path,json={'draft_version':item['draft_version']}),range(2)))
    assert all(response.status_code==200 for response in results)
    assert results[0].json()['submitted_at']==results[1].json()['submitted_at']
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind=='report_received'))==1


@pytest.mark.parametrize('mail_mode',['local','smtp'])
def test_unverified_private_grants_block_every_content_path_until_real_verification(client,link,monkeypatch,mail_mode):
    from app.config import settings
    email='private@example.test'
    with TestClient(app) as customer:
        assert customer.post('/api/customer/register',json={'name':'Pending customer','email':email,'password':'A secure customer phrase 42!'}).status_code==201
        item=create(customer,link).json();path='/api/public/submissions/'+item['access_token']
        saved=customer.post(path+'/attachments?reviewed=true',content=image(),headers={'Content-Type':'image/png'}).json()
        assert customer.post(path+'/submit',json={'draft_version':saved['draft_version']}).status_code==200
        fid=client.get('/api/feedback').json()[0]['id']
        client.post(f'/api/feedback/{fid}/messages',json={'body':'Existing reply before the project became private'})
        assert customer.get('/api/auth/notifications/customer').json()['unread_count']==1
        verification_mail=next(mail for mail in client.get('/api/team/outbox').json() if mail['recipient']==email and '/verify/' in mail['body'])
        verification_token=re.search(r'/verify/([A-Za-z0-9_-]{43})',verification_mail['body'])[1]
        monkeypatch.setattr(settings,'mail_mode',mail_mode)
        client.patch(f'/api/projects/{link["project_id"]}/access',json={'mode':'members'})
        access=client.post(f'/api/projects/{link["project_id"]}/members/customer',json={'email':email}).json()
        assert access['customers'][0]['verification_required'] is True
        assert access['customers'][0]['email_verified'] is False
        for method,url,body in [('GET','/api/public/intake/'+link['token'],None),('GET',path,None),
            ('GET',path+'/messages',None),('GET',path+'/attachments/'+saved['attachments'][0]['id']+'/content',None),
            ('POST',path+'/messages',{'body':'Denied'}),('PATCH',path+'/archive',{'archived':True}),
            ('DELETE',path,None),('POST',path+'/submit',{'draft_version':saved['draft_version']}),
            ('POST','/api/customer/claims',{'token':item['access_token']}),
            ('POST','/api/customer/projects',{'token':link['token']})]:
            response=customer.request(method,url,json=body) if body is not None else customer.request(method,url)
            assert response.status_code==403,(method,url,response.status_code)
        assert customer.get('/api/customer/reports').json()==[]
        assert customer.get('/api/auth/notifications/customer').json()['items']==[]
        assert customer.get('/api/auth/notifications/customer').json()['unread_count']==0
        pending=customer.get('/api/customer/projects').json()[0]
        assert pending['verification_required'] and pending['intake_token'] is None
        assert pending['name']=='Private project invitation' and pending['team_name']==''
        assert client.get(f'/api/feedback/{fid}').status_code==200
        assert customer.post('/api/auth/accounts/customer/verify/complete',json={'token':verification_token}).status_code==200
        assert customer.get('/api/customer/session').json()['customer']['email_verified'] is True
        assert customer.get('/api/public/intake/'+link['token']).status_code==200
        assert customer.get(path).status_code==200
        assert customer.get(path+'/messages').json()[0]['body']=='Existing reply before the project became private'
        assert customer.get(path+'/attachments/'+saved['attachments'][0]['id']+'/content').status_code==200
        assert len(customer.get('/api/customer/reports').json())==1
        assert customer.get('/api/auth/notifications/customer').json()['unread_count']==1
        active=customer.get('/api/customer/projects').json()[0]
        assert not active['verification_required'] and active['intake_token']==link['token']
        assert active['name']=='Customer site'


def test_verification_does_not_restore_revoked_access_or_grant_other_projects(client,link):
    email='revoked@example.test'
    with TestClient(app) as customer:
        customer.post('/api/customer/register',json={'name':'Revoked customer','email':email,'password':'A secure customer phrase 42!'})
        client.patch(f'/api/projects/{link["project_id"]}/access',json={'mode':'members'})
        access=client.post(f'/api/projects/{link["project_id"]}/members/customer',json={'email':email}).json()
        cid=access['customers'][0]['id']
        client.delete(f'/api/projects/{link["project_id"]}/members/customer/{cid}')
        assert verify(customer,client,email).status_code==200
        assert customer.get('/api/public/intake/'+link['token']).status_code==403
        assert customer.get('/api/customer/projects').json()==[]
        client.post(f'/api/projects/{link["project_id"]}/members/customer',json={'email':email})
        assert customer.get('/api/public/intake/'+link['token']).status_code==200
        other=client.post('/api/projects',json={'name':'Uninvited private project'}).json()
        other_link=client.post(f'/api/projects/{other["id"]}/intake-link',json={}).json()['token']
        client.patch(f'/api/projects/{other["id"]}/access',json={'mode':'members'})
        assert customer.get('/api/public/intake/'+other_link).status_code==403


def test_unverified_link_based_projects_remain_available(client,link):
    with TestClient(app) as customer:
        customer.post('/api/customer/register',json={'name':'Link customer','email':'link@example.test','password':'A secure customer phrase 42!'})
        assert customer.get('/api/public/intake/'+link['token']).status_code==200
        item=create(customer,link).json()
        assert customer.post('/api/public/submissions/'+item['access_token']+'/submit',json={'draft_version':item['draft_version']}).status_code==200
