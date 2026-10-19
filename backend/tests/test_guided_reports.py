"""Structured customer answers remain original, scoped evidence."""
import secrets
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import CustomerSubmission
from app.providers.base import Generation
from app.schemas import BugReport
from test_intake import anonymous, link, create

DETAILS = {'goal': 'Complete my order', 'expected': 'Payment form opens.',
           'steps': '1. Open cart\n2. Click Pay now', 'frequency': 'every_time'}


def test_guided_answers_roundtrip_edit_clear_and_old_client_preservation(client, anonymous, link):
    item = create(anonymous, link, guided_details={**DETAILS, 'goal': '  Complete my order  '}).json()
    base = f'/api/public/submissions/{item["access_token"]}'
    assert item['guided_details'] == DETAILS
    assert anonymous.get(base).json()['guided_details'] == DETAILS
    # An older client editing its description must not silently erase structured answers.
    assert anonymous.put(base, json={'text': 'Original updated symptom', 'draft_version': anonymous.get(base).json()['draft_version']}).json()['guided_details'] == DETAILS
    assert anonymous.put(base, json={'text': 'Original updated symptom', 'draft_version': anonymous.get(base).json()['draft_version'], 'guided_details': {'frequency': 'not_sure'}}).json()['guided_details'] == {
        'goal': '', 'expected': '', 'steps': '', 'frequency': 'not_sure'}
    assert anonymous.put(base, json={'text': 'Original updated symptom', 'draft_version': anonymous.get(base).json()['draft_version'], 'guided_details': None}).json()['guided_details'] is None


@pytest.mark.parametrize('details', [
    {'frequency': 'always'}, {'goal': 'x' * 1001}, {'expected': 'x' * 2001},
    {'steps': 'x' * 2001}, {'unknown': 'secret'}, {'goal': {'text': 'bad'}},
])
def test_guided_validation(anonymous, link, details):
    assert create(anonymous, link, guided_details=details).status_code == 422


def test_guided_answers_submit_once_and_stay_read_only(client, anonymous, link):
    nonce = secrets.token_urlsafe(24)
    first = create(anonymous, link, client_nonce=nonce, guided_details=DETAILS).json()
    retried = create(anonymous, link, client_nonce=nonce, guided_details={'goal': 'Different retry'}).json()
    assert retried['guided_details'] == DETAILS
    assert retried['access_token'] == first['access_token']
    assert client.get('/api/feedback').json() == []
    base = f'/api/public/submissions/{first["access_token"]}'
    for _ in range(2):
        assert anonymous.post(base + '/submit', json={'draft_version': anonymous.get((base + '/submit').removesuffix('/submit')).json().get('draft_version', 1)}).json()['guided_details'] == DETAILS
    report = client.get('/api/feedback').json()[0]
    assert report['text'] == first['text']
    assert report['customer']['guided_details'] == DETAILS
    assert anonymous.put(base, json={'text': 'Changed', 'guided_details': None}).status_code == 409
    assert anonymous.get(base).json()['guided_details'] == DETAILS


def test_guided_evidence_quotes_are_available_without_sharing_name(client, anonymous, link, report_data):
    class Generator:
        async def generate(self, evidence):
            assert evidence['feedback'] == 'I clicked Pay now. Nothing happened.'
            assert evidence['guided:goal'] == DETAILS['goal']
            assert evidence['guided:expected'] == DETAILS['expected']
            assert evidence['guided:steps'] == DETAILS['steps']
            assert evidence['guided:frequency'] == 'Every time'
            assert 'captured_context' not in evidence
            assert all('Private reporter' not in value for value in evidence.values())
            from app.providers.gemini import validate_evidence
            report = BugReport.model_validate({**report_data, 'expected_behaviour': {
                'text': 'The customer expected the payment form.',
                'evidence_quote': DETAILS['expected'], 'source': 'guided:expected'},
                'reproduction_steps': [{'text': 'Open the cart.', 'evidence_quote': 'Open cart', 'source': 'guided:steps'}]})
            validate_evidence(report, evidence)
            return Generation(report)
    app.state.generator = Generator()
    item = create(anonymous, link, reporter_name='Private reporter', guided_details=DETAILS).json()
    checked = anonymous.post(f'/api/public/submissions/{item["access_token"]}/process', json={'consent': True})
    assert checked.status_code == 200 and checked.json()['has_report']
    assert checked.json()['guided_details'] == DETAILS
    assert anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit', json={'draft_version': anonymous.get((f"/api/public/submissions/{item['access_token']}/submit").removesuffix('/submit')).json().get('draft_version', 1)}).status_code == 200
    saved = client.get('/api/feedback').json()[0]
    assert saved['report']['expected_behaviour']['source'] == 'guided:expected'


