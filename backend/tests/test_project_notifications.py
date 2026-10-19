"""Exercise isolation and notification delivery with real role sessions and membership changes."""
from contextlib import ExitStack
from io import BytesIO
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.models import (EmployeeAccount, EmployeeProject, CustomerSubmission, Notification,
                        MailMessage, CustomerAccount, NotificationPreference, now)
from app.customer_auth import password_hash
from test_workflow import database, patch

PASSWORD = 'Project notification test phrase!'


@pytest.fixture
def people(client):
    projects = [client.post('/api/projects', json={'name': name}).json() for name in ('Project Alpha', 'Project Beta')]
    with database() as db:
        hashed = password_hash(PASSWORD)
        employees = [EmployeeAccount(name=name, email=email, password_hash=hashed, email_verified_at=now())
                     for name, email in [('Alex', 'alex@project.test'), ('Blair', 'blair@project.test')]]
        db.add_all(employees); db.flush()
        for employee, project in zip(employees, projects):
            db.add(EmployeeProject(employee_id=employee.id, project_id=project['id']))
        db.commit()
        ids = [employee.id for employee in employees]
    with ExitStack() as stack:
        employees = [stack.enter_context(TestClient(app)) for _ in range(2)]
        customers = [stack.enter_context(TestClient(app)) for _ in range(2)]
        records = []
        for index in range(2):
            email = ('alex@project.test', 'blair@project.test')[index]
            assert employees[index].post('/api/auth/employee/login', json={'email': email, 'password': PASSWORD}).status_code == 200
            result = customers[index].post('/api/customer/register', json={
                'name': 'Customer ' + str(index), 'email': f'customer{index}@project.test', 'password': PASSWORD})
            assert result.status_code == 201
            project = projects[index]
            link = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()['token']
            record = customers[index].post(f'/api/public/intake/{link}/submissions', json={
                'client_nonce': 'project-notification-nonce-123456789', 'text': 'Checkout is not responding.'}).json()
            token = record['access_token']
            assert customers[index].post(f'/api/public/submissions/{token}/submit', json={'draft_version': customers[index].get((f'/api/public/submissions/{token}/submit').removesuffix('/submit')).json().get('draft_version', 1)}).status_code == 200
            with database() as db:
                feedback_id = db.scalar(select(CustomerSubmission.feedback_id).where(CustomerSubmission.access_token == token))
            records.append({'id': feedback_id, 'token': token, 'link': link, 'customer_id': result.json()['customer']['id']})
        yield {'projects': projects, 'employees': employees, 'employee_ids': ids, 'customers': customers, 'records': records}


def test_employee_access_filters_lists_and_guards_every_report_route(client, people):
    employee = people['employees'][0]
    first, other = people['records']
    alpha, beta = people['projects']
    assert [p['id'] for p in employee.get('/api/projects').json()] == [alpha['id']]
    assert [f['id'] for f in employee.get('/api/feedback').json()] == [first['id']]
    assert employee.get(f'/api/feedback/{first["id"]}').status_code == 200
    for suffix in ('', '/workflow', '/messages', '/attachments/unknown/content'):
        assert employee.get(f'/api/feedback/{other["id"]}' + suffix).status_code == 404
    assert employee.delete(f'/api/feedback/{other["id"]}').status_code == 404
    assert employee.post(f'/api/feedback/{other["id"]}/messages', json={'body': 'Not allowed'}).status_code == 404
    assert employee.post(f'/api/feedback/{other["id"]}/generate', json={'consent': True}).status_code == 404
    assert employee.post('/api/feedback', json={'project_id': beta['id'], 'text': 'Attempted cross-project write.'}).status_code == 404
    assert employee.put(f'/api/feedback/{first["id"]}', json={'project_id': beta['id'], 'text': 'Move outside my project.'}).status_code == 409
    manual = employee.post('/api/feedback', json={'project_id': alpha['id'], 'text':'An editable manual report.'}).json()
    assert employee.put(f'/api/feedback/{manual["id"]}', json={'project_id': beta['id'], 'text':'Move outside my project.'}).status_code == 404
    assert employee.post(f'/api/projects/{beta["id"]}/intake-link', json={}).status_code == 404
    assert employee.put(f'/api/projects/{beta["id"]}', json={'name': 'Unauthorized rename'}).status_code == 404
    directory = employee.get('/api/employees').json()
    assert [m['id'] for m in directory] == [people['employee_ids'][0]]
    assert client.get(f'/api/feedback/{other["id"]}').status_code == 200


