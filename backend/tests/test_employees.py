"""Invited employee access and isolation from customer credentials."""
from contextlib import contextmanager
import hashlib
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import get_db
from app.models import EmployeeAccount, EmployeeSession
from app.employee_auth import COOKIE
from app.customer_auth import password_matches

PASSWORD = 'A personal employee phrase 42!'
CODE = 'test-agency-access-code'


def database():
    return contextmanager(app.dependency_overrides[get_db])()


def registration(**changes):
    return {'name': 'Alex Employee', 'email': 'alex@example.com', 'password': PASSWORD,
            'workspace_code': CODE, **changes}


def test_employee_registration_requires_workspace_invitation(client):
    with TestClient(app) as employee:
        assert employee.post('/api/auth/employee/register', json=registration(workspace_code='wrong')).status_code == 403
        assert employee.get('/api/projects').status_code == 401
        response = employee.post('/api/auth/employee/register', json=registration())
        assert response.status_code == 201
        assert response.json()['employee']['name'] == 'Alex Employee'
        assert 'workspace_code' not in response.text and 'password' not in response.text
        assert employee.get('/api/projects').status_code == 200
        assert employee.get('/api/auth/session').json()['employee']['email'] == 'alex@example.com'
        assert employee.get('/api/customer/reports').status_code == 401


def test_employee_credentials_and_session_tokens_are_hashed(client):
    with TestClient(app) as employee:
        response = employee.post('/api/auth/employee/register', json=registration(email=' ALEX@Example.com '))
        assert response.status_code == 201
        cookie = response.headers.get_list('set-cookie')[-1].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        raw = employee.cookies.get(COOKIE)
        with database() as db:
            account = db.scalar(select(EmployeeAccount))
            session = db.scalar(select(EmployeeSession))
            assert account.email == 'alex@example.com' and account.password_hash != PASSWORD
            assert password_matches(PASSWORD, account.password_hash)
            assert session.token_hash == hashlib.sha256(raw.encode()).hexdigest()
            assert session.expires_at > time.time()


@pytest.mark.parametrize('changes', [
    {'name': '   '}, {'password': 'short'}, {'password': 'x'*129}, {'email': 'invalid'}, {'role': 'admin'}])
def test_employee_registration_validation(client, changes):
    with TestClient(app) as employee:
        assert employee.post('/api/auth/employee/register', json=registration(**changes)).status_code in (400, 422)


def test_duplicate_employee_cannot_replace_original_credentials(client):
    with TestClient(app) as employee:
        assert employee.post('/api/auth/employee/register', json=registration()).status_code == 201
        assert employee.post('/api/auth/employee/register', json=registration(name='Other', email='ALEX@example.com', password='Another employee phrase.')).status_code == 409
        with database() as db:
            account = db.scalar(select(EmployeeAccount))
            assert account.name == 'Alex Employee' and password_matches(PASSWORD, account.password_hash)


def test_employee_login_logout_revokes_cookie_and_relogin_rotates_session(client):
    with TestClient(app) as employee:
        employee.post('/api/auth/employee/register', json=registration())
        token = employee.cookies.get(COOKIE)
        assert employee.post('/api/auth/logout').status_code == 200
        employee.cookies.set(COOKIE, token)
        assert employee.get('/api/projects').status_code == 401
        assert employee.get('/api/auth/session').json() == {'authenticated': False}
        employee.cookies.clear()
        wrong = employee.post('/api/auth/employee/login', json={'email': 'alex@example.com', 'password': 'wrong'})
        unknown = employee.post('/api/auth/employee/login', json={'email': 'unknown@example.com', 'password': 'wrong'})
        assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
        assert employee.post('/api/auth/employee/login', json={'email': 'ALEX@example.com', 'password': PASSWORD}).status_code == 200
        assert employee.cookies.get(COOKIE) != token
        assert employee.get('/api/projects').status_code == 200


def test_expired_employee_session_cannot_fall_back_to_old_owner_cookie(client):
    with TestClient(app) as employee:
        assert employee.post('/api/auth/login', json={'code': CODE}).status_code == 200
        employee.post('/api/auth/employee/register', json=registration())
        assert not employee.cookies.get('bugbrief_agency')
        with database() as db:
            session = db.scalar(select(EmployeeSession))
            session.expires_at = time.time()-1
            db.commit()
        assert employee.get('/api/projects').status_code == 401
        employee.cookies.set(COOKIE, 'forged')
        assert employee.get('/api/auth/session').json() == {'authenticated': False}


def test_customer_and_employee_logins_are_separate_even_with_same_email(client):
    with TestClient(app) as person:
        assert person.post('/api/customer/register', json={'name': 'Customer', 'email': 'alex@example.com', 'password': 'A different customer phrase.'}).status_code == 201
        assert person.get('/api/projects').status_code == 401
        assert person.post('/api/auth/employee/login', json={'email': 'alex@example.com', 'password': 'A different customer phrase.'}).status_code == 401
        assert person.post('/api/auth/employee/register', json=registration()).status_code == 201
        assert person.get('/api/customer/session').json()['authenticated'] is True
        assert person.get('/api/projects').status_code == 200
        person.post('/api/auth/logout')
        assert person.get('/api/projects').status_code == 401
        assert person.get('/api/customer/session').json()['authenticated'] is True


def test_employee_can_manage_shared_projects_and_delete_workspace_reports(client):
    with TestClient(app) as employee:
        employee.post('/api/auth/employee/register', json=registration())
        project = employee.post('/api/projects', json={'name': 'Shared company project'}).json()
        feedback = client.post('/api/feedback', json={'project_id': project['id'], 'text': 'A report for the team.'}).json()
        assert employee.get(f'/api/feedback/{feedback["id"]}').status_code == 200
        assert employee.delete(f'/api/feedback/{feedback["id"]}').status_code == 200
        assert client.get(f'/api/feedback/{feedback["id"]}').status_code == 404


def test_employee_attempt_limits_and_origin_checks(client):
    with TestClient(app) as employee:
        for _ in range(5):
            assert employee.post('/api/auth/employee/register', json=registration(workspace_code='wrong')).status_code == 403
        assert employee.post('/api/auth/employee/register', json=registration()).status_code == 429
        for _ in range(8):
            assert employee.post('/api/auth/employee/login', json={'email': 'unknown@example.com', 'password': 'wrong'}).status_code == 401
        assert employee.post('/api/auth/employee/login', json={'email': 'unknown@example.com', 'password': 'wrong'}).status_code == 429
        assert employee.post('/api/auth/employee/login', json={'email': 'alex@example.com', 'password': PASSWORD}, headers={'Origin': 'https://untrusted.example'}).status_code == 403


def test_employee_cookie_secure_on_https(client):
    with TestClient(app, base_url='https://testserver') as employee:
        response = employee.post('/api/auth/employee/register', json=registration())
        assert response.status_code == 201
        assert 'secure' in response.headers.get_list('set-cookie')[-1].lower()
