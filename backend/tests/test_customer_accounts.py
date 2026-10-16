from contextlib import contextmanager
import hashlib
import secrets
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import get_db
from app.models import CustomerAccount, CustomerSession, CustomerSubmission
from app.customer_auth import COOKIE, password_hash, password_matches

PASSWORD = 'A long customer passphrase 32!'


def database():
    return contextmanager(app.dependency_overrides[get_db])()


def register(customer, email='new@example.com'):
    return customer.post('/api/customer/register', json={'name': 'New customer', 'email': email, 'password': PASSWORD})


@pytest.fixture
def invitation(client):
    project = client.post('/api/projects', json={'name': 'Private client project'}).json()
    link = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()
    return {**link, 'project_id': project['id']}


def create(customer, invitation, nonce=None):
    return customer.post(f'/api/public/intake/{invitation["token"]}/submissions', json={
        'client_nonce': nonce or secrets.token_urlsafe(24), 'text': 'The checkout button does not respond.'})


def test_registration_hashes_password_and_stores_only_hashed_session_token(client):
    with TestClient(app) as customer:
        response = register(customer, '  NEW@Example.com  ')
        assert response.status_code == 201
        data = response.json()
        assert data['customer']['email'] == 'new@example.com'
        assert 'password' not in str(data)
        cookie = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        token = customer.cookies.get(COOKIE)
        with database() as db:
            account = db.scalar(select(CustomerAccount))
            assert account.password_hash != PASSWORD and password_matches(PASSWORD, account.password_hash)
            session = db.scalar(select(CustomerSession))
            assert session.token_hash == hashlib.sha256(token.encode()).hexdigest()
            assert token not in session.token_hash and session.expires_at > time.time()
        assert customer.get('/api/customer/session').json()['authenticated'] is True
        assert customer.get('/api/feedback').status_code == 401


def test_login_logout_revocation_and_case_normalization(client):
    with TestClient(app) as customer:
        register(customer)
        old_cookie = customer.cookies.get(COOKIE)
        assert customer.post('/api/customer/logout').status_code == 200
        assert customer.get('/api/customer/session').json() == {'authenticated': False}
        customer.cookies.set(COOKIE, old_cookie)
        assert customer.get('/api/customer/reports').status_code == 401
        customer.cookies.clear()
        wrong = customer.post('/api/customer/login', json={'email': 'NEW@example.com', 'password': 'wrong'})
        absent = customer.post('/api/customer/login', json={'email': 'absent@example.com', 'password': 'wrong'})
        assert wrong.status_code == absent.status_code == 401 and wrong.json() == absent.json()
        assert customer.post('/api/customer/login', json={'email': 'NEW@example.com', 'password': PASSWORD}).status_code == 200
        assert customer.cookies.get(COOKIE) != old_cookie


def test_expired_forged_and_agency_sessions_do_not_authorize_customer_dashboard(client):
    assert client.get('/api/customer/reports').status_code == 401
    with TestClient(app) as customer:
        customer.cookies.set(COOKIE, 'x'*43)
        assert customer.get('/api/customer/reports').status_code == 401
        customer.cookies.clear()
        register(customer)
        with database() as db:
            row = db.scalar(select(CustomerSession))
            row.expires_at = time.time()-1
            db.commit()
        assert customer.get('/api/customer/reports').status_code == 401


@pytest.mark.parametrize('changes', [
    {'password': 'short'}, {'password': 'x'*129}, {'email': 'invalid'}, {'name': '   '}, {'account_id': 'injected'}])
def test_registration_validation(client, changes):
    with TestClient(app) as customer:
        response = customer.post('/api/customer/register', json={'name': 'New customer', 'email': 'new@example.com', 'password': PASSWORD, **changes})
        assert response.status_code in (400, 422)


def test_duplicate_registration_cannot_overwrite_password(client):
    with TestClient(app) as customer:
        assert register(customer).status_code == 201
        assert customer.post('/api/customer/register', json={'name': 'Impersonator', 'email': 'NEW@example.com', 'password': 'Another strong password.'}).status_code == 409
        with database() as db:
            row = db.scalar(select(CustomerAccount))
            assert row.name == 'New customer' and password_matches(PASSWORD, row.password_hash)


def test_login_and_registration_attempt_limits(client):
    with TestClient(app) as customer:
        for _ in range(8):
            assert customer.post('/api/customer/login', json={'email': 'absent@example.com', 'password': 'wrong'}).status_code == 401
        assert customer.post('/api/customer/login', json={'email': 'absent@example.com', 'password': 'wrong'}).status_code == 429
        for _ in range(5):
            assert customer.post('/api/customer/register', json={'name': 'N', 'email': 'new@example.com', 'password': 'short'}).status_code == 400
        assert register(customer).status_code == 429