def test_project_membership_changes_are_owner_only_and_assignment_is_project_scoped(client, people):
    alpha = people['projects'][0]['id']
    employee = people['employees'][0]
    fid = people['records'][0]['id']
    assert employee.post(f'/api/projects/{alpha}/members/employee', json={'email':'blair@project.test'}).status_code == 403
    assert employee.patch(f'/api/projects/{alpha}/access', json={'mode':'members'}).status_code == 403
    assert patch(client, fid, status='in_progress', employee=people['employee_ids'][1]).status_code == 422
    assert client.post(f'/api/projects/{alpha}/members/employee', json={'email':'blair@project.test'}).status_code == 200
    colleague = next(row for row in employee.get('/api/employees').json() if row['id'] == people['employee_ids'][1])
    assert colleague['project_ids'] == [alpha]
    state = patch(client, fid, status='in_progress', employee=people['employee_ids'][1]).json()
    assert state['status'] == 'in_progress'
    assert client.delete(f'/api/projects/{alpha}/members/employee/{people["employee_ids"][1]}').status_code == 200
    assert people['employees'][1].get(f'/api/feedback/{fid}').status_code == 404
    state = client.get(f'/api/feedback/{fid}/workflow').json()
    assert state['assigned_employee_id'] is None and state['version'] == 2


def test_members_only_projects_require_customer_grant_and_keep_reports_individual(client, people):
    alpha = people['projects'][0]['id']
    record = people['records'][0]
    other = people['customers'][1]
    assert client.patch(f'/api/projects/{alpha}/access', json={'mode':'members'}).status_code == 200
    with TestClient(app) as guest:
        assert guest.get(f'/api/public/intake/{record["link"]}').status_code == 401
        assert guest.post(f'/api/public/intake/{record["link"]}/submissions', json={'client_nonce':'guest-attempt-nonce-123456','text':'Blocked'}).status_code == 401
    assert other.get(f'/api/public/intake/{record["link"]}').status_code == 403
    assert other.post('/api/customer/projects', json={'token':record['link']}).status_code == 403
    assert client.post(f'/api/projects/{alpha}/members/customer', json={'email':'customer1@project.test'}).status_code == 200
    assert other.get(f'/api/public/intake/{record["link"]}').status_code == 403
    import re
    outbox = client.get('/api/team/outbox').json()
    mail = next(mail for mail in outbox if mail['recipient'] == 'customer1@project.test' and '/verify/' in mail['body'])
    verify_token = re.search(r'/verify/([A-Za-z0-9_-]{43})', mail['body'])[1]
    assert other.post('/api/auth/accounts/customer/verify/complete', json={'token': verify_token}).status_code == 200
    assert other.get(f'/api/public/intake/{record["link"]}').status_code == 200
    assert other.get(f'/api/public/submissions/{record["token"]}').status_code == 404
    assert client.delete(f'/api/projects/{alpha}/members/customer/{people["records"][1]["customer_id"]}').status_code == 200
    client.patch(f'/api/projects/{alpha}/access', json={'mode':'link'})
    assert other.post('/api/customer/projects', json={'token':record['link']}).status_code == 403
    assert other.get(f'/api/public/intake/{record["link"]}').status_code == 403


def test_customer_removal_hides_reports_images_conversations_and_notifications(client, people):
    customer = people['customers'][0]
    record = people['records'][0]
    client.post(f'/api/feedback/{record["id"]}/messages', json={'body':'A reply before access removal.'})
    assert customer.get('/api/auth/notifications/customer').json()['unread_count'] == 1
    alpha = people['projects'][0]['id']
    assert client.delete(f'/api/projects/{alpha}/members/customer/{record["customer_id"]}').status_code == 200
    assert customer.get('/api/customer/reports').json() == []
    assert customer.get('/api/customer/projects').json() == []
    assert customer.get('/api/auth/notifications/customer').json()['items'] == []
    for suffix in ('', '/messages', '/attachments/unknown/content'):
        assert customer.get(f'/api/public/submissions/{record["token"]}' + suffix).status_code == 403
    assert customer.post(f'/api/public/submissions/{record["token"]}/messages', json={'body':'Blocked'}).status_code == 403
    assert client.post(f'/api/projects/{alpha}/members/customer', json={'email':'customer0@project.test'}).status_code == 200
    assert customer.get(f'/api/public/submissions/{record["token"]}').status_code == 200


