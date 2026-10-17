"""Privacy, retest concurrency, and account/team security integration checks."""
import hashlib
import re
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import AccountAction, MailMessage, EmployeeAccount, ReportMessage, IssueProgress
from app.customer_auth import _attempts
from test_workflow import customer_report, employee, patch, database

PASSWORD = 'Account management test phrase!'


def mail_token(client, kind, email=None):
    messages = client.get('/api/team/outbox').json()
    message = next(m for m in messages if f'/{kind}/' in m['body'] and (email is None or m['recipient'] == email))
    return re.search(r'/(?:reset|verify|invite)/([A-Za-z0-9_-]{43})', message['body'])[1]


def register(person, scope, email='person@example.com'):
    data = {'name': 'Test Person', 'email': email, 'password': PASSWORD}
    if scope == 'employee':
        data['workspace_code'] = 'test-agency-access-code'
    return person.post('/api/customer/register' if scope == 'customer' else '/api/auth/employee/register', json=data)


def test_replies_and_private_notes_are_separated_and_erased(client, customer_report):
    fid, token = customer_report['id'], customer_report['token']
    endpoint = f'/api/feedback/{fid}/messages'
    public = f'/api/public/submissions/{token}/messages'
    assert client.post(endpoint, json={'body': 'Please try Safari.'}).status_code == 201
    assert client.post(endpoint, json={'body': 'Private billing detail', 'visibility': 'internal'}).status_code == 201
    with TestClient(app) as customer:
        values = customer.get(public).json()
        assert len(values) == 1 and values[0]['body'] == 'Please try Safari.'
        assert 'Private billing detail' not in customer.get(f'/api/public/submissions/{token}').text
        assert customer.get(endpoint).status_code == 401
        assert customer.post(public, json={'body': 'Fake private note', 'visibility': 'internal'}).status_code == 403
        assert customer.post(public, json={'body': 'Safari still fails.'}).status_code == 201
        assert len(customer.get(public).json()) == 2
        assert customer.get('/api/public/submissions/' + 'x'*43 + '/messages').status_code == 404
    values = client.get(endpoint).json()
    assert len(values) == 3 and values[-1]['author_role'] == 'customer'
    client.delete(f'/api/feedback/{fid}')
    assert client.get(endpoint).status_code == 404
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReportMessage)) == 0


def test_owned_report_conversation_is_inaccessible_to_other_customer(client, customer_report):
    token = customer_report['token']
    with TestClient(app) as first, TestClient(app) as other:
        register(first, 'customer', 'first@example.com')
        assert first.post('/api/customer/claims', json={'token': token}).status_code == 200
        register(other, 'customer', 'other@example.com')
        public = f'/api/public/submissions/{token}/messages'
        assert first.post(public, json={'body': 'My report details.'}).status_code == 201
        assert other.get(public).status_code == 404
        assert other.post(public, json={'body': 'Not mine'}).status_code == 404
        assert other.post(f'/api/public/submissions/{token}/retest', json={'version': 1, 'outcome': 'works'}).status_code == 404


def test_customer_can_reject_then_confirm_new_fix_without_stale_confirmation(client, customer_report, employee):
    fid, token = customer_report['id'], customer_report['token']
    original = client.get(f'/api/feedback/{fid}').json()['version']
    value = patch(client, fid, status='in_progress', employee=employee).json()
    value = patch(client, fid, version=value['version'], status='ready_to_retest', employee=employee).json()
    with TestClient(app) as customer:
        public = customer.get(f'/api/public/submissions/{token}').json()['workflow']
        assert public['retest_version'] == value['version'] and 'version' not in public
        endpoint = f'/api/public/submissions/{token}/retest'
        assert customer.post(endpoint, json={'version': value['version'], 'outcome': 'still_happening'}).status_code == 422
        result = customer.post(endpoint, json={'version': value['version'], 'outcome': 'still_happening', 'note': 'Still fails on Safari.'})
        assert result.status_code == 200 and result.json()['status'] == 'in_progress'
        assert customer.post(endpoint, json={'version': value['version'], 'outcome': 'works'}).status_code == 409
        value = patch(client, fid, version=value['version']+1, status='ready_to_retest', employee=employee).json()
        assert customer.post(endpoint, json={'version': value['version']-2, 'outcome': 'works'}).status_code == 409
        result = customer.post(endpoint, json={'version': value['version'], 'outcome': 'works'})
        assert result.json()['status'] == 'resolved'
        assert result.json()['events'][-1]['label'] == 'Customer confirmed the fix'
    assert client.get(f'/api/feedback/{fid}').json()['version'] == original


