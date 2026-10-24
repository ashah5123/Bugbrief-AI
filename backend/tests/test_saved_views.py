"""Private inbox preferences, validated references, bounded storage and conflict-safe writes."""
from fastapi.testclient import TestClient
from app.main import app
from test_project_notifications import people


def create(client, name='My queue', filters=None):
    return client.post('/api/saved-views', json={'name':name,'filters':filters or {}})


def test_owner_views_trim_names_persist_all_filters_and_reject_stale_updates_and_deletes(client, people):
    filters={'view':'reports','archive':True,'search':'Checkout','project_id':people['projects'][0]['id'],
        'status':'review','progress':'in_progress','priority':'urgent','attention':'overdue',
        'assignee':people['employee_ids'][0],'customer':'customer:'+people['records'][0]['customer_id'],'sort':'due'}
    response=create(client,'  My overdue queue  ',filters)
    assert response.status_code==201
    row=response.json();assert row['name']=='My overdue queue' and row['filters']==filters and not row['unavailable']
    assert client.get('/api/saved-views').json()==[row]
    assert client.get('/api/saved-views/'+row['id']).json()==row
    data={'name':'Updated queue','filters':filters,'version':row['version']}
    updated=client.patch('/api/saved-views/'+row['id'],json=data)
    assert updated.status_code==200 and updated.json()['version']==2
    assert client.patch('/api/saved-views/'+row['id'],json=data).status_code==409
    assert client.request('DELETE','/api/saved-views/'+row['id'],json={'version':1}).status_code==409
    assert client.request('DELETE','/api/saved-views/'+row['id'],json={'version':2}).status_code==200
    assert client.get('/api/saved-views').json()==[]
    assert client.get('/api/feedback/'+people['records'][0]['id']).status_code==200


def test_views_belong_only_to_active_company_identity_and_viewers_can_save_personal_preferences(client, people):
    employee,other=people['employees'];customer=people['customers'][0]
    pid=people['projects'][0]['id']; eid=people['employee_ids'][0]
    assert client.patch(f'/api/projects/{pid}/members/employee/{eid}',json={'role':'viewer','can_delete':False}).status_code==200
    owner=create(client,'Owner only').json()
    personal=create(employee,'Employee only',{'project_id':pid,'assignee':'me'}).json()
    assert personal['id']!=owner['id']
    assert [r['name'] for r in client.get('/api/saved-views').json()]==['Owner only']
    assert [r['name'] for r in employee.get('/api/saved-views').json()]==['Employee only']
    assert other.get('/api/saved-views').json()==[]
    for actor,row in [(client,personal),(employee,owner),(other,personal)]:
        path='/api/saved-views/'+row['id']
        assert actor.get(path).status_code==404
        assert actor.patch(path,json={'name':'Stolen','filters':{},'version':1}).status_code==404
        assert actor.request('DELETE',path,json={'version':1}).status_code==404
    assert customer.get('/api/saved-views').status_code==401
    assert create(customer).status_code==401
    with TestClient(app) as guest:
        assert guest.get('/api/saved-views').status_code==401
    assert client.delete('/api/team/employees/'+eid).status_code==200
    assert employee.get('/api/saved-views').status_code==401


def test_inaccessible_references_and_unsent_customers_cannot_be_used_as_filter_oracles(client, people):
    employee=people['employees'][0]; foreign=people['projects'][1]['id']
    for filters in ({'project_id':foreign},{'assignee':people['employee_ids'][1]},
        {'customer':'customer:'+people['records'][1]['customer_id']},{'project_id':'nonexistent'}, {'customer':'invented'},
        {'customer':'customer:nonexistent'}, {'assignee':'nonexistent'}):
        assert create(employee,filters=filters).status_code==404
    assert create(client,filters={'assignee':'me'}).status_code==404
    pid=people['projects'][0]['id'];token=people['records'][0]['link']
    draft=people['customers'][0].post('/api/public/intake/'+token+'/submissions',json={'client_nonce':'unsent-view-customer-nonce-12345','text':'Unsent private customer input.'}).json()
    # Existing account ownership is already visible through its submitted report. A separate guest draft is not.
    with TestClient(app) as guest:
        unsent=guest.post('/api/public/intake/'+token+'/submissions',json={'client_nonce':'unsent-guest-view-nonce-12345','text':'Private guest draft.'}).json()
        from test_workflow import database
        from sqlalchemy import select
        from app.models import CustomerSubmission
        with database() as db:
            item=db.scalar(select(CustomerSubmission).where(CustomerSubmission.access_token==unsent['access_token']))
            target=item.id
        assert create(employee,filters={'project_id':pid,'customer':'customer:'+target}).status_code==404


def test_revocation_marks_existing_view_unavailable_and_never_replaces_its_scope(client, people):
    employee=people['employees'][0];pid=people['projects'][0]['id'];eid=people['employee_ids'][0]
    row=create(employee,'One project',{'project_id':pid}).json()
    assert client.delete(f'/api/projects/{pid}/members/employee/{eid}').status_code==200
    current=employee.get('/api/saved-views/'+row['id']).json()
    assert current['unavailable'] and current['filters']['project_id']==pid
    assert employee.get('/api/saved-views').json()[0]['unavailable']
    assert employee.get('/api/feedback/'+people['records'][0]['id']).status_code==404
    assert employee.patch('/api/saved-views/'+row['id'],json={'name':row['name'],'filters':row['filters'],'version':1}).status_code==404
    assert client.post(f'/api/projects/{pid}/members/employee',json={'email':'alex@project.test'}).status_code==200
    assert employee.get('/api/saved-views/'+row['id']).json()['unavailable'] is False
    assert client.delete('/api/feedback/'+people['records'][0]['id']).status_code==200
    assert employee.get('/api/saved-views/'+row['id']).json()['unavailable'] is False # An empty accessible project remains valid.


def test_removed_assignee_and_deleted_customer_filters_are_unavailable(client, people):
    employee=people['employees'][0];pid=people['projects'][0]['id']
    person=create(employee,'Assigned work',{'assignee':people['employee_ids'][0]}).json()
    customer=create(employee,'Customer work',{'customer':'customer:'+people['records'][0]['customer_id']}).json()
    assert client.delete('/api/feedback/'+people['records'][0]['id']).status_code==200
    assert employee.get('/api/saved-views/'+customer['id']).json()['unavailable']
    assert client.delete(f'/api/projects/{pid}/members/employee/{people["employee_ids"][0]}').status_code==200
    assert employee.get('/api/saved-views/'+person['id']).json()['unavailable']


def test_view_names_are_casefold_unique_and_storage_limit_reuses_deleted_slot(client):
    first=create(client,'Straße').json()
    assert create(client,'STRASSE').status_code==409
    for number in range(19):
        assert create(client,'Queue '+str(number)).status_code==201
    assert create(client,'Queue 21').status_code==422
    assert len(client.get('/api/saved-views').json())==20
    assert client.request('DELETE','/api/saved-views/'+first['id'],json={'version':1}).status_code==200
    assert create(client,'Replacement').status_code==201
    assert len(client.get('/api/saved-views').json())==20


def test_filters_validate_bounds_enums_and_cannot_inject_another_owner(client):
    for filters in ({'search':'x'*201},{'project_id':'x'*101},{'progress':'invented'},
        {'attention':'invented'},{'view':'overview'},{'archive':'maybe'},{'sort':'invented'},{'owner':'someone'}):
        assert create(client,filters=filters).status_code==422
    for name in ('   ','x'*81):
        assert create(client,name).status_code==422
    assert client.post('/api/saved-views',json={'name':'Injected','filters':{},'account_id':'another'}).status_code==422
