"""Workflow authorization, transitions, concurrency and evidence independence."""
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.db import get_db
from app.models import EmployeeAccount, CustomerAccount, IssueEvent, IssueProgress, Feedback, Project, EmployeeProject
from app.customer_auth import password_hash


def database():
    return contextmanager(app.dependency_overrides[get_db])()


@pytest.fixture
def employee(client):
    with database() as db:
        row = EmployeeAccount(name='Assigned Employee', email='assigned@example.com', password_hash='unused-test-hash')
        db.add(row); db.flush()
        for project_id in db.scalars(select(Project.id)).all():
            db.add(EmployeeProject(employee_id=row.id, project_id=project_id))
        db.commit()
        return row.id


def patch(client, feedback_id, version=0, status='new', employee=None, note=''):
    return client.patch(f'/api/feedback/{feedback_id}/workflow', json={
        'version': version, 'status': status, 'assigned_employee_id': employee, 'note': note})


@pytest.fixture
def customer_report(client):
    project = client.post('/api/projects', json={'name': 'Tracked customer project'}).json()
    link = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()
    record = client.post(f'/api/public/intake/{link["token"]}/submissions', json={
        'client_nonce': 'tracked-customer-nonce-123456', 'text': 'The checkout button fails.'}).json()
    client.post(f'/api/public/submissions/{record["access_token"]}/submit', json={})
    feedback = client.get('/api/feedback').json()[0]
    return {'id': feedback['id'], 'token': record['access_token'], 'link': link['token'], 'project': project['id']}


def test_existing_feedback_has_safe_default_progress_without_get_mutation(client, draft):
    value = client.get(f'/api/feedback/{draft["id"]}/workflow').json()
    assert value['status'] == 'new' and value['version'] == 0 and value['assigned_to'] is None
    assert value['events'][0]['label'] == 'Report received'
    with database() as db:
        assert db.scalar(select(func.count()).select_from(IssueProgress)) == 0
        assert db.scalar(select(func.count()).select_from(IssueEvent)) == 0


def test_workflow_and_employee_directory_require_company_access(client, draft, employee):
    with TestClient(app) as outsider:
        assert outsider.get('/api/employees').status_code == 401
        assert outsider.get(f'/api/feedback/{draft["id"]}/workflow').status_code == 401
        assert patch(outsider, draft['id'], employee=employee).status_code == 401
        outsider.post('/api/customer/register', json={'name': 'Customer', 'email': 'c@example.com', 'password': 'A customer password phrase.'})
        assert outsider.get('/api/employees').status_code == 401
        assert patch(outsider, draft['id'], employee=employee).status_code == 401
    assert client.get('/api/employees').json() == [{'id': employee, 'name': 'Assigned Employee', 'project_ids': [draft['project_id']]}]


def test_assign_progress_and_reopen_without_altering_report_version(client, draft, employee, report_data):
    saved = client.put(f'/api/feedback/{draft["id"]}/report', json={'version': draft['version'], 'report': report_data}).json()
    original_version = saved['version']
    value = patch(client, draft['id'], employee=employee).json()
    assert value['version'] == 1 and value['assigned_to']['name'] == 'Assigned Employee'
    for status in ['in_progress', 'ready_to_retest', 'resolved', 'in_progress']:
        response = patch(client, draft['id'], version=value['version'], status=status, employee=employee, note='A public progress update.')
        assert response.status_code == 200
        value = response.json()
        assert value['status'] == status
    assert value['events'][-1]['label'] == 'Report reopened'
    unchanged = client.get(f'/api/feedback/{draft["id"]}').json()
    assert unchanged['report'] == saved['report'] and unchanged['version'] == original_version
    assert unchanged['status'] == 'review' and unchanged['text'] == saved['text']


@pytest.mark.parametrize('status', ['in_progress', 'ready_to_retest', 'resolved'])
def test_cannot_start_or_close_without_employee(client, draft, status):
    assert patch(client, draft['id'], status=status).status_code == 422


