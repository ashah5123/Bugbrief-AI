"""Full-description customer search and attributed, audience-scoped activity history."""
import secrets
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import CustomerSubmission, Feedback, IssueEvent, ProjectEvent, CustomerAccount, now
from test_intake import anonymous, link, create
from test_workflow_safeguards import teammate, role


@pytest.fixture
def search_customer(client):
    with TestClient(app) as customer:
        r=customer.post('/api/customer/register',json={'name':'Search customer','email':'search@example.test','password':'Search account phrase 42!'})
        assert r.status_code==201
        yield customer


def sent(customer,link,text):
    item=create(customer,link,text=text).json()
    assert customer.post('/api/public/submissions/'+item['access_token']+'/submit',json={'draft_version':item['draft_version']}).status_code==200
    return item


def test_customer_search_full_text_reference_unicode_literal_and_combined_filters(client,search_customer,link):
    customer=search_customer
    item=sent(customer,link,'Beginning. '+'x'*180+' UNIQUE-tail हिंदी 100% _literal_')
    other=sent(customer,link,'Another issue')
    path='/api/customer/reports'
    result=customer.get(path,params={'q':'unique-TAIL'}).json()
    assert [r['access_token'] for r in result]==[item['access_token']]
    assert 'UNIQUE-tail' not in result[0]['summary']
    assert customer.get(path,params={'q':'हिंदी'}).json()[0]['access_token']==item['access_token']
    assert customer.get(path,params={'q':'100% _literal_'}).json()[0]['access_token']==item['access_token']
    assert customer.get(path,params={'q':'%_not_anything_'}).json()==[]
    assert len(customer.get(path,params={'q':'BB-'+item['reference'].lower()}).json())==1
    assert len(customer.get(path,params={'q':'Customer SITE','project_id':link['project_id'],'status':'new'}).json())==2
    assert customer.get(path,params={'project_id':'not-a-project'}).json()==[]
    assert customer.get(path,params={'status':'in_progress'}).json()==[]
    assert customer.get(path,params={'q':'x'*201}).status_code==422
    assert customer.get(path,params={'status':'secret'}).status_code==422
    assert customer.get(path,params={'attention':'secret'}).status_code==422


def test_search_action_status_and_archive_scopes(client,search_customer,link):
    customer=search_customer
    first=sent(customer,link,'Needs a reply')
    second=sent(customer,link,'Needs a retest')
    draft=create(customer,link,text='An unfinished draft').json()
    with app.state.session_factory() as db:
        from app.models import IssueProgress
        for record,status in [(first,'needs_information'),(second,'ready_to_retest')]:
            fid=db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token==record['access_token']))
            db.add(IssueProgress(feedback_id=fid,status=status,version=1))
        db.commit()
    path='/api/customer/reports'
    assert customer.get(path,params={'attention':'reply'}).json()[0]['access_token']==first['access_token']
    assert customer.get(path,params={'attention':'retest'}).json()[0]['access_token']==second['access_token']
    assert customer.get(path,params={'status':'draft'}).json()[0]['access_token']==draft['access_token']
    customer.patch('/api/public/submissions/'+first['access_token']+'/archive',json={'archived':True})
    assert customer.get(path,params={'attention':'reply'}).json()==[]
    archived=customer.get(path,params={'archive':'archived','attention':'reply'}).json()
    assert [r['access_token'] for r in archived]==[first['access_token']]
    assert len(customer.get(path,params={'archive':'all'}).json())==3
    assert len(customer.get(path,params={'include_archived':True,'archive':'active'}).json())==2


def test_search_does_not_disclose_other_accounts_or_unverified_private_reports(client,search_customer,link):
    item=sent(search_customer,link,'Confidential searchable phrase')
    with TestClient(app) as other:
        other.post('/api/customer/register',json={'name':'Other','email':'other-search@example.test','password':'Search account phrase 42!'})
        assert other.get('/api/customer/reports',params={'q':'Confidential','archive':'all'}).json()==[]
    client.patch(f'/api/projects/{link["project_id"]}/access',json={'mode':'members'})
    assert search_customer.get('/api/customer/reports',params={'q':item['reference'],'archive':'all'}).json()==[]
    with app.state.session_factory() as db:
        account=db.scalar(select(CustomerAccount).where(CustomerAccount.email=='search@example.test'))
        account.email_verified_at=now();db.commit()
    assert len(search_customer.get('/api/customer/reports',params={'q':'Confidential'}).json())==1