def test_notifications_are_recipient_scoped_and_private_notes_never_alert_customers(client, people):
    customer = people['customers'][0]
    employee = people['employees'][0]
    other_employee = people['employees'][1]
    fid = people['records'][0]['id']
    assert employee.get('/api/auth/notifications/company').json()['unread_count'] == 1
    assert employee.post(f'/api/feedback/{fid}/messages', json={'body':'Public response'}).status_code == 201
    inbox = customer.get('/api/auth/notifications/customer').json()
    assert inbox['unread_count'] == 1 and inbox['items'][0]['kind'] == 'company_reply'
    assert other_employee.get('/api/auth/notifications/company').json()['unread_count'] == 1
    assert employee.post(f'/api/feedback/{fid}/messages', json={'body':'Private secret', 'visibility':'internal'}).status_code == 201
    assert customer.get('/api/auth/notifications/customer').json()['unread_count'] == 1
    assert 'Private secret' not in customer.get('/api/auth/notifications/customer').text
    assert customer.post('/api/auth/notifications/customer/'+inbox['items'][0]['id']+'/read').status_code == 200
    assert customer.get('/api/auth/notifications/customer').json()['unread_count'] == 0
    assert people['customers'][1].post('/api/auth/notifications/customer/'+inbox['items'][0]['id']+'/read').status_code == 404
    assert employee.post('/api/auth/notifications/company/'+inbox['items'][0]['id']+'/read').status_code == 404
    token = people['records'][0]['token']
    customer.post(f'/api/public/submissions/{token}/messages', json={'body':'Another detail'})
    assert employee.get('/api/auth/notifications/company').json()['unread_count'] == 2
    assert employee.post('/api/auth/notifications/company/read-all').json()['unread_count'] == 0
    assert other_employee.get('/api/auth/notifications/company').json()['unread_count'] == 1


def test_retest_alerts_open_only_current_accessible_report_and_reading_marks_them_read(client, people):
    record = people['records'][0]
    customer = people['customers'][0]
    employee_id = people['employee_ids'][0]
    state = patch(client, record['id'], status='in_progress', employee=employee_id).json()
    patch(client, record['id'], version=state['version'], status='ready_to_retest', employee=employee_id)
    inbox = customer.get('/api/auth/notifications/customer').json()
    assert inbox['items'][0]['kind'] == 'retest_requested'
    assert inbox['items'][0]['url'] == '/s/' + record['token']
    assert customer.post('/api/auth/notifications/customer/read-report', json={'report':record['token']}).json()['changed'] is True
    assert customer.get('/api/auth/notifications/customer').json()['unread_count'] == 0
    state = customer.get(f'/api/public/submissions/{record["token"]}').json()['workflow']
    assert customer.post(f'/api/public/submissions/{record["token"]}/retest', json={'version':state['retest_version'],'outcome':'works'}).status_code == 200
    assert people['employees'][0].get('/api/auth/notifications/company').json()['items'][0]['kind'] == 'retest_result'


def test_email_alerts_are_opt_in_and_use_local_outbox_without_private_content(client, people):
    customer = people['customers'][0]
    fid = people['records'][0]['id']
    assert customer.get('/api/auth/notifications/customer').json()['email_enabled'] is False
    client.post(f'/api/feedback/{fid}/messages', json={'body':'Do not put report content into emails.'})
    with database() as db:
        assert db.scalar(select(func.count()).select_from(MailMessage).where(MailMessage.notification_id.is_not(None))) == 0
    assert customer.patch('/api/auth/notifications/customer/preferences', json={'email_enabled':True}).status_code == 200
    client.post(f'/api/feedback/{fid}/messages', json={'body':'Sensitive customer reply text stays inside the app.'})
    with database() as db:
        mail = db.scalar(select(MailMessage).where(MailMessage.notification_id.is_not(None)))
        assert mail.delivery == 'local' and mail.recipient == 'customer0@project.test'
        assert 'Sensitive customer reply text' not in mail.body
        assert '/s/' + people['records'][0]['token'] in mail.body
    customer.patch('/api/auth/notifications/customer/preferences', json={'email_enabled':False})
    client.post(f'/api/feedback/{fid}/messages', json={'body':'Email now disabled.'})
    with database() as db:
        assert db.scalar(select(func.count()).select_from(MailMessage).where(MailMessage.notification_id.is_not(None))) == 1
    assert client.delete(f'/api/feedback/{fid}').status_code == 200
    assert customer.get('/api/auth/notifications/customer').json()['items'] == []
    with database() as db:
        assert db.scalar(select(func.count()).select_from(MailMessage).where(MailMessage.notification_id.is_not(None))) == 0


