"""Authorization, content erasure and quota-preservation checks for report deletion."""
from contextlib import contextmanager
from io import BytesIO
import secrets
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, func
from app.main import app
from app.db import get_db
from app.models import Feedback, CustomerSubmission, Attachment, Clarification, AIJob
from app.jobs import day


def database():
    return contextmanager(app.dependency_overrides[get_db])()


def customer_record(client, text='The checkout button does nothing.'):
    project = client.post('/api/projects', json={'name': 'Deletion project'}).json()
    link = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()
    payload = {'client_nonce': secrets.token_urlsafe(24), 'text': text,
               'reporter_name': 'Private name', 'context': {'user_agent': 'Private browser'}}
    item = client.post(f'/api/public/intake/{link["token"]}/submissions', json=payload).json()
    return project, link, payload, item


@pytest.mark.parametrize('actor', ['customer', 'company'])
def test_delete_erases_content_files_and_private_access_but_keeps_quota(client, actor, report_data):
    _, link, payload, item = customer_record(client)
    token = item['access_token']
    with TestClient(app) as customer:
        raw = BytesIO()
        Image.new('RGB', (10, 10), 'red').save(raw, format='PNG')
        image = customer.post(f'/api/public/submissions/{token}/attachments?reviewed=true&filename=private.png',
                              content=raw.getvalue(), headers={'Content-Type': 'image/png'}).json()['attachments'][0]
        assert customer.post(f'/api/public/submissions/{token}/answers', json={'answers': [
            {'question': 'Additional context', 'answer': 'Private answer'}]}).status_code == 200
        customer.post(f'/api/public/submissions/{token}/submit', json={})
        feedback = client.get('/api/feedback').json()[0]
        with database() as db:
            stored = db.get(Feedback, feedback['id'])
            stored.report = report_data
            stored.proposal = report_data
            db.add(AIJob(feedback_id=stored.id, day=day(), model='test', outcome='quota'))
            db.commit()
            key = db.get(Attachment, image['id']).storage_key
        assert app.state.storage.path(key).exists()
        response = (customer.delete(f'/api/public/submissions/{token}') if actor == 'customer'
                    else client.delete(f'/api/feedback/{feedback["id"]}'))
        assert response.status_code == 200 and response.json() == {'deleted': True}
        assert not app.state.storage.path(key).exists()
        assert client.get('/api/feedback').json() == []
        assert client.get(f'/api/feedback/{feedback["id"]}').status_code == 404
        assert customer.get(f'/api/public/submissions/{token}').status_code == 404
        assert customer.get(f'/api/public/submissions/{token}/attachments/{image["id"]}/content').status_code == 404
        assert customer.post(f'/api/public/submissions/{token}/submit', json={}).status_code == 404
        assert customer.put(f'/api/public/submissions/{token}', json={'text': 'Revive'}).status_code == 404
        assert customer.post(f'/api/public/intake/{link["token"]}/submissions', json=payload).status_code == 410
        assert client.delete(f'/api/feedback/{feedback["id"]}').status_code == 404
        usage = client.get('/api/health').json()['usage']
        assert usage['attempts'] == 1 and usage['paused'] is True
        with database() as db:
            erased = db.get(Feedback, feedback['id'])
            assert erased.deleted_at and erased.text == '' and erased.page_url == ''
            assert erased.report is None and erased.proposal is None and erased.error is None
            customer_row = db.scalar(select(CustomerSubmission))
            assert customer_row.context == {} and customer_row.reporter_name == '' and customer_row.stage == 'deleted'
            assert db.scalar(select(func.count()).select_from(Attachment)) == 0
            assert db.scalar(select(func.count()).select_from(Clarification)) == 0


def test_anonymous_cannot_delete_company_or_other_customer_reports(client):
    _, link, _, first = customer_record(client, 'First customer feedback')
    second = client.post(f'/api/public/intake/{link["token"]}/submissions', json={
        'text': 'Second customer feedback', 'client_nonce': secrets.token_urlsafe(24)}).json()
    for item in (first, second):
        client.post(f'/api/public/submissions/{item["access_token"]}/submit', json={})
    rows = client.get('/api/feedback').json()
    with TestClient(app) as customer:
        assert customer.delete(f'/api/feedback/{rows[0]["id"]}').status_code == 401
        assert customer.delete(f'/api/public/submissions/{link["token"]}').status_code == 404
        assert customer.delete(f'/api/public/submissions/{rows[0]["id"]}').status_code == 404
        assert customer.delete(f'/api/public/submissions/{first["access_token"]}').status_code == 200
        assert customer.get(f'/api/public/submissions/{second["access_token"]}').status_code == 200
    assert len(client.get('/api/feedback').json()) == 1


@pytest.mark.parametrize('actor', ['customer', 'company'])
def test_deletion_rejected_while_own_report_is_processing(client, actor, monkeypatch):
    _, _, _, item = customer_record(client)
    with database() as db:
        feedback_id = db.scalar(select(CustomerSubmission.feedback_id))
    class Locked:
        def locked(self): return True
    monkeypatch.setattr(app.state, 'job_lock', Locked())
    monkeypatch.setattr(app.state, 'active_feedback_id', feedback_id)
    path = f'/api/public/submissions/{item["access_token"]}' if actor == 'customer' else f'/api/feedback/{feedback_id}'
    assert client.delete(path).status_code == 409
    assert client.get(f'/api/public/submissions/{item["access_token"]}').status_code == 200


def test_company_can_delete_manual_draft_without_affecting_other_records(client, draft):
    other = client.post('/api/feedback', json={'project_id': draft['project_id'], 'text': 'Keep this draft.'}).json()
    assert client.delete(f'/api/feedback/{draft["id"]}').status_code == 200
    assert client.get(f'/api/feedback/{other["id"]}').status_code == 200
    assert len(client.get('/api/feedback').json()) == 1


def test_revoked_link_still_allows_private_holder_to_delete(client):
    project, _, _, item = customer_record(client)
    client.delete(f'/api/projects/{project["id"]}/intake-link')
    with TestClient(app) as customer:
        assert customer.delete(f'/api/public/submissions/{item["access_token"]}').status_code == 200


def test_deleted_draft_does_not_reset_project_submission_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'public_submissions_daily_limit', 1)
    _, link, _, item = customer_record(client)
    client.delete(f'/api/public/submissions/{item["access_token"]}')
    response = client.post(f'/api/public/intake/{link["token"]}/submissions', json={
        'client_nonce': secrets.token_urlsafe(24), 'text': 'Another report'})
    assert response.status_code == 429
