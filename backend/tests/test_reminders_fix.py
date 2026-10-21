"""Durable reminders, permission changes and explicit customer retest instructions."""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from app.main import app
from app.models import (CustomerSubmission, IssueProgress, IssueEvent, ReportMessage, Notification,
                        MailMessage, CustomerAccount, ReminderPolicy, Feedback)
from app.reminders import run_reminders, reminder_is_current
from test_workflow import database, employee, customer_report, patch
from test_project_notifications import people
from test_duplicates import records, linked, shared, group

FIX = {'summary': 'Checkout handler corrected.', 'location': 'Staging website, build 42.',
       'steps': 'Open checkout.\nPress Pay now once and check the confirmation.'}


def alerts(fid):
    with database() as db:
        return list(db.scalars(select(Notification).where(Notification.feedback_id == fid,
            Notification.kind.like('reminder_%'))))


def age_wait(fid, stamp):
    with database() as db:
        item = db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id == fid))
        item.submitted_at = (stamp-timedelta(hours=72)).isoformat()
        db.execute(update(IssueEvent).where(IssueEvent.feedback_id == fid).values(created_at=(stamp-timedelta(hours=96)).isoformat()))
        db.commit()


def test_reply_reminder_is_durable_once_per_recipient_and_waiting_episode(client, people):
    fid = people['records'][0]['id']; stamp = datetime.now(timezone.utc)
    assert patch(client, fid, employee=people['employee_ids'][0]).status_code == 200
    age_wait(fid, stamp)
    run_reminders(app.state.session_factory, stamp)
    first = alerts(fid)
    assert len(first) == 1 and first[0].kind == 'reminder_reply'
    assert (first[0].scope, first[0].account_id) == ('employee', people['employee_ids'][0])
    assert not any(n['kind'].startswith('reminder_') for n in people['employees'][1].get('/api/auth/notifications/company').json()['items'])
    assert not any(n['kind'].startswith('reminder_') for n in people['customers'][0].get('/api/auth/notifications/customer').json()['items'])
    people['employees'][0].post('/api/auth/notifications/company/read-all')
    # Fresh sessions after each scan exercise the durable receipt, including read reminders.
    run_reminders(app.state.session_factory, stamp+timedelta(hours=12))
    assert len(alerts(fid)) == 1
    with database() as db:
        db.add(ReportMessage(feedback_id=fid, visibility='public', author_role='customer', author_name='Customer',
            body='More information.', created_at=(stamp-timedelta(hours=25)).isoformat()))
        db.commit()
    run_reminders(app.state.session_factory, stamp)
    assert len(alerts(fid)) == 2
    assert people['employees'][0].post(f'/api/feedback/{fid}/messages', json={'visibility':'public','body':'We are checking this.'}).status_code == 201
    run_reminders(app.state.session_factory, stamp+timedelta(days=3))
    assert len(alerts(fid)) == 2
    with database() as db:
        assert not reminder_is_current(db, db.get(Notification, first[0].id), db.get(Feedback, fid), stamp)


def test_unassigned_reply_and_overdue_escalation_go_only_to_owner(client, people):
    fid = people['records'][0]['id']; stamp = datetime.now(timezone.utc)
    age_wait(fid, stamp)
    state=client.get(f'/api/feedback/{fid}/workflow').json()
    assert client.patch(f'/api/feedback/{fid}/triage', json={'version':state['version'],'priority':'urgent',
        'due_date':(stamp.date()-timedelta(days=1)).isoformat()}).status_code == 200
    run_reminders(app.state.session_factory, stamp)
    rows = alerts(fid)
    assert {n.kind for n in rows} == {'reminder_reply','reminder_overdue'}
    assert all((n.scope,n.account_id)==('owner','owner') for n in rows)
    run_reminders(app.state.session_factory, stamp+timedelta(days=2))
    assert len(alerts(fid)) == 2
    assert client.delete(f'/api/feedback/{fid}').status_code == 200
    run_reminders(app.state.session_factory, stamp+timedelta(days=3))
    assert not alerts(fid)


def test_deadline_uses_configured_timezone_and_changed_date_can_escalate_again(client, draft):
    policy=client.get('/api/team/reminders').json()
    assert client.patch('/api/team/reminders', json={**policy,'timezone':'America/Phoenix'}).status_code == 200
    assert client.patch(f'/api/feedback/{draft["id"]}/triage', json={'version':0,'priority':'normal','due_date':'2026-10-19'}).status_code == 200
    run_reminders(app.state.session_factory, datetime(2026,10,20,3,tzinfo=timezone.utc))
    assert not alerts(draft['id'])
    run_reminders(app.state.session_factory, datetime(2026,10,20,7,tzinfo=timezone.utc))
    assert len(alerts(draft['id'])) == 1
    state=client.get(f'/api/feedback/{draft["id"]}/workflow').json()
    client.patch(f'/api/feedback/{draft["id"]}/triage', json={'version':state['version'],'priority':'normal','due_date':'2026-10-20'})
    run_reminders(app.state.session_factory, datetime(2026,10,21,7,tzinfo=timezone.utc))
    assert len(alerts(draft['id'])) == 2