@pytest.mark.parametrize('scope', ['customer', 'employee'])
def test_recovery_is_generic_one_use_expires_and_revokes_sessions(client, scope):
    with TestClient(app) as person:
        assert register(person, scope).status_code == 201
        endpoint = f'/api/auth/accounts/{scope}'
        known = person.post(endpoint + '/recover', json={'email': 'person@example.com'})
        unknown = person.post(endpoint + '/recover', json={'email': 'unknown@example.com'})
        assert known.json() == unknown.json()
        token = mail_token(client, 'reset')
        with database() as db:
            action = db.get(AccountAction, hashlib.sha256(token.encode()).hexdigest())
            assert action and action.email == 'person@example.com'
            assert token != action.token_hash
        other_scope = 'employee' if scope == 'customer' else 'customer'
        assert person.post(f'/api/auth/accounts/{other_scope}/reset/complete', json={'token': token, 'password': PASSWORD}).status_code == 400
        new_password = 'My replacement password phrase!'
        assert person.post(endpoint + '/reset/complete', json={'token': token, 'password': new_password}).status_code == 200
        session = person.get('/api/customer/session' if scope == 'customer' else '/api/auth/session').json()
        assert session['authenticated'] is False
        assert person.post(endpoint + '/reset/complete', json={'token': token, 'password': PASSWORD}).status_code == 400
        login = '/api/customer/login' if scope == 'customer' else '/api/auth/employee/login'
        assert person.post(login, json={'email': 'person@example.com', 'password': PASSWORD}).status_code == 401
        assert person.post(login, json={'email': 'person@example.com', 'password': new_password}).status_code == 200
        person.post(endpoint + '/recover', json={'email': 'person@example.com'})
        expired = mail_token(client, 'reset')
        with database() as db:
            db.get(AccountAction, hashlib.sha256(expired.encode()).hexdigest()).expires_at = time.time()-1
            db.commit()
        assert person.post(endpoint + '/reset/complete', json={'token': expired, 'password': PASSWORD}).status_code == 400


@pytest.mark.parametrize('scope', ['customer', 'employee'])
def test_email_verification_is_scoped_and_one_use(client, scope):
    with TestClient(app) as person:
        response = register(person, scope)
        assert response.json()[scope]['email_verified'] is False
        token = mail_token(client, 'verify')
        endpoint = f'/api/auth/accounts/{scope}/verify/complete'
        assert person.post(endpoint, json={'token': token}).status_code == 200
        assert person.post(endpoint, json={'token': token}).status_code == 400
        session = person.get('/api/customer/session' if scope == 'customer' else '/api/auth/session').json()
        assert session[scope]['email_verified'] is True


def test_individual_invitation_owner_only_email_bound_revocable_and_one_use(client, employee):
    email = 'invited@example.com'
    with TestClient(app) as outsider:
        assert outsider.post('/api/auth/employee/register', json={'name': 'New', 'email': email, 'password': PASSWORD, 'workspace_code': 'test-agency-access-code'}).status_code == 403
        assert outsider.get('/api/team/outbox').status_code == 401
        assert client.post('/api/team/invitations', json={'email': email}).status_code == 201
        token = mail_token(client, 'invite', email)
        assert outsider.post('/api/auth/employee/register', json={'name': 'New', 'email': 'wrong@example.com', 'password': PASSWORD, 'workspace_code': token}).status_code == 403
        good = {'name': 'New', 'email': email, 'password': PASSWORD, 'workspace_code': token}
        assert outsider.post('/api/auth/employee/register', json=good).status_code == 201
        assert outsider.get('/api/team').json()['can_manage'] is False
        assert outsider.get('/api/team/outbox').status_code == 403
        assert outsider.post('/api/team/invitations', json={'email': 'other@example.com'}).status_code == 403
        assert outsider.delete(f'/api/team/employees/{employee}').status_code == 403
        assert outsider.post('/api/auth/employee/register', json=good).status_code == 403
    client.post('/api/team/invitations', json={'email': 'revoke@example.com'})
    token = mail_token(client, 'invite', 'revoke@example.com')
    invitation = client.get('/api/team').json()['invitations'][0]
    assert client.delete('/api/team/invitations/' + invitation['id']).status_code == 200
    with TestClient(app) as outsider:
        assert outsider.post('/api/auth/employee/register', json={'name':'No','email':'revoke@example.com','password':PASSWORD,'workspace_code':token}).status_code == 403


