"""Reply image validation, atomic writes, private access, retries and deletion."""
import base64
from io import BytesIO
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from PIL import Image
from app.main import app
from app.models import MessageAttachment, ReportMessage, Feedback, Notification
from app.evidence import report_evidence
from app.reply_media import MAX_REPLY_BODY
from test_workflow import customer_report, database
from test_project_notifications import people
from test_evidence import image_bytes


def payload(content=None, **overrides):
    return {'filename':'screen.png', 'mime_type':'image/png', 'caption':'Look at the checkout button.', 'reviewed':True,
            'content_base64':base64.b64encode(content if content is not None else image_bytes(metadata=True)).decode(), **overrides}


def send(client, endpoint, attachments=None, **extra):
    return client.post(endpoint, json={'body':'The button still does not respond.', 'request_id':str(uuid4()),
        'attachments': [payload()] if attachments is None else attachments, **extra})


def content_path(endpoint, message):
    return f'{endpoint}/{message["id"]}/attachments/{message["attachments"][0]["id"]}/content'


def test_customer_screenshot_is_normalized_captioned_and_independent_of_evidence(client, customer_report):
    fid, token = customer_report['id'], customer_report['token']
    endpoint = f'/api/public/submissions/{token}/messages'
    before = client.get(f'/api/feedback/{fid}').json()
    with TestClient(app) as customer:
        result = send(customer, endpoint, [payload(filename='../private/screen.png')])
        assert result.status_code == 201
        message = result.json()[0]; image = message['attachments'][0]
        assert image['filename'] == 'screen.png' and image['caption'] == 'Look at the checkout button.'
        assert image['width'] == 160 and image['height'] == 100
        assert not {'storage_key','sha256','request_actor','request_fingerprint'} & image.keys()
        assert not {'request_id','request_actor','request_fingerprint'} & message.keys()
        response = customer.get(content_path(endpoint, message))
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert 'private-comment' not in Image.open(BytesIO(response.content)).info
    private = client.get(f'/api/feedback/{fid}/messages').json()[0]
    assert client.get(content_path(f'/api/feedback/{fid}/messages', private)).status_code == 200
    after = client.get(f'/api/feedback/{fid}').json()
    assert after['version'] == before['version'] and after['attachments'] == [] and after['report'] == before['report']
    with database() as db:
        assert not any(key.startswith('screenshot:') for key in report_evidence(db, db.get(Feedback,fid)))
    assert client.get('/api/health').json()['usage']['attempts'] == 0


@pytest.mark.parametrize('overrides,code', [({'reviewed':False},422),({'mime_type':'image/svg+xml'},422),
    ({'content_base64':'invalid base64!!!'},422),({'caption':'x'*501},422),
    ({'content_base64':base64.b64encode(b'not an image').decode()},415),
    ({'mime_type':'image/jpeg'},415)])
def test_bad_screenshots_leave_no_messages_or_files(client, draft, overrides, code):
    endpoint = f'/api/feedback/{draft["id"]}/messages'
    assert send(client, endpoint, [payload(**overrides)]).status_code == code
    assert client.get(endpoint).json() == []
    assert not app.state.storage.root.exists()


def test_jpeg_supported_and_pixel_byte_request_limits_enforced(client, draft):
    endpoint = f'/api/feedback/{draft["id"]}/messages'
    assert send(client, endpoint, [payload(image_bytes(kind='JPEG'), mime_type='image/jpeg', filename='screen.jpg')]).status_code == 201
    assert send(client, endpoint, [payload(image_bytes((2500,2000)))]).status_code == 413
    assert send(client, endpoint, [payload(b'a'*(2*1024*1024+1))]).status_code == 413
    assert send(client, endpoint, [payload()]*4).status_code == 422
    assert client.post(endpoint, content=b' '*(MAX_REPLY_BODY+1), headers={'Content-Type':'application/json'}).status_code == 413
    assert len(client.get(endpoint).json()) == 1


def test_private_note_images_remain_hidden_even_if_customer_knows_ids(client, customer_report):
    fid, token = customer_report['id'], customer_report['token']
    company = f'/api/feedback/{fid}/messages'; public = f'/api/public/submissions/{token}/messages'
    message = send(client, company, visibility='internal').json()[0]
    with TestClient(app) as customer:
        assert customer.get(public).json() == []
        assert customer.get(content_path(public, message)).status_code == 404
        assert customer.get(content_path(company, message)).status_code == 401
        assert send(customer, public, visibility='internal').status_code == 403
    assert client.get(content_path(company, message)).status_code == 200


