"""Real image/SQLite checks; hosted responses below are explicit isolated test doubles."""
import asyncio
from io import BytesIO
import pytest
from PIL import Image, PngImagePlugin
from app.main import app
from app.config import settings
from app.schemas import BugReport, ImageAnalysis
from app.providers.base import Generation, VisionGeneration, ProviderError
from app.providers.gemini import validate_evidence


def image_bytes(size=(160,100), kind='PNG', metadata=False):
    output=BytesIO()
    image=Image.new('RGB',size,'white')
    if metadata:
        info=PngImagePlugin.PngInfo();info.add_text('private-comment','must disappear')
        image.save(output,format=kind,pnginfo=info)
    else:
        image.save(output,format=kind)
    return output.getvalue()

def upload(client,draft,content=None,kind='image/png',reviewed='true',name='screen.png'):
    return client.post(f'/api/feedback/{draft["id"]}/attachments?reviewed={reviewed}&filename={name}',content=content if content is not None else image_bytes(),headers={'Content-Type':kind})

class VisionDouble:
    def __init__(self,error=None):self.error=error
    async def analyze(self,content,mime_type):
        assert content and mime_type in ('image/png','image/jpeg')
        if self.error:raise self.error
        return VisionGeneration(ImageAnalysis(observations=[{'description':'A Pay now button is visible.','region':'center'}],limitations=['A still image cannot establish prior actions or button responsiveness.']),10,20)

def analyze(client,item,consent=True):
    return client.post(f'/api/feedback/{item["id"]}/attachments/{item["attachments"][0]["id"]}/analyze',json={'consent':consent})

def test_upload_metadata_preview_and_delete(client,draft):
    result=upload(client,draft,content=image_bytes(metadata=True),name='../private/screen.png')
    assert result.status_code==201
    item=result.json();image=item['attachments'][0]
    assert image['filename']=='screen.png' and image['width']==160 and image['reviewed_at']
    assert 'storage_key' not in image and image['analysis'] is None
    content_path=f'/api/feedback/{item["id"]}/attachments/{image["id"]}/content'
    response=client.get(content_path)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert 'private-comment' not in Image.open(BytesIO(response.content)).info
    assert len(list(app.state.storage.root.iterdir()))==1
    removed=client.delete(content_path.removesuffix('/content'))
    assert removed.status_code==200 and not removed.json()['attachments']
    assert client.get(content_path).status_code==404
    assert not list(app.state.storage.root.iterdir())
    assert removed.json()['version']>item['version']

@pytest.mark.parametrize('content,kind,status',[(b'not an image','image/png',415),(b'<svg/>','image/svg+xml',415),(image_bytes(),'image/jpeg',415),(b'', 'image/png',413),(b'a'*(2*1024*1024+1),'image/png',413)])
def test_bad_uploads_do_not_leave_files(client,draft,content,kind,status):
    assert upload(client,draft,content,kind).status_code==status
    assert not client.get(f'/api/feedback/{draft["id"]}').json()['attachments']
    assert not app.state.storage.root.exists()

def test_unreviewed_upload_blocked(client,draft):
    assert upload(client,draft,reviewed='false').status_code==400

def test_pixel_limit_before_decode(client,draft):
    assert upload(client,draft,image_bytes((2500,2000))).status_code==413

def test_jpeg_supported_and_mime_verified(client,draft):
    response=upload(client,draft,image_bytes(kind='JPEG'),kind='image/jpeg')
    assert response.status_code==201 and response.json()['attachments'][0]['mime_type']=='image/jpeg'

def test_attachment_cap_and_deletion_frees_slot(client,draft):
    for _ in range(3):assert upload(client,draft).status_code==201
    assert upload(client,draft).status_code==409
    item=client.get(f'/api/feedback/{draft["id"]}').json()
    client.delete(f'/api/feedback/{draft["id"]}/attachments/{item["attachments"][0]["id"]}')
    assert upload(client,draft).status_code==201

def test_ownership_path_checked(client,draft):
    item=upload(client,draft).json()
    other=client.post('/api/feedback',json={'project_id':draft['project_id'],'text':'Different feedback'}).json()
    assert client.get(f'/api/feedback/{other["id"]}/attachments/{item["attachments"][0]["id"]}/content').status_code==404

