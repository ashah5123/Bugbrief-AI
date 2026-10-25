import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";
const base = "http://127.0.0.1:15173";
async function post(request: APIRequestContext, path: string, data: unknown) {
  const response = await request.post(api + path, { data }); expect(response.ok(), `${path}: ${response.status()}`).toBe(true); return response.json();
}
async function nav(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).waitFor({ state: 'attached' });
  const menu = page.getByRole('button', { name: 'Open navigation', exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: new RegExp('^' + name) }).click();
}
async function seed(request: APIRequestContext, name: string) {
  const project = await post(request, '/projects', { name });
  const link = await post(request, `/projects/${project.id}/intake-link`, {});
  await post(request, `/projects/${project.id}/members/employee`, { email: 'workflow-employee@example.com' });
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find((person: { name: string }) => person.name === 'Workflow Employee');
  const rows = [];
  for (let index = 0; index < 4; index++) {
    const row = await post(request, '/feedback', { project_id: project.id, text: `Health issue ${index} ${name}` });
    rows.push(row);
    if (index > 0) {
      let state = await (await request.patch(`${api}/feedback/${row.id}/workflow`, { data: { version: 0, status: 'in_progress', assigned_employee_id: employee.id } })).json();
      if (index >= 2) state = await (await request.patch(`${api}/feedback/${row.id}/workflow`, { data: { version: state.version, status: 'ready_to_retest', assigned_employee_id: employee.id, fix_details: { summary: 'Corrected checkout.', location: 'Staging.', steps: 'Repeat checkout.' } } })).json();
      if (index === 3) expect((await request.patch(`${api}/feedback/${row.id}/workflow`, { data: { version: state.version, status: 'resolved', assigned_employee_id: employee.id } })).ok()).toBe(true);
    }
  }
  expect((await request.patch(`${api}/feedback/${rows[1].id}/triage`, { data: { version: 1, priority: 'urgent', due_date: '2020-01-01' } })).ok()).toBe(true);
  const archived = await post(request, '/feedback', { project_id: project.id, text: 'Archived health report' });
  expect((await request.patch(`${api}/feedback/${archived.id}/archive`, { data: { archived: true } })).ok()).toBe(true);
  const customer = await post(request, `/public/intake/${link.token}/submissions`, { client_nonce: `health-${project.id}-customer-nonce-123456`, text: 'Customer waiting for help.' });
  await post(request, `/public/submissions/${customer.access_token}/submit`, { draft_version: customer.draft_version });
  await post(request, `/public/intake/${link.token}/submissions`, { client_nonce: `health-${project.id}-unsent-nonce-123456`, text: 'Unsent private report.' });
  return { project, rows, archived };
}

