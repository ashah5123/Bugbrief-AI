"""Mocked HTTP transport contract tests. These do not verify live model accuracy."""
import asyncio
import json
import httpx
import pytest
from app.config import Settings
from app.providers.gemini import GeminiGenerator, validate_evidence
from app.providers.base import ProviderError
from app.schemas import BugReport

@pytest.mark.parametrize('field', ['actual_behaviour','reproduction_steps'])
def test_fabricated_evidence_rejected(report_data,field):
    if field == 'actual_behaviour':
        report_data[field]['evidence_quote'] = 'An invented network error'
    else:
        report_data[field][0]['evidence_quote'] = 'I opened the browser developer console'
    with pytest.raises(ProviderError,match='unsupported'):
        validate_evidence(BugReport.model_validate(report_data),{'feedback':'I clicked Pay now. Nothing happened.'})

@pytest.mark.parametrize('status,code', [(429,'quota'),(401,'credentials'),(403,'credentials'),(500,'provider_failure')])
def test_http_failures(monkeypatch,status,code):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(status)),**kwargs))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(GeminiGenerator(Settings(gemini_api_key='test',free_tier_confirmed=True)).generate({'feedback':'Test'}))
    assert exc.value.code == code

@pytest.mark.parametrize('raw', ['not json', '{}', '{"title":"Unsupported"}'])
def test_invalid_ai_response(monkeypatch,raw):
    original = httpx.AsyncClient
    payload = {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':raw}]}}]}
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload)),**kwargs))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(GeminiGenerator(Settings(gemini_api_key='test',free_tier_confirmed=True)).generate({'feedback':'Test'}))
    assert exc.value.code == 'invalid_response'

def test_valid_provider_contract(monkeypatch,report_data):
    original = httpx.AsyncClient
    def respond(request):
        assert request.headers['x-goog-api-key'] == 'test'
        body = json.loads(request.content)
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert 'UNTRUSTED' in body['systemInstruction']['parts'][0]['text']
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(report_data)}]}}], 'usageMetadata':{'promptTokenCount':12,'candidatesTokenCount':22}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    result = asyncio.run(GeminiGenerator(Settings(gemini_api_key='test',free_tier_confirmed=True)).generate({'feedback':'I clicked Pay now. Nothing happened.'}))
    assert result.report.title == report_data['title'] and result.input_tokens == 12

def test_timeout(monkeypatch):
    original = httpx.AsyncClient
    def respond(request):
        raise httpx.ReadTimeout('test timeout')
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(GeminiGenerator(Settings(gemini_api_key='test',free_tier_confirmed=True)).generate({'feedback':'Test'}))
    assert exc.value.code == 'timeout'

def test_vision_http_contract(monkeypatch):
    import base64
    from app.providers.gemini import GeminiImageAnalyzer
    original=httpx.AsyncClient
    def respond(request):
        body=json.loads(request.content)
        parts=body['contents'][0]['parts']
        assert parts[0]['inlineData']['mimeType']=='image/png'
        assert base64.b64decode(parts[0]['inlineData']['data'])==b'reviewed-pixels'
        assert 'UNTRUSTED DATA' in body['systemInstruction']['parts'][0]['text']
        result={'observations':[{'description':'An error banner is visible.','region':'top'}],'limitations':['A screenshot cannot prove preceding user actions.']}
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result)}]}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    result=asyncio.run(GeminiImageAnalyzer(Settings(gemini_api_key='test',free_tier_confirmed=True)).analyze(b'reviewed-pixels','image/png'))
    assert result.analysis.observations[0].region=='top'

def test_vision_invalid_output_rejected(monkeypatch):
    from app.providers.gemini import GeminiImageAnalyzer
    original=httpx.AsyncClient
    # Invented interaction fields are outside the allowed observation schema.
    invalid={'observations':[],'limitations':[],'reproduction_steps':['Click checkout']}
    payload={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(invalid)}]}}]}
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload)),**kwargs))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(GeminiImageAnalyzer(Settings(gemini_api_key='test',free_tier_confirmed=True)).analyze(b'image','image/png'))
    assert exc.value.code=='invalid_response'