@pytest.mark.parametrize('status', ['ready_to_retest', 'resolved', 'invented'])
def test_invalid_status_or_skipped_transition_rejected(client, draft, employee, status):
    assert patch(client, draft['id'], status=status, employee=employee).status_code == 422


def test_invalid_assignee_and_customer_id_are_rejected(client, draft):
    with database() as db:
        customer = CustomerAccount(name='Customer', email='customer@example.com', password_hash='unused')
        db.add(customer); db.commit(); account_id = customer.id
    assert patch(client, draft['id'], employee='').status_code == 422
    assert patch(client, draft['id'], employee='missing').status_code == 422
    assert patch(client, draft['id'], employee=account_id).status_code == 422


def test_needs_information_requires_visible_question_and_records_history(client, draft):
    assert patch(client, draft['id'], status='needs_information').status_code == 422
    response = patch(client, draft['id'], status='needs_information', note=' Which browser did you use? ')
    assert response.status_code == 200
    value = response.json()
    assert value['events'][-1]['note'] == 'Which browser did you use?'
    assert value['status'] == 'needs_information'


def test_stale_update_cannot_overwrite_other_employee_or_append_history(client, draft, employee):
    first = patch(client, draft['id'], employee=employee).json()
    stale = patch(client, draft['id'], employee=None, note='Stale note')
    assert stale.status_code == 409
    current = client.get(f'/api/feedback/{draft["id"]}/workflow').json()
    assert current == first
    unchanged = patch(client, draft['id'], version=first['version'], employee=employee).json()
    assert unchanged == first


def test_customer_tracking_is_read_only_minimal_and_scoped(client, customer_report, employee):
    value = patch(client, customer_report['id'], status='in_progress', employee=employee, note='We are investigating checkout.').json()
    with TestClient(app) as customer:
        response = customer.get(f'/api/public/submissions/{customer_report["token"]}')
        progress = response.json()['workflow']
        assert progress['status'] == 'in_progress' and progress['assigned_to'] == {'name': 'Assigned Employee'}
        assert 'version' not in progress and 'assigned_employee_id' not in progress
        assert 'assigned@example.com' not in response.text and 'password_hash' not in response.text
        assert 'report' not in response.json()
        assert customer.patch(f'/api/public/submissions/{customer_report["token"]}', json={'workflow': {'status': 'resolved'}}).status_code == 405
        assert patch(customer, customer_report['id'], version=value['version'], status='resolved', employee=employee).status_code == 401
        assert customer.get(f'/api/public/submissions/{customer_report["link"]}').status_code == 404


def test_pending_customer_drafts_cannot_be_tracked_by_company(client):
    project = client.post('/api/projects', json={'name': 'Pending'}).json()
    token = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()['token']
    record = client.post(f'/api/public/intake/{token}/submissions', json={'client_nonce': 'pending-workflow-nonce-12345', 'text': 'Not sent yet'}).json()
    assert record['workflow'] is None
    with database() as db:
        feedback_id = db.scalar(select(Feedback.id))
    assert patch(client, feedback_id).status_code == 404


def test_report_edit_and_progress_update_do_not_clobber_each_other(client, draft, employee, report_data):
    first = patch(client, draft['id'], status='in_progress', employee=employee).json()
    saved = client.put(f'/api/feedback/{draft["id"]}/report', json={'version': draft['version'], 'report': report_data}).json()
    assert saved['workflow'] == first
    changed = client.put(f'/api/feedback/{draft["id"]}', json={'project_id': draft['project_id'], 'text': 'More original details.'}).json()
    assert changed['workflow'] == first
    assert client.get('/api/health').json()['usage']['attempts'] == 0


def test_deletion_erases_public_history_and_assignment(client, draft, employee):
    patch(client, draft['id'], employee=employee, note='Erase this public update too.')
    assert client.delete(f'/api/feedback/{draft["id"]}').status_code == 200
    assert client.get(f'/api/feedback/{draft["id"]}/workflow').status_code == 404
    assert patch(client, draft['id']).status_code == 404
    with database() as db:
        assert db.scalar(select(func.count()).select_from(IssueEvent)) == 0
        assert db.scalar(select(func.count()).select_from(IssueProgress)) == 0
