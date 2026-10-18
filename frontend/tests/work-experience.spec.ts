import { test, expect, type APIRequestContext } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";
const base = "http://127.0.0.1:15173";
async function post(request: APIRequestContext, path: string, data: unknown) {
  const response = await request.post(`${api}${path}`, { data });
  expect(response.ok(), `${path}: ${response.status()}`).toBe(true);
  return response.json();
}
async function progress(request: APIRequestContext, id: string, employee: string, status: string) {
  const current = await (await request.get(`${api}/feedback/${id}/workflow`)).json();
  const response = await request.patch(`${api}/feedback/${id}/workflow`, { data: {
    version: current.version, status, assigned_employee_id: employee,
    note: status === "needs_information" ? "Which browser did you use?" : "",
  } });
  expect(response.ok()).toBe(true);
}

test("employee lands on personal work queues; other assignees and projects stay out", async ({ browser, request }, info) => {
  const email = `experience-${info.project.name}@example.test`;
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  try {
    const employeeToken = Buffer.alloc(32, info.project.name === "desktop" ? "f" : "g").toString("base64url");
    await context.addCookies([{ name: "bugbrief_employee", value: employeeToken, url: base }]);
    const auth = await (await context.request.get(`${api}/auth/session`)).json();
    const employee = auth.employee.id;
    const project = await post(request, "/projects", { name: `Personal queue ${info.project.name}` });
    await post(request, `/projects/${project.id}/members/employee`, { email });
    await post(request, `/projects/${project.id}/members/employee`, { email: "workflow-employee@example.com" });
    const colleagues = await (await request.get(`${api}/employees`)).json();
    const other = colleagues.find((person: { name: string }) => person.name === "Workflow Employee").id;
    const overdue = await post(request, "/feedback", { project_id: project.id, text: "My overdue issue" });
    await progress(request, overdue.id, employee, "new");
    expect((await request.patch(`${api}/feedback/${overdue.id}/triage`, { data: { version: 1, priority: "urgent", due_date: "2020-01-01" } })).ok()).toBe(true);
    const link = await post(request, `/projects/${project.id}/intake-link`, {});
    const records: string[] = [];
    for (const stage of ["waiting", "retest"]) {
      const record = await post(request, `/public/intake/${link.token}/submissions`, { text: `My ${stage} customer issue`, client_nonce: `personal-${info.project.name}-${stage}-123456789` });
      await post(request, `/public/submissions/${record.access_token}/submit`, {});
      const items = await (await request.get(`${api}/feedback`)).json();
      const item = items.find((row: { text: string; project_id: string }) => row.project_id === project.id && row.text === `My ${stage} customer issue`);
      records.push(item.id);
      await progress(request, item.id, employee, "in_progress");
      if (stage === "retest") await progress(request, item.id, employee, "ready_to_retest");
      else await post(request, `/public/submissions/${record.access_token}/messages`, { body: "Any news from the team?" });
    }
    const otherReport = await post(request, "/feedback", { project_id: project.id, text: "Another employee owns this" });
    await progress(request, otherReport.id, other, "new");
    const resolved = await post(request, "/feedback", { project_id: project.id, text: "My completed issue" });
    for (const status of ["in_progress", "ready_to_retest", "resolved"]) await progress(request, resolved.id, employee, status);
    const secretProject = await post(request, "/projects", { name: "Unrelated private project" });
    const secret = await post(request, "/feedback", { project_id: secretProject.id, text: "Unrelated confidential issue" });
    const page = await context.newPage();
    await page.goto(`${base}/workspace`);
    await expect(page.getByRole("heading", { name: "Your work, with a clear next step." })).toBeVisible();
    const work = page.getByRole("region", { name: "My work", exact: true });
    await expect(work.locator(".my-work-item")).toHaveCount(3);
    await expect(work).not.toContainText("Another employee owns this");
    await expect(work).not.toContainText("My completed issue");
    expect((await context.request.get(`${api}/feedback/${secret.id}`)).status()).toBe(404);
    for (const [label, id] of [["Overdue", overdue.id], ["Customers awaiting reply", records[0]], ["Awaiting retest", records[1]]]) {
      await work.locator(".my-work-queues").getByRole("button", { name: new RegExp(label) }).click();
      await expect(work.locator(".my-work-item")).toHaveCount(1);
      await expect(work.locator(`[data-work-report-id="${id}"]`)).toBeVisible();
    }
    await work.locator(".my-work-queues").getByRole("button", { name: /Customers awaiting reply/ }).click();
    await page.screenshot({ path: `../test-results/${info.project.name}-my-work.png`, fullPage: true });
    await work.locator(".my-work-item").click();
    await expect(page.locator(".capture-card > .next-step")).toContainText("Reply to the customer");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  } finally { await context.close(); }
});

