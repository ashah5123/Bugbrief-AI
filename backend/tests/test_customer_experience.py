"""Customer onboarding metadata remains scoped and preserves project settings."""
from fastapi.testclient import TestClient
from app.main import app
from test_project_notifications import people


def test_team_name_is_trimmed_public_and_preserved_by_older_project_updates(client):
    project = client.post('/api/projects', json={'name': 'Customer storefront', 'team_name': '  Acme support  '}).json()
    assert project['team_name'] == 'Acme support'
    link = client.post(f'/api/projects/{project["id"]}/intake-link', json={}).json()['token']
    with TestClient(app) as guest:
        assert guest.get(f'/api/public/intake/{link}').json()['team_name'] == 'Acme support'
        record = guest.post(f'/api/public/intake/{link}/submissions', json={'text': 'Customer-owned context', 'client_nonce': 'team-name-customer-nonce-12345'}).json()
        assert record['team_name'] == 'Acme support'
        assert guest.put(f'/api/projects/{project["id"]}', json={'name': 'Tampered', 'team_name': 'Impersonator'}).status_code == 401
    updated = client.put(f'/api/projects/{project["id"]}', json={'name': 'Renamed', 'url': 'https://example.test'}).json()
    assert updated['team_name'] == 'Acme support'
    assert client.put(f'/api/projects/{project["id"]}', json={'name': 'Renamed', 'team_name': ''}).json()['team_name'] == ''
    assert client.post('/api/projects', json={'name': 'Invalid', 'team_name': 'x'*101}).status_code == 422


def test_customer_project_team_and_report_summary_are_account_scoped(client, people):
    first, other = people['records']
    project = people['projects'][0]
    assert client.put(f'/api/projects/{project["id"]}', json={'name': project['name'], 'team_name': 'Project Alpha team'}).status_code == 200
    customer = people['customers'][0]
    projects = customer.get('/api/customer/projects').json()
    assert len(projects) == 1 and projects[0]['team_name'] == 'Project Alpha team'
    reports = customer.get('/api/customer/reports').json()
    assert len(reports) == 1 and reports[0]['access_token'] == first['token']
    assert reports[0]['summary'] == 'Checkout is not responding.'
    assert other['token'] not in str(reports)
    assert not {'report', 'priority', 'due_date', 'assigned_employee_id'} & reports[0].keys()
    assert people['employees'][0].put(f'/api/projects/{people["projects"][1]["id"]}', json={'name': 'Other', 'team_name': 'Forbidden'}).status_code == 404
    assert people['customers'][1].get('/api/customer/projects').json()[0]['team_name'] == ''
