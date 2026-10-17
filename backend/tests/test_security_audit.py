"""Regression cases for issues reproduced during the workflow/security audit."""
import hashlib
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from sqlalchemy.exc import OperationalError
from app.main import app
from app.auth import COOKIE, _failures
from app.config import settings
from app.models import OwnerSession, EmployeeAccount, EmployeeSession, Feedback, MailMessage, NotificationPreference, now
from app.customer_auth import password_hash
from test_workflow import database, patch, customer_report, employee
from test_project_notifications import people

CODE = 'test-agency-access-code'


def test_owner_cookie_is_hashed_revocable_rotated_and_expires(client, monkeypatch):
    _failures.clear()
    with TestClient(app) as owner:
        assert owner.post('/api/auth/login', json={'code':CODE}).status_code == 200
        raw = owner.cookies.get(COOKIE)
        with database() as db:
            row = db.get(OwnerSession, hashlib.sha256(raw.encode()).hexdigest())
            assert row and row.token_hash != raw and row.expires_at > time.time()
        assert owner.get('/api/team').json()['can_manage'] is True
        assert owner.post('/api/auth/logout').status_code == 200
        owner.cookies.set(COOKIE,raw)
        assert owner.get('/api/projects').status_code == 401
        owner.cookies.clear()
        owner.post('/api/auth/login',json={'code':CODE})
        fresh = owner.cookies.get(COOKIE)
        assert fresh != raw
        with database() as db:
            db.get(OwnerSession,hashlib.sha256(fresh.encode()).hexdigest()).expires_at = time.time()-1
            db.commit()
        assert owner.get('/api/projects').status_code == 401
        owner.cookies.clear()
        owner.post('/api/auth/login',json={'code':CODE})
        monkeypatch.setattr(settings,'agency_access_code','rotated-private-owner-code')
        assert owner.get('/api/projects').status_code == 401


def test_role_switch_revokes_previous_owner_and_employee_credentials(client):
    _failures.clear()
    with TestClient(app) as person:
        assert person.post('/api/auth/employee/register',json={'name':'Named employee','email':'audit-employee@example.test','password':'My audit employee phrase!','workspace_code':CODE}).status_code == 201
        employee_cookie = person.cookies.get('bugbrief_employee')
        assert person.post('/api/auth/login',json={'code':CODE}).status_code == 200
        assert not person.cookies.get('bugbrief_employee')
        assert person.get('/api/auth/session').json() == {'authenticated':True}
        with TestClient(app) as copied:
            copied.cookies.set('bugbrief_employee',employee_cookie)
            assert copied.get('/api/projects').status_code == 401
        owner_cookie = person.cookies.get(COOKIE)
        assert person.post('/api/auth/employee/login',json={'email':'audit-employee@example.test','password':'My audit employee phrase!'}).status_code == 200
        assert not person.cookies.get(COOKIE)
        assert person.get('/api/auth/session').json()['employee']['name'] == 'Named employee'
        with TestClient(app) as copied:
            copied.cookies.set(COOKIE,owner_cookie)
            assert copied.get('/api/team/outbox').status_code == 401


def test_company_cannot_read_or_mutate_unsent_customer_evidence_even_with_known_ids(client):
    project=client.post('/api/projects',json={'name':'Private unsent draft'}).json()
    link=client.post(f'/api/projects/{project["id"]}/intake-link',json={}).json()['token']
    with TestClient(app) as customer:
        draft=customer.post(f'/api/public/intake/{link}/submissions',json={'client_nonce':'private-unsent-draft-nonce-12345','text':'Private before I send.'}).json()
        with database() as db:
            fid=db.scalar(select(Feedback.id))
        for suffix in ('','/workflow','/messages','/attachments/unknown/content'):
            assert client.get(f'/api/feedback/{fid}'+suffix).status_code == 404
        assert client.delete(f'/api/feedback/{fid}').status_code == 404
        assert client.put(f'/api/feedback/{fid}',json={'project_id':project['id'],'text':'Override customer draft.'}).status_code == 404
        assert client.post(f'/api/feedback/{fid}/generate',json={'consent':True}).status_code == 404
        assert customer.get(f'/api/public/submissions/{draft["access_token"]}').json()['text'] == 'Private before I send.'
        assert customer.post(f'/api/public/submissions/{draft["access_token"]}/submit',json={}).status_code == 200
        assert client.get(f'/api/feedback/{fid}').status_code == 200


def test_moving_report_releases_assignee_who_cannot_access_destination(client, draft, employee):
    state=patch(client,draft['id'],status='in_progress',employee=employee).json()
    destination=client.post('/api/projects',json={'name':'Different destination'}).json()
    result=client.put(f'/api/feedback/{draft["id"]}',json={'project_id':destination['id'],'text':draft['text']})
    assert result.status_code == 200
    progress=result.json()['workflow']
    assert progress['assigned_employee_id'] is None and progress['version'] == state['version']+1
    assert progress['events'][-1]['label'] == 'Assignment removed'


def test_restored_customer_uses_current_link_instead_of_revoked_membership_link(client, people):
    project=people['projects'][0]['id']
    record=people['records'][0]
    customer=people['customers'][0]
    client.delete(f'/api/projects/{project}/members/customer/{record["customer_id"]}')
    client.delete(f'/api/projects/{project}/intake-link')
    fresh=client.post(f'/api/projects/{project}/intake-link',json={}).json()['token']
    assert fresh != record['link']
    assert client.post(f'/api/projects/{project}/members/customer',json={'email':'customer0@project.test'}).status_code == 200
    card=next(row for row in customer.get('/api/customer/projects').json() if row['id']==project)
    assert card['intake_token'] == fresh and card['closed'] is False


def test_delivery_rechecks_preferences_and_skips_deleted_queued_mail_between_sends(client, people, monkeypatch):
    from app import notifications
    from app.models import CustomerAccount
    record=people['records'][0]
    customer=people['customers'][0]
    customer.patch('/api/auth/notifications/customer/preferences',json={'email_enabled':True})
    with database() as db:
        db.get(CustomerAccount,record['customer_id']).email_verified_at=now()
        db.commit()
    for i in range(3):
        client.post(f'/api/feedback/{record["id"]}/messages',json={'body':f'Reply {i}'})
    with database() as db:
        mails=db.scalars(select(MailMessage).where(MailMessage.notification_id.is_not(None)).order_by(MailMessage.created_at)).all()
        ids=[m.id for m in mails]
        for mail in mails: mail.delivery='pending'
        db.commit()
    monkeypatch.setattr(settings,'mail_mode','smtp')
    sent=[]
    def simulated_send(mail):
        sent.append(mail.id)
        with database() as other:
            other.get(NotificationPreference,('customer',record['customer_id'])).email_enabled=0
            other.execute(delete(MailMessage).where(MailMessage.id==ids[1]))
            other.commit()
        mail.delivery,mail.body='sent',''
    monkeypatch.setattr(notifications,'deliver_mail',simulated_send)
    notifications.deliver_pending(app.state.session_factory)
    assert sent == [ids[0]]
    with database() as db:
        assert db.get(MailMessage,ids[1]) is None
        assert db.get(MailMessage,ids[2]).delivery == 'cancelled'


def test_temporary_database_error_does_not_kill_mail_worker_or_hold_lock(client):
    from app.notifications import deliver_pending
    def unavailable():
        raise OperationalError('SELECT',{},Exception('temporary database lock'))
    deliver_pending(unavailable)
    deliver_pending(app.state.session_factory)