def test_image_urls_enforce_account_project_and_report_scope(client, people):
    own, foreign = people['records']
    endpoint = f'/api/public/submissions/{own["token"]}/messages'
    first, other = people['customers']
    message = send(first, endpoint).json()[0]
    assert other.get(content_path(endpoint, message)).status_code == 404
    assert other.get(content_path(f'/api/public/submissions/{foreign["token"]}/messages', message)).status_code == 404
    company_path = content_path(f'/api/feedback/{own["id"]}/messages', message)
    assert people['employees'][1].get(company_path).status_code == 404
    assert people['employees'][0].get(company_path).status_code == 200
    assert client.get(content_path(f'/api/feedback/{foreign["id"]}/messages', message)).status_code == 404


def test_retry_creates_one_reply_image_and_one_set_of_notifications(client, customer_report):
    fid, token = customer_report['id'], customer_report['token']
    endpoint = f'/api/public/submissions/{token}/messages'; request_id = str(uuid4())
    with TestClient(app) as customer:
        for _ in range(2):
            response = send(customer, endpoint, request_id=request_id)
            assert response.status_code == 201 and len(response.json()) == 1
        assert send(customer, endpoint, request_id=request_id, body='A different message').status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReportMessage)) == 1
        assert db.scalar(select(func.count()).select_from(MessageAttachment)) == 1
        alerts = db.scalars(select(Notification).where(Notification.feedback_id==fid, Notification.kind=='customer_reply')).all()
        assert len({(row.scope,row.account_id) for row in alerts}) == len(alerts)
    assert len(list(app.state.storage.root.iterdir())) == 1


def test_failed_second_file_rolls_back_message_and_cleans_all_written_bytes(client, draft, monkeypatch):
    original = app.state.storage.put
    calls = 0
    def failing(key, content):
        nonlocal calls
        calls += 1
        original(key, content)
        if calls == 2:
            raise OSError('Simulated storage failure')
    monkeypatch.setattr(app.state.storage, 'put', failing)
    endpoint = f'/api/feedback/{draft["id"]}/messages'
    with pytest.raises(OSError):
        send(client, endpoint, [payload(),payload()])
    assert client.get(endpoint).json() == []
    assert list(app.state.storage.root.iterdir()) == []
    with database() as db:
        assert db.scalar(select(func.count()).select_from(MessageAttachment)) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_report_screenshot_cap_allows_text_and_idempotent_retries(client, draft, monkeypatch):
    import app.reply_media as media
    monkeypatch.setattr(media,'MAX_REPORT_IMAGES',1)
    endpoint = f'/api/feedback/{draft["id"]}/messages'; request_id = str(uuid4())
    assert send(client, endpoint, request_id=request_id).status_code == 201
    assert send(client, endpoint, request_id=request_id).status_code == 201
    assert send(client, endpoint).status_code == 409
    assert send(client, endpoint, []).status_code == 201
    assert len(client.get(endpoint).json()) == 2


def test_linked_reports_do_not_share_reply_images_and_deletion_removes_only_own_files(client, customer_report):
    fid, token = customer_report['id'], customer_report['token']
    other = client.post('/api/feedback', json={'project_id':customer_report['project'],'text':'Another linked report'}).json()
    assert client.post(f'/api/feedback/{other["id"]}/duplicates', json={'main_feedback_id':fid,'version':0}).status_code == 200
    public = f'/api/public/submissions/{token}/messages'
    with TestClient(app) as customer:
        message = send(customer, public).json()[0]
        image_path = content_path(public, message)
    assert client.post(f'/api/feedback/{fid}/duplicates/updates', json={'version':1,'request_id':str(uuid4()),'body':'A shared plain update'}).status_code == 200
    other_messages = client.get(f'/api/feedback/{other["id"]}/messages').json()
    assert len(other_messages)==1 and other_messages[0]['attachments']==[]
    own_other = send(client, f'/api/feedback/{other["id"]}/messages', visibility='internal').json()[-1]
    own_other_path = content_path(f'/api/feedback/{other["id"]}/messages', own_other)
    assert client.delete(f'/api/feedback/{fid}').status_code == 200
    assert client.get(image_path).status_code == 404
    assert client.get(own_other_path).status_code == 200
    with database() as db:
        assert db.scalar(select(func.count()).select_from(MessageAttachment)) == 1
    assert client.delete(f'/api/feedback/{other["id"]}').status_code == 200
    assert list(app.state.storage.root.iterdir()) == []