def test_retest_reminder_uses_request_time_and_stops_after_customer_confirmation(client, people):
    fid=people['records'][0]['id']; token=people['records'][0]['token']; stamp=datetime.now(timezone.utc)
    state=patch(client, fid, status='in_progress', employee=people['employee_ids'][0]).json()
    state=patch(client, fid, version=state['version'], status='ready_to_retest', employee=people['employee_ids'][0]).json()
    with database() as db:
        db.get(IssueProgress,fid).retest_requested_at=(stamp-timedelta(hours=49)).isoformat()
        db.commit()
    client.patch(f'/api/feedback/{fid}/triage', json={'version':state['version'],'priority':'high','due_date':None})
    run_reminders(app.state.session_factory, stamp)
    rows=alerts(fid)
    assert len(rows)==1 and rows[0].kind=='reminder_retest' and rows[0].account_id==people['records'][0]['customer_id']
    run_reminders(app.state.session_factory, stamp+timedelta(days=4))
    assert len(alerts(fid))==1
    customer=people['customers'][0]
    public=customer.get(f'/api/public/submissions/{token}').json()['workflow']
    assert public['fix_details']['summary']=='Checkout handler corrected.'
    assert customer.post(f'/api/public/submissions/{token}/retest',json={'version':public['retest_version'],'outcome':'works'}).status_code==200
    run_reminders(app.state.session_factory, stamp+timedelta(days=5))
    assert len(alerts(fid))==1
    with database() as db:
        assert not reminder_is_current(db,db.get(Notification,rows[0].id),db.get(Feedback,fid),stamp)


def test_pending_reminder_email_rechecks_action_and_disabled_policy(client, people, monkeypatch):
    from app.notifications import deliver_pending
    from app.config import settings
    fid=people['records'][0]['id']; stamp=datetime.now(timezone.utc)
    customer=people['customers'][0]
    with database() as db:
        db.get(CustomerAccount,people['records'][0]['customer_id']).email_verified_at=stamp.isoformat()
        db.commit()
    customer.patch('/api/auth/notifications/customer/preferences',json={'email_enabled':True})
    state=patch(client,fid,status='in_progress',employee=people['employee_ids'][0]).json()
    patch(client,fid,version=state['version'],status='ready_to_retest',employee=people['employee_ids'][0])
    with database() as db:
        db.get(IssueProgress,fid).retest_requested_at=(stamp-timedelta(hours=49)).isoformat();db.commit()
    monkeypatch.setattr(settings,'mail_mode','smtp')
    run_reminders(app.state.session_factory,stamp)
    with database() as db:
        mail=db.scalar(select(MailMessage).join(Notification,Notification.id==MailMessage.notification_id).where(Notification.kind=='reminder_retest'))
        assert mail.delivery=='pending'; mail_id=mail.id
    policy=client.get('/api/team/reminders').json()
    assert client.patch('/api/team/reminders',json={**policy,'enabled':False}).status_code==200
    sent=[]
    monkeypatch.setattr('app.notifications.deliver_mail',lambda mail:sent.append(mail.id))
    deliver_pending(app.state.session_factory)
    with database() as db:
        assert db.get(MailMessage,mail_id).delivery=='cancelled' and db.get(MailMessage,mail_id).body==''
    assert mail_id not in sent


def test_reminders_respect_revoked_private_access_disabled_employees_and_unsent_drafts(client, people):
    fid=people['records'][0]['id']; stamp=datetime.now(timezone.utc)
    state=patch(client,fid,status='in_progress',employee=people['employee_ids'][0]).json()
    patch(client,fid,version=state['version'],status='ready_to_retest',employee=people['employee_ids'][0])
    with database() as db:
        db.get(IssueProgress,fid).retest_requested_at=(stamp-timedelta(hours=49)).isoformat();db.commit()
    project=people['projects'][0]['id']
    client.patch(f'/api/projects/{project}/access',json={'mode':'members'})
    run_reminders(app.state.session_factory,stamp)
    assert not alerts(fid) # This account has not verified private access.
    client.delete(f'/api/projects/{project}/members/customer/{people["records"][0]["customer_id"]}')
    run_reminders(app.state.session_factory,stamp+timedelta(days=3))
    assert not alerts(fid)
    with database() as db:
        item=db.scalar(select(CustomerSubmission).where(CustomerSubmission.feedback_id==fid));item.stage='draft';db.commit()
    age_wait(fid,stamp)
    run_reminders(app.state.session_factory,stamp+timedelta(days=3))
    assert not alerts(fid)


def test_policy_is_owner_only_validated_and_conflict_safe(client, people):
    policy=client.get('/api/team/reminders').json()
    assert policy['reply_hours']==24 and policy['retest_hours']==48
    assert people['employees'][0].get('/api/team/reminders').status_code==403
    assert people['employees'][0].patch('/api/team/reminders',json=policy).status_code==403
    assert people['customers'][0].get('/api/team/reminders').status_code in (401,403)
    for changes in ({'reply_hours':0},{'retest_hours':721},{'timezone':'Invalid/Zone'}):
        assert client.patch('/api/team/reminders',json={**policy,**changes}).status_code==422
    assert client.patch('/api/team/reminders',json={**policy,'enabled':False}).status_code==200
    assert client.patch('/api/team/reminders',json=policy).status_code==409


