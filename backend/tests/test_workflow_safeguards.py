"""Concurrency, history boundaries, employee capabilities and independent archives."""
import hashlib
import secrets
import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import Feedback, ReportMessage, CustomerSubmission, EmployeeAccount, EmployeeSession, EmployeeProject
from test_intake import anonymous, link, create, image


def draft_body(item, **changes):
    return {**{key: item[key] for key in ('text', 'page_url', 'reporter_name', 'context', 'guided_details', 'draft_version')}, **changes}


def test_draft_conflict_missing_version_and_exact_retry(anonymous, link):
    first = create(anonymous, link, guided_details={'expected': 'Original'}).json()
    path = '/api/public/submissions/' + first['access_token']
    assert anonymous.put(path, json={'text': 'Blind overwrite'}).status_code == 428
    newer = anonymous.put(path, json=draft_body(first, guided_details={'expected': 'Newer'}))
    assert newer.status_code == 200 and newer.json()['draft_version'] == first['draft_version'] + 1
    # Repeating a committed save after losing its response returns that save, without bumping the version.
    retry = anonymous.put(path, json=draft_body(first, guided_details={'expected': 'Newer'}))
    assert retry.json()['draft_version'] == newer.json()['draft_version']
    stale = anonymous.put(path, json=draft_body(first, text='Stale words'))
    assert stale.status_code == 409
    assert anonymous.get(path).json()['guided_details']['expected'] == 'Newer'
    assert anonymous.get(path).json()['text'] == first['text']
    restored = anonymous.put(path, json=draft_body(newer.json(), text='Reviewed correction'))
    assert restored.status_code == 200 and restored.json()['text'] == 'Reviewed correction'


def test_screenshot_change_invalidates_stale_draft_version(anonymous, link):
    first = create(anonymous, link).json()
    path = '/api/public/submissions/' + first['access_token']
    upload = anonymous.post(path+'/attachments?reviewed=true', content=image(), headers={'Content-Type': 'image/png'})
    assert upload.status_code == 201 and upload.json()['draft_version'] > first['draft_version']
    assert anonymous.put(path, json=draft_body(first, text='Stale correction')).status_code == 409
    assert len(anonymous.get(path).json()['attachments']) == 1


def test_pagination_stable_ties_private_cursors_and_new_replies(client, anonymous, link):
    first = create(anonymous, link).json()
    other = create(anonymous, link).json()
    base = '/api/public/submissions/' + first['access_token']
    anonymous.post(base+'/submit', json={'draft_version': anonymous.get((base + '/submit').removesuffix('/submit')).json().get('draft_version', 1)})
    with app.state.session_factory() as db:
        fid = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == first['access_token']))
        rows = [ReportMessage(id=str(uuid4()), feedback_id=fid, visibility='public', author_role='customer', author_name='Customer', body=str(n), created_at='2026-01-01T00:00:00+00:00') for n in range(205)]
        private = ReportMessage(feedback_id=fid, visibility='internal', author_role='company', author_name='Company', body='Private note')
        db.add_all(rows+[private]); db.commit(); private_id=private.id
    path = f'/api/feedback/{fid}/messages'
    assert isinstance(client.get(path).json(), list)
    page = anonymous.get(base+'/messages?paged=true').json()
    assert len(page['items']) == 100 and page['next_before']
    all_ids = {m['id'] for m in page['items']}
    # A new reply while paging must not shift the older cursor's boundary.
    assert anonymous.post(base+'/messages', json={'body':'New latest reply'}).status_code == 201
    while page['next_before']:
        page = anonymous.get(base+'/messages', params={'paged': True, 'before': page['next_before']}).json()
        ids = {m['id'] for m in page['items']}
        assert not all_ids.intersection(ids)
        all_ids.update(ids)
    assert len(all_ids) == 205 and private_id not in all_ids
    assert anonymous.get(base+'/messages', params={'paged': True, 'before': private_id}).status_code == 404
    assert anonymous.get('/api/public/submissions/'+other['access_token']+'/messages', params={'paged': True, 'before': next(iter(all_ids))}).status_code == 409
    company = client.get(path+'?paged=true').json()
    assert any(m['id'] == private_id for m in company['items'])
    assert client.get(path, params={'paged': True, 'before': 'missing'}).status_code == 404


@pytest.fixture
def teammate(client, link):
    token = secrets.token_urlsafe(32)
    with app.state.session_factory() as db:
        employee = EmployeeAccount(name='Scoped employee', email='scoped@example.test', password_hash='unused')
        db.add(employee); db.flush(); eid=employee.id
        db.add(EmployeeSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), account_id=eid, expires_at=time.time()+3600))
        db.add(EmployeeProject(employee_id=eid, project_id=link['project_id']))
        db.commit()
    with TestClient(app) as person:
        person.cookies.set('bugbrief_employee', token)
        yield person, eid


def role(client, link, eid, value, can_delete=False):
    return client.patch(f'/api/projects/{link["project_id"]}/members/employee/{eid}', json={'role': value, 'can_delete': can_delete})


