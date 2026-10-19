"""Shared fixes preserve project isolation, individual retests and private conversations."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import DuplicateGroup, DuplicateMember, DuplicateAction, ReportMessage, Feedback, CustomerSubmission
from test_workflow import database, employee, patch
from test_project_notifications import people


def group(client, fid):
    return client.get(f'/api/feedback/{fid}/duplicates').json()['group']


def link(client, fid, main, version=0):
    return client.post(f'/api/feedback/{fid}/duplicates', json={'main_feedback_id': main, 'version': version})


def shared(client, fid, employee, status='in_progress', note='We are working on the shared checkout fix.', **overrides):
    current = group(client, fid)
    data = {'version': current['version'], 'request_id': str(uuid4()), 'status': status,
            'assigned_employee_id': employee, 'note': note,
            'report_versions': {row['id']: row['workflow']['version'] for row in current['members']}, **overrides}
    return client.post(f'/api/feedback/{fid}/duplicates/workflow', json=data)


@pytest.fixture
def records(client, draft):
    project = draft['project_id']
    token = client.post(f'/api/projects/{project}/intake-link', json={}).json()['token']
    rows = []
    for index in range(2):
        result = client.post(f'/api/public/intake/{token}/submissions', json={
            'client_nonce': f'duplicate-customer-{index}-nonce-123456', 'reporter_name': f'Private Customer {index}',
            'text': f'Customer {index} private checkout report'}).json()
        client.post(f'/api/public/submissions/{result["access_token"]}/submit', json={'draft_version': client.get((f"/api/public/submissions/{result['access_token']}/submit").removesuffix('/submit')).json().get('draft_version', 1)})
        with database() as db:
            fid = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == result['access_token']))
        rows.append({'id': fid, 'token': result['access_token']})
    return {'main': draft['id'], 'project': project, 'customers': rows}


def linked(client, records):
    for index, row in enumerate(records['customers']):
        assert link(client, row['id'], records['main'], version=index).status_code == 200
    return group(client, records['main'])


def test_linking_is_private_flat_and_preserves_evidence_progress(client, records):
    main = records['main']; child = records['customers'][0]
    before = client.get(f'/api/feedback/{child["id"]}').json()
    response = link(client, child['id'], main)
    assert response.status_code == 200
    current = response.json()['group']
    assert current['main_feedback_id'] == main and len(current['members']) == 2 and current['version'] == 1
    after = client.get(f'/api/feedback/{child["id"]}').json()
    assert after['workflow'] == before['workflow'] and after['version'] == before['version']
    assert after['text'] == before['text'] and after['report'] == before['report']
    assert after['duplicate_group'] == {'main_feedback_id': main, 'count': 2, 'is_main': False}
    assert link(client, main, child['id']).status_code == 409
    assert link(client, records['customers'][1]['id'], child['id']).status_code == 409
    assert link(client, records['customers'][1]['id'], main, version=0).status_code == 409
    assert len(group(client, main)['members']) == 2
    assert link(client, records['customers'][1]['id'], main, version=1).status_code == 200


def test_self_cross_project_deleted_and_unsent_targets_rejected(client, records):
    main = records['main']
    assert link(client, main, main).status_code == 422
    other = client.post('/api/projects', json={'name':'Other'}).json()
    foreign = client.post('/api/feedback', json={'project_id': other['id'], 'text':'Different private project'}).json()
    assert link(client, records['customers'][0]['id'], foreign['id']).status_code == 404
    token = client.post(f'/api/projects/{records["project"]}/intake-link', json={}).json()['token']
    pending = client.post(f'/api/public/intake/{token}/submissions', json={'client_nonce':'pending-duplicate-nonce-123456','text':'Unsent private draft'}).json()
    with database() as db:
        pending_id = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == pending['access_token']))
    assert link(client, main, pending_id).status_code == 404
    assert link(client, pending_id, main).status_code == 404
    assert client.delete(f'/api/feedback/{foreign["id"]}').status_code == 200
    assert link(client, main, foreign['id']).status_code == 404


def test_customer_cannot_manage_or_discover_other_reports(client, records):
    linked(client, records)
    child = records['customers'][0]
    with TestClient(app) as customer:
        for suffix in ('/duplicates', '/duplicates/candidates'):
            assert customer.get(f'/api/feedback/{child["id"]}' + suffix).status_code == 401
        assert link(customer, child['id'], records['main']).status_code == 401
        value = customer.get(f'/api/public/submissions/{child["token"]}').json()
        assert 'duplicate_group' not in value and 'group' not in value['workflow']
        assert records['main'] not in str(value) and records['customers'][1]['id'] not in str(value)
        assert customer.get(f'/api/public/submissions/{child["token"]}/duplicates').status_code == 404


def test_project_isolation_guards_group_and_candidate_routes(client, people):
    own, foreign = people['records']
    employee = people['employees'][0]
    assert employee.get(f'/api/feedback/{foreign["id"]}/duplicates').status_code == 404
    assert employee.get(f'/api/feedback/{foreign["id"]}/duplicates/candidates').status_code == 404
    assert link(employee, own['id'], foreign['id']).status_code == 404
    assert employee.get(f'/api/feedback/{own["id"]}/duplicates/candidates').json() == []


def test_candidate_search_is_project_scoped_and_skips_children(client, records):
    child = records['customers'][0]
    assert link(client, child['id'], records['main']).status_code == 200
    third = records['customers'][1]['id']
    candidates = client.get(f'/api/feedback/{third}/duplicates/candidates', params={'q': records['main'][:8]}).json()
    assert [row['id'] for row in candidates] == [records['main']] and candidates[0]['version'] == 1
    assert all(row['id'] != child['id'] for row in client.get(f'/api/feedback/{third}/duplicates/candidates').json())
    assert client.get(f'/api/feedback/{third}/duplicates/candidates', params={'q':'%'}).json() == []
    assert client.get(f'/api/feedback/{third}/duplicates/candidates', params={'q':'x'*121}).status_code == 422


def test_shared_updates_are_separate_safe_messages_and_retry_safe(client, records):
    linked(client, records)
    main = records['main']
    client.post(f'/api/feedback/{main}/messages', json={'body':'Private root note never copied', 'visibility':'internal'})
    client.post(f'/api/public/submissions/{records["customers"][0]["token"]}/messages', json={'body':'My private customer conversation'})
    payload = {'version': group(client, main)['version'], 'request_id': str(uuid4()), 'body':'Checkout fix is being tested.'}
    for _ in range(2):
        result = client.post(f'/api/feedback/{main}/duplicates/updates', json=payload)
        assert result.status_code == 200 and result.json()['updated_count'] == 3
    for customer in records['customers']:
        messages = client.get(f'/api/public/submissions/{customer["token"]}/messages').json()
        assert sum(row['body'] == payload['body'] for row in messages) == 1
        assert all(row['body'] != 'Private root note never copied' for row in messages)
    other = client.get(f'/api/public/submissions/{records["customers"][1]["token"]}/messages').json()
    assert all(row['body'] != 'My private customer conversation' for row in other)
    assert client.post(f'/api/feedback/{main}/duplicates/updates', json={**payload,'body':'Different content'}).status_code == 409
    assert client.post(f'/api/feedback/{records["customers"][0]["id"]}/duplicates/updates', json={**payload, 'request_id':str(uuid4())}).status_code == 409


def test_shared_work_and_retest_preserve_priority_and_individual_confirmations(client, records, employee):
    linked(client, records)
    main = records['main']; first, second = records['customers']
    assert client.patch(f'/api/feedback/{first["id"]}/triage', json={'version':0,'priority':'urgent','due_date':'2026-11-01'}).status_code == 200
    assert shared(client, main, employee, status='ready_to_retest').status_code == 422
    assert shared(client, main, employee).status_code == 200
    current = group(client, main)
    payload = {'version':current['version'],'request_id':str(uuid4()),'assigned_employee_id':employee,'status':'ready_to_retest',
        'note':'We fixed checkout. Repeat the original payment steps.', 'report_versions':{row['id']:row['workflow']['version'] for row in current['members']}}
    for _ in range(2):
        assert client.post(f'/api/feedback/{main}/duplicates/workflow', json=payload).status_code == 200
    public = client.get(f'/api/public/submissions/{first["token"]}').json()['workflow']
    assert public['status'] == 'ready_to_retest'
    assert client.post(f'/api/public/submissions/{first["token"]}/retest', json={'version':public['retest_version'],'outcome':'works'}).status_code == 200
    other = client.get(f'/api/public/submissions/{second["token"]}').json()['workflow']
    assert other['status'] == 'ready_to_retest'
    assert client.post(f'/api/public/submissions/{second["token"]}/retest', json={'version':other['retest_version'],'outcome':'still_happening','note':'Payment still fails.'}).status_code == 200
    confirmed = client.get(f'/api/feedback/{first["id"]}/workflow').json()
    assert confirmed['status'] == 'resolved' and confirmed['priority'] == 'urgent' and confirmed['due_date'] == '2026-11-01'
    assert shared(client, main, employee).json()['updated_count'] == 2
    assert client.get(f'/api/feedback/{first["id"]}/workflow').json() == confirmed
    assert client.get('/api/health').json()['usage']['attempts'] == 0


def test_main_customer_confirmation_does_not_block_remaining_shared_retests(client, records, employee):
    first, second = records['customers']
    assert link(client, second['id'], first['id']).status_code == 200
    assert shared(client, first['id'], employee).status_code == 200
    assert shared(client, first['id'], employee, status='ready_to_retest').status_code == 200
    public = client.get(f'/api/public/submissions/{first["token"]}').json()['workflow']
    assert client.post(f'/api/public/submissions/{first["token"]}/retest', json={'version':public['retest_version'],'outcome':'works'}).status_code == 200
    assert shared(client, first['id'], employee).json()['updated_count'] == 1
    assert shared(client, first['id'], employee, status='ready_to_retest').status_code == 200
    assert client.get(f'/api/public/submissions/{first["token"]}').json()['workflow']['status'] == 'resolved'
    assert client.get(f'/api/public/submissions/{second["token"]}').json()['workflow']['status'] == 'ready_to_retest'


def test_stale_member_or_group_versions_roll_back_entire_shared_action(client, records, employee):
    linked(client, records); main = records['main']
    current = group(client, main)
    payload = {'version':current['version'],'request_id':str(uuid4()),'assigned_employee_id':employee,'status':'in_progress',
        'note':'Start a shared fix','report_versions':{row['id']:row['workflow']['version'] for row in current['members']}}
    child = records['customers'][1]['id']
    assert patch(client, child, employee=employee).status_code == 200
    before = group(client, main)
    assert client.post(f'/api/feedback/{main}/duplicates/workflow', json=payload).status_code == 409
    assert group(client, main) == before
    payload['report_versions'].pop(child)
    assert client.post(f'/api/feedback/{main}/duplicates/workflow', json=payload).status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(DuplicateAction)) == 0


def test_invalid_shared_owner_and_blank_updates_do_not_mutate_group(client, records, employee):
    linked(client, records); main = records['main']; before = group(client, main)
    assert shared(client, main, 'missing').status_code == 422
    assert shared(client, main, employee, note='   ').status_code == 422
    assert client.post(f'/api/feedback/{main}/duplicates/updates', json={'version':before['version'],'request_id':str(uuid4()),'body':'  '}).status_code == 422
    assert group(client, main) == before


def test_unlink_and_delete_preserve_other_reports_and_prevent_linked_project_moves(client, records, employee):
    linked(client, records); main = records['main']; first, second = records['customers']
    shared(client, main, employee)
    other_project = client.post('/api/projects', json={'name':'Destination'}).json()
    assert client.put(f'/api/feedback/{main}', json={'project_id':other_project['id'],'text':'Move report'}).status_code == 409
    before = client.get(f'/api/feedback/{first["id"]}').json()
    assert client.delete(f'/api/feedback/{second["id"]}').status_code == 200
    assert len(group(client, main)['members']) == 2
    assert client.delete(f'/api/feedback/{main}').status_code == 200
    after = client.get(f'/api/feedback/{first["id"]}').json()
    assert after['duplicate_group'] is None and after['workflow'] == before['workflow'] and after['text'] == before['text']
    with database() as db:
        assert db.scalar(select(func.count()).select_from(DuplicateGroup)) == 0
        assert db.scalar(select(func.count()).select_from(DuplicateMember)) == 0
        assert db.scalar(select(func.count()).select_from(DuplicateAction)) == 0


def test_unlink_checks_version_and_cleans_up_last_pair(client, records):
    child = records['customers'][0]['id']; main = records['main']
    assert link(client, child, main).status_code == 200
    assert client.request('DELETE', f'/api/feedback/{child}/duplicates', json={'version':0}).status_code == 409
    assert client.request('DELETE', f'/api/feedback/{child}/duplicates', json={'version':1}).status_code == 200
    assert group(client, main) is None and group(client, child) is None
    assert client.put(f'/api/feedback/{main}', json={'project_id':records['project'],'text':'Still editable'}).status_code == 200


def test_group_size_limit_rolls_back_membership_and_version(client, records, monkeypatch):
    import app.duplicates as duplicates
    monkeypatch.setattr(duplicates, 'MAX_MEMBERS', 2)
    first, second = records['customers']
    assert link(client, first['id'], records['main']).status_code == 200
    before = group(client, records['main'])
    assert link(client, second['id'], records['main'], version=1).status_code == 422
    assert group(client, records['main']) == before
    assert group(client, second['id']) is None


def test_shared_notifications_stay_individual_and_private(client, people):
    first = people['records'][0]; alpha = people['projects'][0]['id']
    customer = people['customers'][1]
    email = 'customer1@project.test'
    assert client.post(f'/api/projects/{alpha}/members/customer', json={'email':email}).status_code == 200
    result = customer.post(f'/api/public/intake/{first["link"]}/submissions', json={
        'text':'A separate customer with the same bug', 'client_nonce':'notified-duplicate-customer-12345'}).json()
    assert customer.post(f'/api/public/submissions/{result["access_token"]}/submit', json={'draft_version': customer.get((f"/api/public/submissions/{result['access_token']}/submit").removesuffix('/submit')).json().get('draft_version', 1)}).status_code == 200
    with database() as db:
        fid = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == result['access_token']))
    assert link(client, fid, first['id']).status_code == 200
    payload = {'version':1,'request_id':str(uuid4()),'body':'A customer-safe shared update'}
    assert client.post(f'/api/feedback/{first["id"]}/duplicates/updates', json=payload).status_code == 200
    own = people['customers'][0].get('/api/auth/notifications/customer').json()['items']
    other = customer.get('/api/auth/notifications/customer').json()['items']
    assert any(n['url'].endswith(first['token']) and n['title'].startswith('Company replied') for n in own)
    assert not any(n['url'].endswith(result['access_token']) for n in own)
    assert any(n['url'].endswith(result['access_token']) and n['title'].startswith('Company replied') for n in other)
    assert not any(n['url'].endswith(first['token']) for n in other)
    assert 'duplicate_group' not in str(customer.get('/api/customer/reports').json())
