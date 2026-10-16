import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import Base, get_db, make_engine
from app.main import app
from app.config import settings
from app.providers.gemini import GeminiGenerator, GeminiImageAnalyzer
from app.storage import LocalStorage

@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.customer_auth import _attempts
    _attempts.clear()
    engine = make_engine(f'sqlite:///{tmp_path / "test.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def db_override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(settings, 'agency_access_code', 'test-agency-access-code')
    monkeypatch.setattr(settings, 'agency_code_path', tmp_path / 'owner-code.txt')
    monkeypatch.setattr(settings, 'gemini_api_key', 'test-key-never-sent')
    monkeypatch.setattr(settings, 'free_tier_confirmed', True)
    monkeypatch.setattr(settings, 'ai_daily_limit', 20)
    app.state.generator = GeminiGenerator(settings)
    app.state.image_analyzer = GeminiImageAnalyzer(settings)
    app.state.storage = LocalStorage(tmp_path / 'attachments')
    with TestClient(app) as c:
        c.headers['X-Agency-Key'] = 'test-agency-access-code'
        yield c
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def draft(client):
    p = client.post('/api/projects', json={'name':'Test storefront','url':'https://example.com'}).json()
    return client.post('/api/feedback', json={'project_id':p['id'],'text':'I clicked Pay now. Nothing happened.'}).json()

@pytest.fixture
def report_data():
    return {'title':'Pay now button does not respond','description':'The user reports that Pay now does not respond.',
        'expected_behaviour':None,'actual_behaviour':{'text':'No response after clicking.','evidence_quote':'Nothing happened.','source':'feedback'},
        'reproduction_steps':[{'text':'Click Pay now.','evidence_quote':'I clicked Pay now.','source':'feedback'}],
        'observations':[], 'hypotheses':[], 'unknowns':['Browser and device are not supplied.'],
        'questions':['Which browser and device were you using?'],'category':'Functionality','priority':'Medium'}