def test_roles_enforced_for_direct_writes_and_delete_is_independent(client, anonymous, link, teammate):
    person, eid = teammate
    item=create(anonymous,link).json(); base='/api/public/submissions/'+item['access_token']
    anonymous.post(base+'/submit',json={'draft_version': anonymous.get((base + '/submit').removesuffix('/submit')).json().get('draft_version', 1)})
    fid=client.get('/api/feedback').json()[0]['id']; path=f'/api/feedback/{fid}'
    assert role(client,link,eid,'viewer').status_code == 200
    assert person.get(path).status_code == 200
    for method, url, data in [('POST',path+'/messages',{'body':'Not allowed'}),
        ('PATCH',path+'/archive',{'archived':True}), ('PATCH',path+'/triage',{'version':0,'priority':'high'}),
        ('PUT',path+'/report',{}), ('PUT',f'/api/projects/{link["project_id"]}',{'name':'Changed'}),
        ('POST','/api/feedback',{'project_id':link['project_id'],'text':'No access to create'})]:
        assert person.request(method,url,json=data).status_code == 403
    assert person.delete(path).status_code == 403
    assert role(client,link,eid,'contributor').status_code == 200
    assert person.post(path+'/messages',json={'body':'Allowed contributor reply'}).status_code == 201
    assert person.patch(path+'/archive',json={'archived':True}).status_code == 200
    assert person.post(f'/api/projects/{link["project_id"]}/intake-link',json={}).status_code == 403
    assert person.delete(path).status_code == 403
    assert role(client,link,eid,'manager').status_code == 200
    assert person.put(f'/api/projects/{link["project_id"]}',json={'name':'Managed project'}).status_code == 200
    assert person.post(f'/api/projects/{link["project_id"]}/intake-link',json={}).status_code == 200
    assert person.patch(f'/api/projects/{link["project_id"]}/members/employee/{eid}',json={'role':'manager','can_delete':True}).status_code == 403
    assert person.delete(path).status_code == 403
    # Explicit deletion permission is checked independently, including when the role is view-only.
    assert role(client,link,eid,'viewer',True).status_code == 200
    assert person.post(path+'/messages',json={'body':'Still read-only'}).status_code == 403
    assert person.delete(path).status_code == 200
    assert person.get(path).status_code == 404


def test_permissions_do_not_cross_projects_and_changes_take_effect_immediately(client, link, teammate):
    person,eid=teammate
    other=client.post('/api/projects',json={'name':'Other'}).json()
    assert person.get('/api/projects/'+other['id']+'/access').status_code == 404
    assert role(client,link,eid,'unknown').status_code == 422
    assert role(client,link,eid,'viewer').status_code == 200
    permission=person.get('/api/projects').json()[0]['permissions']
    assert permission == {'role':'viewer','work':False,'manage':False,'delete':False}
    assert client.delete(f'/api/projects/{link["project_id"]}/members/employee/{eid}').status_code == 200
    assert person.get('/api/projects').json() == []
    assert person.post(f'/api/projects/{link["project_id"]}/intake-link',json={}).status_code == 404


def test_independent_archives_restore_keep_replies_and_do_not_resolve(client, anonymous, link):
    item=create(anonymous,link).json(); base='/api/public/submissions/'+item['access_token']
    anonymous.post(base+'/submit',json={'draft_version': anonymous.get((base + '/submit').removesuffix('/submit')).json().get('draft_version', 1)})
    fid=client.get('/api/feedback').json()[0]['id']; company=f'/api/feedback/{fid}'
    assert client.patch(company+'/archive',json={'archived':True}).json()['archived_at']
    assert client.get('/api/feedback').json() == []
    assert len(client.get('/api/feedback?include_archived=true').json()) == 1
    assert anonymous.get(base).json()['archived_at'] is None
    assert anonymous.post(base+'/messages',json={'body':'Archived but still need help'}).status_code == 201
    assert client.get(company+'/messages').json()[0]['body']=='Archived but still need help'
    assert client.get(company).json()['workflow']['status'] == 'new'
    assert anonymous.patch(base+'/archive',json={'archived':True}).json()['archived_at']
    assert client.patch(company+'/archive',json={'archived':False}).json()['archived_at'] is None
    assert anonymous.get(base).json()['archived_at']
    assert anonymous.patch(base+'/archive',json={'archived':False}).json()['archived_at'] is None
    assert anonymous.delete(base).status_code == 200
    assert client.patch(company+'/archive',json={'archived':False}).status_code == 404
    assert anonymous.patch(base+'/archive',json={'archived':False}).status_code == 404


def test_customer_archive_list_and_ownership(client, link):
    with TestClient(app) as customer, TestClient(app) as other:
        assert customer.post('/api/customer/register',json={'name':'Owner','email':'owner@example.test','password':'Long customer phrase 42!'}).status_code == 201
        item=create(customer,link).json(); base='/api/public/submissions/'+item['access_token']
        assert customer.patch(base+'/archive',json={'archived':True}).status_code == 409
        customer.post(base+'/submit',json={'draft_version': customer.get((base + '/submit').removesuffix('/submit')).json().get('draft_version', 1)})
        assert other.patch(base+'/archive',json={'archived':True}).status_code == 404
        customer.patch(base+'/archive',json={'archived':True})
        assert customer.get('/api/customer/reports').json() == []
        assert customer.get('/api/customer/reports?include_archived=true').json()[0]['archived_at']
        customer.patch(base+'/archive',json={'archived':False})
        assert len(customer.get('/api/customer/reports').json()) == 1