test("new customer connects a named team; returning customer sees reports and required actions first", async ({ browser, page, request }, info) => {
  const project = await post(request, "/projects", { name: `Guided project ${info.project.name}` });
  const link = await post(request, `/projects/${project.id}/intake-link`, {});
  await post(request, `/projects/${project.id}/members/employee`, { email: "workflow-employee@example.com" });
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find((row: { name: string }) => row.name === "Workflow Employee").id;
  // Configure the customer-facing team name using the company's actual settings UI.
  await page.goto("/workspace");
  await page.getByRole("button", { name: /Collect customer feedback/ }).click();
  const sharing = page.getByRole("dialog", { name: "Collect customer feedback" });
  await sharing.getByLabel("Project", { exact: true }).selectOption(project.id);
  await sharing.getByLabel("Company or team name shown to customers", { exact: true }).fill("Acme support team");
  await sharing.getByRole("button", { name: "Save team name", exact: true }).click();
  await expect(sharing.getByRole("button", { name: "Team name saved", exact: true })).toBeVisible();
  await sharing.getByRole("button", { name: "Close sharing dialog", exact: true }).click();
  const customer = await browser.newContext({ extraHTTPHeaders: {} });
  try {
    await customer.addCookies([{ name: "bugbrief_customer", value: Buffer.alloc(32, info.project.name === "desktop" ? "h" : "i").toString("base64url"), url: base }]);
    const portal = await customer.newPage();
    await portal.goto(`${base}/customer`);
    await expect(portal.getByRole("heading", { name: "Connect your project to get started." })).toBeVisible();
    await portal.getByLabel("Project invitation", { exact: true }).fill(`${base}/c/${link.token}`);
    await portal.getByRole("button", { name: "Connect project", exact: true }).click();
    const projects = portal.locator(".customer-project-grid");
    await expect(projects).toContainText("Managed by Acme support team");
    await portal.getByRole("region", { name: "Your next step", exact: true }).getByRole("link", { name: "Report an issue", exact: true }).click();
    await expect(portal.locator(".customer-project")).toContainText("Managed by Acme support team");
    const record = await post(customer.request, `/public/intake/${link.token}/submissions`, { text: "My checkout needs fixing", client_nonce: `guided-${info.project.name}-report-123456789` });
    await post(customer.request, `/public/submissions/${record.access_token}/submit`, {});
    const draft = await post(customer.request, `/public/intake/${link.token}/submissions`, { text: "An unfinished report", client_nonce: `guided-${info.project.name}-draft-123456789` });
    const items = await (await request.get(`${api}/feedback`)).json();
    const report = items.find((row: { text: string; project_id: string }) => row.project_id === project.id && row.text === "My checkout needs fixing");
    await progress(request, report.id, employee, "needs_information");
    await portal.goto(`${base}/customer`);
    const attention = portal.getByRole("region", { name: "Reports needing your action", exact: true });
    await expect(attention).toContainText("Reply with the requested details");
    await expect(attention).toContainText("Finish and send your report");
    await expect(portal.locator(".customer-report-list")).toContainText("My checkout needs fixing");
    expect(await portal.evaluate(() => document.querySelector('.customer-report-list')!.getBoundingClientRect().top < document.querySelector('.customer-project-grid')!.getBoundingClientRect().top)).toBe(true);
    await progress(request, report.id, employee, "in_progress");
    await progress(request, report.id, employee, "ready_to_retest");
    await portal.reload();
    await attention.getByRole("link").filter({ hasText: "Try the fix" }).click();
    await expect(portal.getByRole("button", { name: "It works", exact: true })).toBeVisible();
    await expect(portal.locator(".customer-project")).toContainText("Managed by Acme support team");
    await portal.goto(`${base}/customer`);
    await expect(portal.locator(".customer-report-list article")).toHaveCount(2);
    await expect(portal.locator(".customer-project-grid")).toContainText("Acme support team");
    await portal.screenshot({ path: `../test-results/${info.project.name}-guided-customer.png`, fullPage: true });
    expect(await portal.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(draft.access_token).toBeTruthy();
  } finally { await customer.close(); }
});

test("returning portal waits for its project data and handles closed projects without a broken intake action", async ({ browser, request }, info) => {
  const project = await post(request, "/projects", { name: `Closed project ${info.project.name}`, team_name: "Support desk" });
  const link = await post(request, `/projects/${project.id}/intake-link`, {});
  const customer = await browser.newContext({ extraHTTPHeaders: {} });
  try {
    await customer.addCookies([{ name: "bugbrief_customer", value: Buffer.alloc(32, info.project.name === "desktop" ? "j" : "k").toString("base64url"), url: base }]);
    await post(customer.request, "/customer/projects", { token: link.token });
    const page = await customer.newPage();
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/customer/projects", async route => { await gate; await route.continue(); });
    await page.goto(`${base}/customer`);
    await expect(page.getByRole("heading", { name: "Opening your reports…", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Connect your project to get started.", exact: true })).toHaveCount(0);
    release();
    await expect(page.locator(".customer-project-grid")).toContainText("Support desk");
    expect((await request.delete(`${api}/projects/${project.id}/intake-link`)).ok()).toBe(true);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Your projects are closed for new reports.", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Report an issue", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "View your reports", exact: true })).toBeVisible();
  } finally { await customer.close(); }
});
