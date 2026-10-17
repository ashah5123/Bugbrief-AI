"""Company planning stays private and reply queues reflect public activity."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import Feedback, IssueProgress, IssueEvent
from test_workflow import customer_report, employee, database, patch


def triage(client, fid, version=0, priority='high', due_date='2026-10-20'):
    return client.patch(f'/api/feedback/{fid}/triage', json={
        'version': version, 'priority': priority, 'due_date': due_date})


def test_triage_defaults_and_persistence_do_not_change_evidence(client, draft):
    before = client.get(f'/api/feedback/{draft["id"]}').json()
    assert before['workflow']['priority'] == 'normal'
    assert before['workflow']['due_date'] is None and before['workflow']['waiting_since'] is None
    response = triage(client, draft['id'], priority='urgent', due_date='2020-02-29')
    assert response.status_code == 200
    value = response.json()
    assert value['priority'] == 'urgent' and value['due_date'] == '2020-02-29'
    assert value['version'] == 1
    after = client.get(f'/api/feedback/{draft["id"]}').json()
    assert after['workflow'] == value
    assert {k: v for k, v in after.items() if k != 'workflow'} == {k: v for k, v in before.items() if k != 'workflow'}
    assert triage(client, draft['id'], version=1, priority='urgent', due_date='2020-02-29').json() == value
    cleared = triage(client, draft['id'], version=1, priority='low', due_date=None).json()
    assert cleared['due_date'] is None and cleared['priority'] == 'low' and cleared['version'] == 2
    progress = patch(client, draft['id'], version=2, note='A public update after planning').json()
    assert progress['events'][0]['label'] == 'Report received'
    assert progress['events'][-1]['note'] == 'A public update after planning'


@pytest.mark.parametrize('due', ['2026-02-29', '2026-13-01', '2026-01-32', '20261020', '2026-1-01', '', 'today', '2026-10-20T00:00:00Z'])
def test_invalid_calendar_dates_rejected(client, draft, due):
    assert triage(client, draft['id'], due_date=due).status_code == 422
    assert client.get(f'/api/feedback/{draft["id"]}/workflow').json()['version'] == 0


def test_priority_validation_and_version_conflicts(client, draft):
    assert triage(client, draft['id'], priority='critical').status_code == 422
    first = triage(client, draft['id']).json()
    assert triage(client, draft['id'], priority='urgent').status_code == 409
    assert patch(client, draft['id'], note='Stale progress').status_code == 409
    current = patch(client, draft['id'], version=first['version'], note='Current public update').json()
    assert current['priority'] == 'high' and current['due_date'] == '2026-10-20'
    assert triage(client, draft['id'], version=first['version']).status_code == 409


def test_triage_private_to_company_and_access_enforced(client, customer_report):
    fid = customer_report['id']
    result = triage(client, fid).json()
    assert result['waiting_since']
    with TestClient(app) as outsider:
        assert triage(outsider, fid).status_code == 401
        public = outsider.get(f'/api/public/submissions/{customer_report["token"]}').json()['workflow']
        assert not {'priority', 'due_date', 'waiting_since', 'version'} & public.keys()
        assert not any('priority' in event['label'].lower() for event in public['events'])
    with database() as db:
        record = db.get(Feedback, fid)
        record.deleted_at = '2026-10-01'
        db.commit()
    assert triage(client, fid, version=1).status_code == 404


def test_waiting_queue_ignores_assignment_private_notes_and_triage(client, customer_report, employee):
    fid, token = customer_report['id'], customer_report['token']
    workflow = client.get(f'/api/feedback/{fid}/workflow').json()
    since = workflow['waiting_since']
    assert since
    workflow = patch(client, fid, employee=employee).json()
    assert workflow['waiting_since'] == since
    client.post(f'/api/feedback/{fid}/messages', json={'body': 'Investigating privately', 'visibility': 'internal'})
    workflow = triage(client, fid, version=workflow['version']).json()
    assert workflow['waiting_since'] == since
    client.post(f'/api/feedback/{fid}/messages', json={'body': 'We have received your report.'})
    assert client.get(f'/api/feedback/{fid}/workflow').json()['waiting_since'] is None
    with TestClient(app) as customer:
        assert customer.post(f'/api/public/submissions/{token}/messages', json={'body': 'Any news?'}).status_code == 201
    workflow = client.get(f'/api/feedback/{fid}/workflow').json()
    assert workflow['waiting_since'] > since
    workflow = patch(client, fid, version=workflow['version'], employee=employee, status='in_progress', note='We are working on it.').json()
    assert workflow['waiting_since'] is None


def test_unavailable_project_and_unsent_draft_cannot_be_triaged(client, draft):
    from app.models import EmployeeAccount, EmployeeSession
    from hashlib import sha256
    from secrets import token_urlsafe
    token = token_urlsafe(32)
    from time import time
    with database() as db:
        employee = EmployeeAccount(name='Other project employee', email='other@example.test', password_hash='unused')
        db.add(employee); db.flush()
        db.add(EmployeeSession(token_hash=sha256(token.encode()).hexdigest(), account_id=employee.id, expires_at=time()+3600))
        db.commit()
    with TestClient(app) as other:
        other.cookies.set('bugbrief_employee', token)
        assert triage(other, draft['id']).status_code == 404
    link = client.post(f'/api/projects/{draft["project_id"]}/intake-link', json={}).json()['token']
    pending = client.post(f'/api/public/intake/{link}/submissions', json={'client_nonce': 'triage-pending-nonce-123456', 'text': 'Private draft'}).json()
    with database() as db:
        from app.models import CustomerSubmission
        from sqlalchemy import select
        fid = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == pending['access_token']))
    assert triage(client, fid).status_code == 404