def test_vision_requires_consent_and_shared_cap(client,draft,monkeypatch):
    item=upload(client,draft).json()
    assert analyze(client,item,False).status_code==400
    app.state.image_analyzer=VisionDouble()
    assert analyze(client,item).status_code==200
    assert analyze(client,item).status_code==409
    usage=client.get('/api/health').json()['usage']
    assert usage['attempts']==1 and usage['vision_successful']==1 and usage['successful']==0
    assert usage['input_tokens']==10
    monkeypatch.setattr(settings,'ai_daily_limit',1)
    assert client.post(f'/api/feedback/{draft["id"]}/generate',json={'consent':True}).status_code==429

@pytest.mark.parametrize('code,status',[('quota',429),('timeout',504),('invalid_response',502)])
def test_vision_failure_preserves_image_and_report(client,draft,report_data,code,status):
    client.put(f'/api/feedback/{draft["id"]}/report',json={'version':draft['version'],'report':report_data})
    item=upload(client,draft).json()
    app.state.image_analyzer=VisionDouble(ProviderError(code,'External analysis unavailable',status))
    assert analyze(client,item).status_code==status
    saved=client.get(f'/api/feedback/{draft["id"]}').json()
    assert saved['report']['title']==report_data['title'] and saved['attachments'][0]['analysis'] is None
    assert saved['attachments'][0]['error'] and len(list(app.state.storage.root.iterdir()))==1
    if code=='quota':
        app.state.image_analyzer=VisionDouble()
        assert analyze(client,item).status_code==429
        assert client.get('/api/health').json()['usage']['attempts']==1

def test_missing_key_does_not_send_or_remove_image(client,draft,monkeypatch):
    item=upload(client,draft).json()
    monkeypatch.setattr(settings,'gemini_api_key','')
    assert analyze(client,item).status_code==503
    assert client.get('/api/health').json()['usage']['attempts']==0
    assert len(client.get(f'/api/feedback/{draft["id"]}').json()['attachments'])==1

def test_unanalyzed_images_block_report(client,draft):
    upload(client,draft)
    assert client.post(f'/api/feedback/{draft["id"]}/generate',json={'consent':True}).status_code==409

def test_clarification_history_survives_correction(client,draft):
    path=f'/api/feedback/{draft["id"]}/clarifications'
    first=client.post(path,json={'question':'Which browser?','answer':'Chrome'}).json()
    second=client.post(path,json={'question':'Which browser?','answer':'Correction: Safari'}).json()
    assert [a['answer'] for a in second['clarifications']]==['Chrome','Correction: Safari']
    assert second['version']>first['version'] and second['status']=='draft'
    assert client.post(path,json={'question':'Which browser?','answer':' '}).status_code==422

@pytest.mark.parametrize('answer',['Android Chrome','एंड्रॉयड पर क्रोम','Android pe Chrome use kiya'])
def test_answer_languages(client,draft,answer):
    result=client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'Which device and browser?','answer':answer})
    assert result.status_code==201 and result.json()['clarifications'][0]['answer']==answer

def test_clarification_cap(client,draft):
    for n in range(20):
        assert client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'More context?','answer':str(n)}).status_code==201
    assert client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'More context?','answer':'21'}).status_code==409

def test_revised_report_cites_answers_and_image_preserves_edits(client,draft,report_data):
    manual={**report_data,'title':'My manual title'}
    saved=client.put(f'/api/feedback/{draft["id"]}/report',json={'version':draft['version'],'report':manual}).json()
    item=upload(client,draft).json()
    app.state.image_analyzer=VisionDouble()
    analyze(client,item)
    answered=client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'Which browser?','answer':'Chrome on Android'}).json()
    answer_id=answered['clarifications'][0]['id'];image_id=item['attachments'][0]['id']
    class ReportDouble:
        async def generate(self,evidence):
            assert evidence[f'clarification:{answer_id}']=='Chrome on Android'
            assert evidence[f'screenshot:{image_id}:0']=='A Pay now button is visible.'
            revised={**report_data,'observations':[{'text':'Chrome on Android was supplied.','evidence_quote':'Chrome on Android','source':f'clarification:{answer_id}'},{'text':'The screenshot appears to show Pay now.','evidence_quote':'A Pay now button is visible.','source':f'screenshot:{image_id}:0'}]}
            report=BugReport.model_validate(revised);validate_evidence(report,evidence)
            return Generation(report)
    app.state.generator=ReportDouble()
    result=client.post(f'/api/feedback/{draft["id"]}/generate',json={'consent':True})
    assert result.status_code==200
    assert result.json()['report']['title']=='My manual title'
    assert result.json()['proposal']['observations'][0]['source']==f'clarification:{answer_id}'
    # New answers invalidate pending proposals, while saved manual edits survive.
    updated=client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'Additional context','answer':'Only on mobile'}).json()
    assert updated['proposal'] is None and updated['report']['title']=='My manual title'