test('project counts exclude archives, resolved work and unsent customer drafts; each count opens its exact queue', async ({ page, request }, info) => {
  const { project, rows } = await seed(request, `Project health ${info.project.name}`);
  const empty = await post(request, '/projects', { name: `Empty health ${info.project.name}` });
  await page.goto('/workspace');
  const overview = page.getByRole('region', { name: 'Project health overview', exact: true });
  const group = overview.getByRole('group', { name: `Health for ${project.name}`, exact: true });
  const expected = [['Open reports', 4], ['Overdue work', 1], ['Customers awaiting reply', 1], ['Awaiting retest', 1], ['Unassigned reports', 2]] as const;
  for (const [label, count] of expected) await expect(group.getByRole('button', { name: `${count} ${label}`, exact: true })).toBeVisible();
  await expect(overview.getByRole('group', { name: `Health for ${empty.name}`, exact: true })).toContainText('No active reports');
  await overview.screenshot({ path: `../test-results/${info.project.name}-project-health.png` });
  for (const [label, count] of expected) {
    await nav(page, 'Overview');
    await group.getByRole('button', { name: `${count} ${label}`, exact: true }).click();
    await expect(page.getByLabel('Filter by project', { exact: true })).toHaveValue(project.id);
    await expect(page.locator('.feedback-row')).toHaveCount(count);
    await expect(page.locator(`[data-report-id="${rows[3].id}"]`)).toHaveCount(0);
  }
  await nav(page, 'Projects');
  const cards = page.getByRole('group', { name: `Health for ${project.name}`, exact: true });
  await cards.getByRole('button', { name: '1 Overdue work', exact: true }).click();
  await expect(page.locator('.feedback-row')).toHaveCount(1);
  await expect(page.locator(`[data-report-id="${rows[1].id}"]`)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('personal views restore filters across browsers and protect changed views from stale edits or deletes', async ({ page, request, browser }, info) => {
  const { project, archived } = await seed(request, `Saved inbox ${info.project.name}`);
  await page.goto('/workspace');
  await nav(page, 'Feedback inbox');
  await page.getByLabel('Filter by project', { exact: true }).selectOption(project.id);
  await page.getByRole('button', { name: 'Archived reports', exact: true }).click();
  await page.getByLabel('Search feedback', { exact: true }).fill('Archived health');
  await page.locator('.more-filters > summary').click();
  await page.getByLabel('Filter by priority', { exact: true }).selectOption('normal');
  await page.getByLabel('Sort reports', { exact: true }).selectOption('newest');
  const saved = page.getByRole('region', { name: 'Saved views', exact: true });
  await expect(saved.getByLabel('View name', { exact: true })).toBeHidden();
  await saved.locator('.saved-view-management > summary').click();
  const name = `Archived queue ${info.project.name}`;
  await saved.getByLabel('View name', { exact: true }).fill(name);
  await saved.getByRole('button', { name: 'Save as new view', exact: true }).click();
  await expect(saved.getByRole('status')).toContainText('View saved');
  const viewId = await saved.getByLabel('Saved view', { exact: true }).inputValue();
  await page.reload();
  await saved.getByLabel('Saved view', { exact: true }).selectOption(viewId);
  await saved.getByRole('button', { name: 'Open view', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Archived reports', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Sort reports', { exact: true })).toHaveValue('newest');
  await expect(page.getByLabel('Sort reports', { exact: true })).toBeHidden();
  await expect(page.getByRole('group', { name: 'Applied additional filters' })).toContainText('Newest first');
  await saved.screenshot({ path: `../test-results/${info.project.name}-compact-saved-views.png` });
  await expect(page.locator('.feedback-row')).toHaveCount(1);
  await expect(page.locator(`[data-report-id="${archived.id}"]`)).toBeVisible();
  const fresh = await browser.newContext({ extraHTTPHeaders: { 'X-Agency-Key': 'e2e-agency-access-code' } });
  try {
    const second = await fresh.newPage(); await second.goto(base + '/workspace');
    const other = second.getByRole('region', { name: 'Saved views', exact: true });
    await other.getByLabel('Saved view', { exact: true }).selectOption(viewId);
    await other.getByRole('button', { name: 'Open view', exact: true }).click();
    await expect(second.locator('.feedback-row')).toHaveCount(1);
    await expect(second.getByLabel('Search feedback', { exact: true })).toHaveValue('Archived health');
  } finally { await fresh.close(); }
  const latest = await (await request.get(`${api}/saved-views/${viewId}`)).json();
  expect((await request.patch(`${api}/saved-views/${viewId}`, { data: { name: name + ' renamed', filters: latest.filters, version: latest.version } })).ok()).toBe(true);
  await saved.locator('.saved-view-management > summary').click();
  await saved.getByLabel('View name', { exact: true }).fill(name + ' local edit');
  await saved.locator('.saved-view-management > summary').click();
  await saved.locator('.saved-view-management > summary').click();
  await expect(saved.getByLabel('View name', { exact: true })).toHaveValue(name + ' local edit');
  await saved.getByRole('button', { name: 'Update saved view', exact: true }).click();
  await expect(saved.getByRole('alert')).toContainText('Saved views changed');
  await expect(saved.getByLabel('View name', { exact: true })).toHaveValue(name + ' local edit');
  await saved.getByRole('button', { name: 'Reload saved views', exact: true }).click();
  await saved.getByLabel('Saved view', { exact: true }).selectOption(viewId);
  await saved.screenshot({ path: `../test-results/${info.project.name}-saved-views.png` });
  await saved.getByRole('button', { name: 'Delete saved view', exact: true }).click();
  await saved.getByRole('button', { name: 'Confirm delete view', exact: true }).click();
  await expect(saved.getByRole('status')).toHaveText('Saved view deleted');
  expect((await request.get(`${api}/feedback/${archived.id}`)).ok()).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('employee views stay private and revoked project views cannot silently open all projects', async ({ browser, request }, info) => {
  const project = await post(request, '/projects', { name: `Private view ${info.project.name}` });
  const foreign = await post(request, '/projects', { name: `Hidden overview ${info.project.name}` });
  const email = `experience-${info.project.name}@example.test`;
  await post(request, `/projects/${project.id}/members/employee`, { email });
  const context = await browser.newContext({ extraHTTPHeaders: {}, viewport: info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1280, height: 900 } });
  try {
    const token = Buffer.alloc(32, info.project.name === 'desktop' ? 'f' : 'g').toString('base64url');
    await context.addCookies([{ name: 'bugbrief_employee', value: token, url: base }]);
    const account = await (await context.request.get(`${api}/auth/session`)).json();
    const personal = await post(context.request, '/saved-views', { name: `My scoped queue ${info.project.name}`, filters: { project_id: project.id, assignee: 'me' } });
    expect((await (await request.get(`${api}/saved-views`)).json()).some((row: { id: string }) => row.id === personal.id)).toBe(false);
    const page = await context.newPage(); await page.goto(base + '/workspace');
    await nav(page, 'Overview');
    const overview = page.getByRole('region', { name: 'Project health overview', exact: true });
    await expect(overview.getByText(project.name, { exact: true })).toBeVisible();
    await expect(overview.getByText(foreign.name, { exact: true })).toHaveCount(0);
    const saved = page.getByRole('region', { name: 'Saved views', exact: true });
    await saved.getByLabel('Saved view', { exact: true }).selectOption(personal.id);
    expect((await request.delete(`${api}/projects/${project.id}/members/employee/${account.employee.id}`)).ok()).toBe(true);
    // Opening revalidates access even before the next focus/poll refresh.
    await saved.getByRole('button', { name: 'Open view', exact: true }).click();
    await expect(saved.getByText(/This view uses a project/).first()).toBeVisible();
    await expect(saved.getByRole('button', { name: 'Open view', exact: true })).toBeDisabled();
    await page.reload(); await nav(page, 'Overview');
    await expect(overview.getByText(project.name, { exact: true })).toHaveCount(0);
  } finally { await context.close(); }
});