def test_account_owns_new_reports_across_sessions_and_cannot_see_other_accounts(client, invitation):
    nonce = secrets.token_urlsafe(24)
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anonymous:
        register(alice, 'alice@example.com')
        register(bob, 'bob@example.com')
        first = create(alice, invitation, nonce).json()
        second = create(bob, invitation).json()
        assert first['account_owned'] is True
        assert alice.get('/api/customer/reports').json()[0]['access_token'] == first['access_token']
        assert len(alice.get('/api/customer/reports').json()) == 1
        projects = alice.get('/api/customer/projects').json()
        assert projects[0]['id'] == invitation['project_id']
        token = first['access_token']
        for outsider in (bob, anonymous):
            assert outsider.get(f'/api/public/submissions/{token}').status_code == 404
            assert outsider.put(f'/api/public/submissions/{token}', json={'text': 'Changed'}).status_code == 404
            assert outsider.delete(f'/api/public/submissions/{token}').status_code == 404
            assert outsider.post(f'/api/public/submissions/{token}/submit', json={}).status_code == 404
            assert create(outsider, invitation, nonce).status_code == 404
        alice.post('/api/customer/logout')
        assert alice.get(f'/api/public/submissions/{token}').status_code == 404
        alice.post('/api/customer/login', json={'email': 'alice@example.com', 'password': PASSWORD})
        assert alice.get(f'/api/public/submissions/{token}').status_code == 200
        assert alice.delete(f'/api/public/submissions/{token}').status_code == 200
        assert alice.get('/api/customer/reports').json() == []
        assert bob.get(f'/api/public/submissions/{second["access_token"]}').status_code == 200


def test_account_claim_requires_private_capability_and_cannot_take_another_account_report(client, invitation):
    guest = create(client, invitation).json()
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anonymous:
        register(alice, 'alice@example.com')
        register(bob, 'bob@example.com')
        assert anonymous.post('/api/customer/claims', json={'token': guest['access_token']}).status_code == 401
        assert alice.post('/api/customer/claims', json={'token': invitation['token']}).status_code == 404
        assert alice.post('/api/customer/claims', json={'token': guest['access_token']}).status_code == 200
        assert alice.post('/api/customer/claims', json={'token': guest['access_token']}).status_code == 200
        assert bob.post('/api/customer/claims', json={'token': guest['access_token']}).status_code == 404
        assert anonymous.get(f'/api/public/submissions/{guest["access_token"]}').status_code == 404
        assert len(alice.get('/api/customer/reports').json()) == 1
        assert bob.get('/api/customer/reports').json() == []


def test_project_invitation_connects_once_revocation_stops_new_reports_but_retains_owned_reports(client, invitation):
    with TestClient(app) as customer:
        register(customer)
        assert customer.get('/api/customer/projects').json() == []
        assert customer.post('/api/customer/projects', json={'token': 'x'*43}).status_code == 404
        for _ in range(2):
            assert customer.post('/api/customer/projects', json={'token': invitation['token']}).status_code == 200
        assert len(customer.get('/api/customer/projects').json()) == 1
        item = create(customer, invitation).json()
        client.delete(f'/api/projects/{invitation["project_id"]}/intake-link')
        assert customer.get('/api/customer/projects').json()[0]['closed'] is True
        assert customer.get('/api/customer/projects').json()[0]['intake_token'] is None
        assert create(customer, invitation).status_code == 404
        assert customer.get(f'/api/public/submissions/{item["access_token"]}').status_code == 200
        assert customer.delete(f'/api/public/submissions/{item["access_token"]}').status_code == 200


def test_owned_screenshot_requires_matching_customer_session(client, invitation):
    from io import BytesIO
    from PIL import Image
    with TestClient(app) as owner, TestClient(app) as outsider:
        register(owner)
        item = create(owner, invitation).json()
        token = item['access_token']
        raw = BytesIO()
        Image.new('RGB', (10, 10), 'white').save(raw, format='PNG')
        response = owner.post(f'/api/public/submissions/{token}/attachments?reviewed=true&filename=test.png',
                              content=raw.getvalue(), headers={'Content-Type': 'image/png'})
        image_id = response.json()['attachments'][0]['id']
        path = f'/api/public/submissions/{token}/attachments/{image_id}/content'
        assert owner.get(path).status_code == 200
        assert outsider.get(path).status_code == 404
        assert outsider.delete(f'/api/public/submissions/{token}/attachments/{image_id}').status_code == 404


def test_auth_origin_guard_and_secure_cookie(client):
    with TestClient(app, base_url='https://testserver') as customer:
        payload = {'name': 'New customer', 'email': 'new@example.com', 'password': PASSWORD}
        assert customer.post('/api/customer/register', json=payload, headers={'Origin': 'https://untrusted.example'}).status_code == 403
        response = customer.post('/api/customer/register', json=payload)
        assert response.status_code == 201 and 'secure' in response.headers['set-cookie'].lower()