def test_fix_details_required_trimmed_preserved_and_version_checked(client, customer_report, employee):
    fid=customer_report['id'];token=customer_report['token']
    state=patch(client,fid,status='in_progress',employee=employee).json()
    payload={'version':state['version'],'status':'ready_to_retest','assigned_employee_id':employee}
    for fix in (None,{}, {**FIX,'steps':'   '},{**FIX,'location':'x'*1001}):
        response=client.patch(f'/api/feedback/{fid}/workflow',json={**payload,'fix_details':fix})
        assert response.status_code==422
    assert client.get(f'/api/feedback/{fid}/workflow').json()['version']==state['version']
    response=client.patch(f'/api/feedback/{fid}/workflow',json={**payload,'fix_details':{**FIX,'summary':'  '+FIX['summary']+'  '}})
    assert response.status_code==200 and response.json()['fix_details']==FIX
    assert client.patch(f'/api/feedback/{fid}/workflow',json={**payload,'fix_details':FIX}).status_code==409
    with TestClient(app) as guest:
        public=guest.get(f'/api/public/submissions/{token}').json()['workflow']
        assert public['fix_details']==FIX
        assert guest.post(f'/api/public/submissions/{token}/retest',json={'version':public['retest_version'],'outcome':'works'}).status_code==200
        assert guest.get(f'/api/public/submissions/{token}').json()['workflow']['fix_details']==FIX
    state=client.get(f'/api/feedback/{fid}/workflow').json()
    assert patch(client,fid,version=state['version'],status='in_progress',employee=employee).json()['fix_details'] is None
    assert client.delete(f'/api/feedback/{fid}').status_code==200
    with database() as db:
        assert db.get(IssueProgress,fid) is None


def test_shared_retest_requires_details_and_retries_preserve_each_customer_instructions(client, records, employee):
    linked(client,records)
    main=records['main']
    assert shared(client,main,employee).status_code==200
    before=group(client,main)
    assert shared(client,main,employee,status='ready_to_retest',fix_details=None).status_code==422
    assert group(client,main)['version']==before['version']
    assert shared(client,main,employee,status='ready_to_retest',fix_details=FIX).status_code==200
    for row in records['customers']:
        with TestClient(app) as guest:
            public=guest.get(f'/api/public/submissions/{row["token"]}').json()['workflow']
            assert public['fix_details']==FIX and public['retest_requested_at']


def test_removed_or_disabled_assignee_receives_no_reminder_and_owner_takes_over(client, people):
    fid=people['records'][0]['id']; stamp=datetime.now(timezone.utc)
    patch(client,fid,employee=people['employee_ids'][0])
    age_wait(fid,stamp)
    assert client.delete(f'/api/projects/{people["projects"][0]["id"]}/members/employee/{people["employee_ids"][0]}').status_code==200
    run_reminders(app.state.session_factory,stamp)
    rows=alerts(fid)
    assert len(rows)==1 and rows[0].scope=='owner'
    assert not any(n['kind'].startswith('reminder_') for n in people['employees'][0].get('/api/auth/notifications/company').json()['items'])


def test_old_ready_report_can_be_read_but_requesting_again_requires_fix_details(client, customer_report, employee):
    fid=customer_report['id'];token=customer_report['token']
    with database() as db:
        db.add(IssueProgress(feedback_id=fid,status='ready_to_retest',assigned_employee_id=employee,version=3))
        db.commit()
    with TestClient(app) as guest:
        public=guest.get(f'/api/public/submissions/{token}').json()['workflow']
        assert public['status']=='ready_to_retest' and public['fix_details'] is None
    response=client.patch(f'/api/feedback/{fid}/workflow',json={'version':3,'status':'ready_to_retest',
        'assigned_employee_id':employee,'note':'Please try again.'})
    assert response.status_code==422


def test_legacy_shared_action_retry_fingerprint_remains_compatible(client, records, employee):
    import hashlib,json
    from uuid import uuid4
    from app.models import DuplicateAction
    linked(client,records)
    main=records['main'];current=group(client,main)
    payload={'version':current['version'],'request_id':str(uuid4()),'status':'in_progress',
        'assigned_employee_id':employee,'note':'Working on checkout.',
        'report_versions':{row['id']:row['workflow']['version'] for row in current['members']}}
    assert client.post(f'/api/feedback/{main}/duplicates/workflow',json=payload).status_code==200
    legacy=hashlib.sha256(json.dumps({'kind':'workflow','data':payload},sort_keys=True).encode()).hexdigest()
    with database() as db:
        assert db.get(DuplicateAction,payload['request_id']).fingerprint==legacy
    version=group(client,main)['version']
    assert client.post(f'/api/feedback/{main}/duplicates/workflow',json=payload).status_code==200
    assert group(client,main)['version']==version