def test_removed_employee_loses_session_assignment_login_and_reset_access(client, draft):
    with TestClient(app) as employee:
        result = register(employee, 'employee').json()
        employee_id = result['employee']['id']
        assert client.post(f'/api/projects/{draft["project_id"]}/members/employee', json={'email':'person@example.com'}).status_code == 200
        patch(client, draft['id'], status='in_progress', employee=employee_id)
        assert client.delete(f'/api/team/employees/{employee_id}').status_code == 200
        assert employee.get('/api/projects').status_code == 401
        assert employee.post('/api/auth/employee/login', json={'email': 'person@example.com', 'password': PASSWORD}).status_code == 401
        assert client.get('/api/employees').json() == []
        state = client.get(f'/api/feedback/{draft["id"]}/workflow').json()
        assert state['assigned_employee_id'] is None and state['status'] == 'in_progress'
        assert patch(client, draft['id'], version=state['version'], status='in_progress', employee=employee_id).status_code == 422
        before = len(client.get('/api/team/outbox').json())
        employee.post('/api/auth/accounts/employee/recover', json={'email': 'person@example.com'})
        assert len(client.get('/api/team/outbox').json()) == before
        assert client.post(f'/api/team/employees/{employee_id}/restore').status_code == 200
        assert employee.get('/api/projects').status_code == 401
        assert employee.post('/api/auth/employee/login', json={'email':'person@example.com','password':PASSWORD}).status_code == 200


def test_smtp_requires_tls_and_outbox_retains_no_security_link(client, monkeypatch):
    from app.config import settings
    from app import account_management
    events = []
    class Sender:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('smtp.example.test', 587, 10)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, context):
            events.append('tls')
        def login(self, username, password):
            assert events == ['tls']
            events.append('login')
        def send_message(self, message):
            assert events == ['tls', 'login']
            assert '#customer/verify/' in message.get_content()
            events.append('sent')
    monkeypatch.setattr(settings, 'mail_mode', 'smtp')
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.example.test')
    monkeypatch.setattr(settings, 'smtp_from', 'sender@example.test')
    monkeypatch.setattr(settings, 'smtp_username', 'sender')
    monkeypatch.setattr(settings, 'smtp_password', 'test-only')
    monkeypatch.setattr(account_management.smtplib, 'SMTP', Sender)
    with TestClient(app) as person:
        assert register(person, 'customer').status_code == 201
    assert events == ['tls', 'login', 'sent']
    message = client.get('/api/team/outbox').json()[0]
    assert message['delivery'] == 'sent' and message['body'] == ''


def test_failed_smtp_is_visible_to_owner_without_exposing_reset_link(client, monkeypatch):
    from app.config import settings
    from app import account_management
    monkeypatch.setattr(settings, 'mail_mode', 'smtp')
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.example.test')
    monkeypatch.setattr(settings, 'smtp_from', 'sender@example.test')
    def unavailable(*args, **kwargs):
        raise OSError('Connection unavailable')
    monkeypatch.setattr(account_management.smtplib, 'SMTP', unavailable)
    with TestClient(app) as person:
        assert register(person, 'customer').status_code == 201
        assert person.post('/api/auth/accounts/customer/recover', json={'email':'person@example.com'}).status_code == 200
    assert all(m['delivery'] == 'failed' and not m['body'] for m in client.get('/api/team/outbox').json())


def test_reissuing_security_link_invalidates_old_token(client):
    with TestClient(app) as person:
        register(person, 'customer')
        person.post('/api/auth/accounts/customer/recover', json={'email':'person@example.com'})
        old = mail_token(client, 'reset')
        person.post('/api/auth/accounts/customer/recover', json={'email':'person@example.com'})
        new = mail_token(client, 'reset')
        assert old != new
        assert person.post('/api/auth/accounts/customer/reset/complete', json={'token':old,'password':PASSWORD}).status_code == 400
        assert person.post('/api/auth/accounts/customer/reset/complete', json={'token':new,'password':PASSWORD}).status_code == 200