def test_activity_pagination_ties_private_cursors_and_legacy_actor(client,anonymous,link):
    item=sent(anonymous,link,'History report');base='/api/public/submissions/'+item['access_token']
    with app.state.session_factory() as db:
        fid=db.scalar(select(CustomerSubmission.feedback_id))
        public=[IssueEvent(id=str(uuid4()),feedback_id=fid,label='Old public update '+str(n),note='',created_at='2026-01-01T00:00:00+00:00') for n in range(125)]
        private=IssueEvent(feedback_id=fid,label='Internal archive note',visibility='internal',actor_name='Workspace owner',actor_role='owner')
        own=IssueEvent(feedback_id=fid,label='Customer archive preference',visibility='customer',actor_name='Customer',actor_role='customer')
        db.add_all(public+[private,own]);db.commit();private_id=private.id;own_id=own.id
    company=f'/api/feedback/{fid}/activity'
    page=anonymous.get(base+'/activity').json();ids=set()
    while True:
        current={event['id'] for event in page['items']}
        assert not ids.intersection(current);ids.update(current)
        assert all(event['label']!='Internal archive note' for event in page['items'])
        assert all('visibility' not in event for event in page['items'])
        if not page['next_before']:break
        page=anonymous.get(base+'/activity',params={'before':page['next_before']}).json()
    assert len(ids)==126 and own_id in ids and private_id not in ids
    assert anonymous.get(base+'/activity',params={'before':private_id}).status_code==404
    assert client.get(company,params={'before':own_id}).status_code==404
    assert client.get(company,params={'before':'not-found'}).status_code==404
    assert anonymous.get(base).json()['workflow']['history_truncated'] is True
    assert len(anonymous.get(base).json()['workflow']['events'])==50
    assert all(event['actor_name'] is None for event in page['items'])
    other=sent(anonymous,link,'Other history report')
    assert anonymous.get('/api/public/submissions/'+other['access_token']+'/activity',params={'before':next(iter(ids))}).status_code==404


def test_attributed_progress_archives_and_triage_do_not_clear_wait_or_leak(client,search_customer,link,teammate):
    person,eid=teammate
    item=sent(search_customer,link,'Still waiting for a reply');base='/api/public/submissions/'+item['access_token']
    fid=client.get('/api/feedback').json()[0]['id'];path=f'/api/feedback/{fid}'
    assert client.get(path).json()['workflow']['waiting_since']
    assert person.patch(path+'/triage',json={'version':0,'priority':'high','due_date':'2027-01-01'}).status_code==200
    assert person.patch(path+'/archive',json={'archived':True}).status_code==200
    assert client.get(path).json()['workflow']['waiting_since']
    public=search_customer.get(base).json()['workflow']['events']
    assert all(event['label'] not in ('Triage updated','Report archived') for event in public)
    rows=person.get(path+'/activity').json()['items']
    assert next(event for event in rows if event['label']=='Report archived')['actor_name']=='Scoped employee'
    search_customer.patch(base+'/archive',json={'archived':True})
    assert any(event['label']=='Archived in your list' and event['actor_name']=='Search customer' for event in search_customer.get(base+'/activity').json()['items'])
    assert all(event['label']!='Archived in your list' for event in person.get(path+'/activity').json()['items'])
    assert person.patch(path+'/workflow',json={'version':1,'status':'in_progress','assigned_employee_id':eid,'note':'We are investigating.'}).status_code==200
    history=search_customer.get(base+'/activity').json()['items']
    assert any('Assigned to' in event['label'] and event['actor_name']=='Scoped employee' for event in history)
    assert not client.get(path).json()['workflow']['waiting_since']


def test_project_permission_history_is_owner_only_and_noops_are_not_logged(client,link,teammate):
    person,eid=teammate
    path=f'/api/projects/{link["project_id"]}'
    baseline=len(client.get(path+'/activity').json()['items'])
    assert role(client,link,eid,'viewer').status_code==200
    assert role(client,link,eid,'viewer').status_code==200
    first=client.get(path+'/activity').json()['items']
    assert len(first)==baseline+1 and first[-1]['actor_name']=='Workspace owner'
    assert 'contributor → viewer' in first[-1]['note']
    assert person.get(path+'/activity').status_code==403
    assert role(client,link,eid,'manager',True).status_code==200
    assert person.get(path+'/activity').status_code==403
    client.patch(path+'/access',json={'mode':'members'})
    client.patch(path+'/access',json={'mode':'members'})
    rows=client.get(path+'/activity').json()['items']
    assert len(rows)==baseline+3
    assert all('email' not in event for event in rows)
    client.delete(path+'/members/employee/'+eid)
    assert person.get(path+'/activity').status_code==404
    assert client.get(path+'/activity').json()['items'][-1]['label']=='Employee removed from project'


def test_deleted_and_revoked_history_is_inaccessible(client,search_customer,link):
    item=sent(search_customer,link,'Private activity');base='/api/public/submissions/'+item['access_token']
    report=client.get('/api/feedback').json()[0];fid=report['id']
    client.patch(f'/api/feedback/{fid}/archive',json={'archived':True})
    assert search_customer.delete(base).status_code==200
    assert search_customer.get(base+'/activity').status_code==404
    assert client.get(f'/api/feedback/{fid}/activity').status_code==404
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(IssueEvent).where(IssueEvent.feedback_id==fid))==0