def test_optional_answers_stay_unknown_and_do_not_replace_a_symptom(client, anonymous, link):
    item = create(anonymous, link, text='', guided_details={'goal': 'Buy something', 'frequency': 'not_sure'}).json()
    assert anonymous.post(f'/api/public/submissions/{item["access_token"]}/submit', json={'draft_version': anonymous.get((f"/api/public/submissions/{item['access_token']}/submit").removesuffix('/submit')).json().get('draft_version', 1)}).status_code == 400
    from app.evidence import report_evidence
    from app.models import Feedback
    with app.state.session_factory() as db:
        feedback = db.scalar(select(Feedback))
        feedback.text = 'The page froze.'
        db.commit()
        evidence = report_evidence(db, feedback)
        assert evidence['guided:frequency'] == 'Not sure'
        assert 'guided:expected' not in evidence and 'guided:steps' not in evidence


def test_guided_answers_delete_with_report(client, anonymous, link):
    item = create(anonymous, link, guided_details=DETAILS).json()
    base = f'/api/public/submissions/{item["access_token"]}'
    assert anonymous.delete(base).status_code == 200
    assert anonymous.get(base).status_code == 404
    with app.state.session_factory() as db:
        tombstone = db.scalar(select(CustomerSubmission))
        assert tombstone.guided_details is None and tombstone.stage == 'deleted'


def test_guided_answers_do_not_leak_between_customer_accounts(client, link):
    with TestClient(app) as first, TestClient(app) as second:
        for browser, email in [(first, 'first@example.test'), (second, 'second@example.test')]:
            assert browser.post('/api/customer/register', json={
                'name': 'Customer', 'email': email, 'password': 'Guided secure phrase 42!'}).status_code == 201
        item = create(first, link, guided_details=DETAILS).json()
        base = f'/api/public/submissions/{item["access_token"]}'
        assert second.get(base).status_code == 404
        assert second.put(base, json={'text': 'Overwrite', 'guided_details': None}).status_code == 404
        assert first.get(base).json()['guided_details'] == DETAILS


def test_multilingual_drafts_have_a_bounded_larger_json_budget(anonymous, link):
    details = {'goal': 'क' * 1000, 'expected': 'क' * 2000, 'steps': 'क' * 2000, 'frequency': 'sometimes'}
    item = create(anonymous, link, text='क' * 8000, guided_details=details)
    assert item.status_code == 201
    token = item.json()['access_token']
    base = f'/api/public/submissions/{token}'
    assert anonymous.put(base, json={'text': 'क' * 8000, 'guided_details': details, 'draft_version': item.json()['draft_version']}).status_code == 200
    for method, path in [('POST', f'/api/public/intake/{link["token"]}/submissions'), ('PUT', base)]:
        assert anonymous.request(method, path, content=b' ' * (65536 + 1), headers={'Content-Type': 'application/json'}).status_code == 413
    # Other JSON endpoints retain the original budget.
    assert anonymous.post(base + '/answers', content=b' ' * 32769, headers={'Content-Type': 'application/json'}).status_code == 413
    assert anonymous.get(base).json()['guided_details'] == details