@pytest.mark.parametrize('field',['expected_behaviour','reproduction_steps'])
def test_screenshot_cannot_prove_history_or_expectations(report_data,field):
    source='screenshot:11111111-1111-1111-1111-111111111111:0'
    claim={'text':'Clicked before the screenshot.','evidence_quote':'A button is visible.','source':source}
    report_data[field]=claim if field=='expected_behaviour' else [claim]
    evidence={'feedback':'I clicked Pay now. Nothing happened.',source:'A button is visible.'}
    with pytest.raises(ProviderError,match='cannot establish'):
        validate_evidence(BugReport.model_validate(report_data),evidence)

def test_fabricated_clarification_reference_rejected(report_data):
    report_data['actual_behaviour']['source']='clarification:11111111-1111-1111-1111-111111111111'
    with pytest.raises(ProviderError,match='unsupported'):
        validate_evidence(BugReport.model_validate(report_data),{'feedback':'I clicked Pay now. Nothing happened.'})

def test_blank_image_only_draft_and_generation_guard(client,draft):
    item=client.post('/api/feedback',json={'project_id':draft['project_id'],'text':''}).json()
    assert client.post(f'/api/feedback/{item["id"]}/generate',json={'consent':True}).status_code==400
    assert upload(client,item).status_code==201

def test_evidence_mutations_blocked_during_job(client,draft):
    item=upload(client,draft).json()
    async def lock():await app.state.job_lock.acquire()
    asyncio.run(lock())
    try:
        assert upload(client,draft).status_code==409
        assert client.delete(f'/api/feedback/{draft["id"]}/attachments/{item["attachments"][0]["id"]}').status_code==409
        assert client.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'Which browser?','answer':'Chrome'}).status_code==409
    finally:app.state.job_lock.release()

def test_manual_report_cannot_use_screenshot_as_reproduction_evidence(client,draft,report_data):
    report_data['reproduction_steps'][0]['source']='screenshot:11111111-1111-1111-1111-111111111111:0'
    response=client.put(f'/api/feedback/{draft["id"]}/report',json={'version':draft['version'],'report':report_data})
    assert response.status_code==422
    assert client.get(f'/api/feedback/{draft["id"]}').json()['report'] is None

def test_actual_concurrent_job_blocks_evidence_and_report_mutations(client,draft,report_data):
    import httpx
    async def scenario():
        entered=asyncio.Event();release=asyncio.Event()
        class BlockingGenerator:
            async def generate(self,evidence):
                entered.set()
                await release.wait()
                return Generation(BugReport.model_validate(report_data))
        app.state.generator=BlockingGenerator()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers={'X-Agency-Key':'test-agency-access-code'}) as remote:
            task=asyncio.create_task(remote.post(f'/api/feedback/{draft["id"]}/generate',json={'consent':True}))
            await asyncio.wait_for(entered.wait(),timeout=3)
            try:
                assert (await remote.post(f'/api/feedback/{draft["id"]}/generate',json={'consent':True})).status_code==409
                assert (await remote.post(f'/api/feedback/{draft["id"]}/clarifications',json={'question':'Which browser?','answer':'Chrome'})).status_code==409
                assert (await remote.put(f'/api/feedback/{draft["id"]}/report',json={'version':draft['version'],'report':report_data})).status_code==409
                assert (await remote.post(f'/api/feedback/{draft["id"]}/attachments?reviewed=true',content=image_bytes(),headers={'Content-Type':'image/png'})).status_code==409
            finally:
                release.set()
            assert (await task).status_code==200
            assert (await remote.get('/api/health')).json()['usage']['attempts']==1
    asyncio.run(scenario())

def test_transparent_hidden_pixels_are_flattened_to_white(client,draft):
    output=BytesIO()
    Image.new('RGBA',(20,20),(255,0,0,0)).save(output,format='PNG')
    item=upload(client,draft,output.getvalue()).json()
    response=client.get(f'/api/feedback/{draft["id"]}/attachments/{item["attachments"][0]["id"]}/content')
    assert Image.open(BytesIO(response.content)).getpixel((0,0))==(255,255,255)