def test_removed_employee_cannot_read_prior_alerts_or_keep_receiving_new_ones(client, people):
    employee = people['employees'][0]
    alpha = people['projects'][0]['id']
    old = employee.get('/api/auth/notifications/company').json()['items'][0]['id']
    client.delete(f'/api/projects/{alpha}/members/employee/{people["employee_ids"][0]}')
    assert employee.get('/api/auth/notifications/company').json()['items'] == []
    assert employee.post('/api/auth/notifications/company/'+old+'/read').status_code == 404
    token = people['records'][0]['token']
    people['customers'][0].post(f'/api/public/submissions/{token}/messages', json={'body':'Only current members should see this.'})
    assert employee.get('/api/auth/notifications/company').json()['unread_count'] == 0
    assert employee.post('/api/auth/notifications/company/read-report', json={'report':people['records'][0]['id']}).status_code == 404


def test_notification_apis_require_the_matching_role_and_reject_bad_origins(client):
    with TestClient(app) as guest:
        for audience in ('company','customer'):
            assert guest.get('/api/auth/notifications/'+audience).status_code == 401
            assert guest.post('/api/auth/notifications/'+audience+'/read-all').status_code == 401
            assert guest.patch('/api/auth/notifications/'+audience+'/preferences', json={'email_enabled':True}).status_code == 401
        assert guest.post('/api/auth/notifications/customer/read-all', headers={'Origin':'https://untrusted.test'}).status_code == 403


def test_pending_email_is_cancelled_if_project_access_is_removed(client, people, monkeypatch):
    from app.config import settings
    from app.notifications import add_alert, deliver_pending
    from app.models import Feedback
    from app import account_management
    monkeypatch.setattr(settings, 'mail_mode', 'smtp')
    record = people['records'][0]
    with database() as db:
        account = db.get(CustomerAccount, record['customer_id'])
        account.email_verified_at = now()
        db.add(NotificationPreference(scope='customer', account_id=account.id, email_enabled=1))
        db.flush()
        add_alert(db, db.get(Feedback, record['id']), 'customer', account.id, 'company_reply', 'Company replied')
        db.commit()
        assert db.scalar(select(MailMessage).where(MailMessage.notification_id.is_not(None))).delivery == 'pending'
    client.delete(f'/api/projects/{people["projects"][0]["id"]}/members/customer/{record["customer_id"]}')
    def forbidden(*args, **kwargs):
        pytest.fail('A revoked project member must not receive email')
    monkeypatch.setattr(account_management.smtplib, 'SMTP', forbidden)
    deliver_pending(app.state.session_factory)
    with database() as db:
        mail = db.scalar(select(MailMessage).where(MailMessage.notification_id.is_not(None)))
        assert mail.delivery == 'cancelled' and mail.body == ''


def test_failed_notification_delivery_does_not_lose_the_reply(client, people, monkeypatch):
    from app.config import settings
    from app import account_management
    record = people['records'][0]
    people['customers'][0].patch('/api/auth/notifications/customer/preferences', json={'email_enabled': True})
    with database() as db:
        db.get(CustomerAccount, record['customer_id']).email_verified_at = now()
        db.commit()
    monkeypatch.setattr(settings, 'mail_mode', 'smtp')
    monkeypatch.setattr(settings, 'smtp_host', 'smtp.example.test')
    monkeypatch.setattr(settings, 'smtp_from', 'sender@example.test')
    def unavailable(*args, **kwargs):
        raise OSError('Test sender unavailable')
    monkeypatch.setattr(account_management.smtplib, 'SMTP', unavailable)
    result = client.post(f'/api/feedback/{record["id"]}/messages', json={'body':'A saved reply despite email failure.'})
    assert result.status_code == 201 and result.json()[-1]['body'] == 'A saved reply despite email failure.'
    with database() as db:
        mail = db.scalar(select(MailMessage).where(MailMessage.notification_id.is_not(None)))
        assert mail.delivery == 'failed' and mail.body == ''
    assert people['customers'][0].get('/api/auth/notifications/customer').json()['unread_count'] == 1


def test_repeated_submit_and_noop_progress_do_not_duplicate_alerts(client, people):
    record = people['records'][0]
    employee = people['employees'][0]
    assert employee.get('/api/auth/notifications/company').json()['unread_count'] == 1
    for _ in range(2):
        assert people['customers'][0].post(f'/api/public/submissions/{record["token"]}/submit', json={'draft_version': people['customers'][0].get((f"/api/public/submissions/{record['token']}/submit").removesuffix('/submit')).json().get('draft_version', 1)}).status_code == 200
        assert patch(client, record['id']).status_code == 200
    assert employee.get('/api/auth/notifications/company').json()['unread_count'] == 1
    assert people['customers'][0].get('/api/auth/notifications/customer').json()['unread_count'] == 0
