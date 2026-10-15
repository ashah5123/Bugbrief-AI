"""Isolated tests only: no API calls. The injected generator is explicitly a test double."""
import asyncio
import pytest
from app.main import app
from app.schemas import BugReport
from app.config import settings
from app.providers.base import Generation, ProviderError

class FakeGenerator:
    def __init__(self, report=None, error=None):
        self.report, self.error = report, error
    async def generate(self, evidence):
        if self.error:
            raise self.error
        return Generation(BugReport.model_validate(self.report), 42, 80)

def generate(client, draft):
    return client.post(f'/api/feedback/{draft["id"]}/generate', json={'consent':True})

@pytest.mark.parametrize('text', ['Checkout button does nothing.', 'भुगतान बटन काम नहीं कर रहा है।', 'Checkout pe click kiya but kuch nahi hua.'])
def test_languages_persist_exactly(client, text):
    p = client.post('/api/projects', json={'name':'Demo'}).json()
    response = client.post('/api/feedback', json={'project_id':p['id'],'text':text})
    assert response.status_code == 201
    assert client.get('/api/feedback').json()[0]['text'] == text

@pytest.mark.parametrize('payload', [{'name':' '},{'name':'Demo','url':'javascript:alert(1)'},{'name':'a'*101}])
def test_invalid_project(client,payload):
    assert client.post('/api/projects',json=payload).status_code == 422

def test_missing_project_and_oversized_feedback(client):
    assert client.post('/api/feedback',json={'project_id':'missing','text':'Some bug'}).status_code == 404
    assert client.post('/api/feedback',json={'project_id':'missing','text':'a'*8001}).status_code == 422

def test_missing_key_preserves_feedback(client,draft,monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','')
    assert generate(client,draft).status_code == 503
    assert client.get('/api/feedback').json()[0]['text'] == draft['text']
    assert client.get('/api/health').json()['usage']['attempts'] == 0

def test_billing_confirmation_required(client,draft,monkeypatch):
    monkeypatch.setattr(settings,'free_tier_confirmed',False)
    assert generate(client,draft).status_code == 503

def test_consent_required(client,draft):
    assert client.post(f'/api/feedback/{draft["id"]}/generate',json={}).status_code == 400

def test_generate_edit_regenerate_preserves_manual_work(client,draft,report_data):
    app.state.generator = FakeGenerator(report_data)
    first = generate(client,draft).json()
    assert first['report']['title'] == report_data['title']
    edited = {**report_data,'title':'My carefully edited title'}
    saved = client.put(f'/api/feedback/{draft["id"]}/report',json={'version':first['version'],'report':edited}).json()
    regenerated = generate(client,draft).json()
    assert regenerated['report']['title'] == edited['title']
    assert regenerated['proposal']['title'] == report_data['title']
    applied = client.post(f'/api/feedback/{draft["id"]}/apply-proposal',json={'version':regenerated['version']}).json()
    assert applied['report']['title'] == report_data['title']
    assert applied['proposal'] is None
    usage = client.get('/api/health').json()['usage']
    assert usage['successful'] == 2 and usage['input_tokens'] == 84
    assert saved['version'] > first['version']

def test_stale_save_rejected(client,draft,report_data):
    path = f'/api/feedback/{draft["id"]}/report'
    assert client.put(path,json={'version':draft['version'],'report':report_data}).status_code == 200
    assert client.put(path,json={'version':draft['version'],'report':report_data}).status_code == 409

def test_invalid_report_never_saved(client,draft):
    assert client.put(f'/api/feedback/{draft["id"]}/report',json={'version':1,'report':{'title':'Invalid'}}).status_code == 422
    assert client.get('/api/feedback').json()[0]['report'] is None

@pytest.mark.parametrize('code,status', [('timeout',504),('invalid_response',502),('network',503),('provider_failure',502)])
def test_provider_failures_preserve_work(client,draft,code,status):
    app.state.generator = FakeGenerator(error=ProviderError(code,'Provider unavailable',status))
    assert generate(client,draft).status_code == status
    item = client.get('/api/feedback').json()[0]
    assert item['text'] == draft['text'] and item['report'] is None
    assert client.get('/api/health').json()['usage']['attempts'] == 1

def test_quota_pauses_further_processing(client,draft,report_data):
    app.state.generator = FakeGenerator(error=ProviderError('quota','Quota exhausted',429))
    assert generate(client,draft).status_code == 429
    app.state.generator = FakeGenerator(report_data)
    assert generate(client,draft).status_code == 429
    assert client.get('/api/health').json()['usage']['attempts'] == 1

def test_daily_cap(client,draft,report_data,monkeypatch):
    monkeypatch.setattr(settings,'ai_daily_limit',1)
    app.state.generator = FakeGenerator(report_data)
    assert generate(client,draft).status_code == 200
    assert generate(client,draft).status_code == 429

def test_single_job_lock(client,draft):
    async def lock():
        await app.state.job_lock.acquire()
    asyncio.run(lock())
    try:
        assert generate(client,draft).status_code == 409
    finally:
        app.state.job_lock.release()

def test_cross_origin_write_rejected(client):
    assert client.post('/api/projects',json={'name':'X'},headers={'Origin':'https://untrusted.example'}).status_code == 403

def test_request_body_size_limit(client):
    assert client.post('/api/projects',content='a'*32769,headers={'Content-Type':'application/json'}).status_code == 413

def test_report_save_blocked_while_ai_running(client,draft,report_data):
    async def lock():
        await app.state.job_lock.acquire()
    asyncio.run(lock())
    try:
        assert client.put(f'/api/feedback/{draft["id"]}/report',json={'version':draft['version'],'report':report_data}).status_code == 409
    finally:
        app.state.job_lock.release()
