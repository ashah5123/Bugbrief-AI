import { test, expect } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";

test("triage persists and combined filters find overdue customer reports", async ({ page, request }, info) => {
  const project = await (await request.post(`${api}/projects`, { data: { name: `Triage ${info.project.name}` } })).json();
  const link = await (await request.post(`${api}/projects/${project.id}/intake-link`, { data: {} })).json();
  const records: { id: string; token: string; customerId: string }[] = [];
  for (const [index, name] of ["Jamie", "Riley"].entries()) {
    const submission = await (await request.post(`${api}/public/intake/${link.token}/submissions`, {
      data: { client_nonce: `triage-${info.project.name}-customer-${index}-123456789`, text: `${name}'s checkout problem`, reporter_name: name },
    })).json();
    expect((await request.post(`${api}/public/submissions/${submission.access_token}/submit`, { data: { draft_version: submission.draft_version } })).ok()).toBe(true);
    const items = await (await request.get(`${api}/feedback`)).json();
    const item = items.find((f: { text: string; project_id: string }) => f.project_id === project.id && f.text === `${name}'s checkout problem`);
    records.push({ id: item.id, token: submission.access_token, customerId: item.customer.id });
  }
  await page.goto(`/workspace?report=${records[0].id}`);
  const panel = page.getByRole("region", { name: "Report priority and deadline" });
  await panel.getByLabel("Report priority", { exact: true }).selectOption("urgent");
  await panel.getByLabel(/Due date/).fill("2020-02-29");
  await panel.getByRole("button", { name: "Save triage", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Triage saved");
  await page.reload();
  await expect(panel.getByLabel("Report priority", { exact: true })).toHaveValue("urgent");
  await expect(panel.getByLabel(/Due date/)).toHaveValue("2020-02-29");
  const row = page.locator(`[data-report-id="${records[0].id}"]`);
  await expect(row).toContainText("Overdue");
  await expect(row).toContainText("Customer awaiting reply");
  await page.getByLabel("Filter by project", { exact: true }).selectOption(project.id);
  await expect(page.getByLabel("Filter by priority", { exact: true })).toBeHidden();
  await page.locator(".more-filters > summary").click();
  await page.getByLabel("Filter by priority", { exact: true }).selectOption("urgent");
  await page.getByLabel("Filter by customer", { exact: true }).selectOption(`customer:${records[0].customerId}`);
  await page.getByLabel("Filter by attention", { exact: true }).selectOption("overdue");
  await page.getByLabel("Filter by assigned employee", { exact: true }).selectOption("unassigned");
  await page.getByLabel("Filter by issue progress", { exact: true }).selectOption("new");
  await page.getByRole("textbox", { name: "Search feedback", exact: true }).fill("  JAMIE  ");
  await expect(page.locator(".feedback-row")).toHaveCount(1);
  await expect(row).toBeVisible();
  await page.locator(".more-filters > summary").click();
  await expect(page.locator(".more-filters > summary")).toContainText("5 active");
  await expect(page.getByLabel("Filter by priority", { exact: true })).toBeHidden();
  await expect(page.locator(".feedback-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Remove priority filter", exact: true }).click();
  await expect(page.locator(".more-filters > summary")).toContainText("4 active");
  await expect(page.locator(".feedback-row")).toHaveCount(1);
  await page.locator(".recent-section").screenshot({ path: `../test-results/${info.project.name}-compact-inbox.png` });
  await page.locator(".more-filters > summary").click();
  await expect(page.getByLabel("Filter by priority", { exact: true })).toHaveValue("all");
  await page.getByRole("textbox", { name: "Search feedback", exact: true }).fill("Riley");
  await expect(page.locator(".feedback-row")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "No matches just yet." })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await page.getByLabel("Filter by project", { exact: true }).selectOption(project.id);
  await expect(page.locator(".feedback-row")).toHaveCount(2);
  await page.getByLabel("Sort reports", { exact: true }).selectOption("triage");
  await expect(page.locator(".feedback-row").first()).toContainText("Jamie's checkout problem");
  await request.post(`${api}/feedback/${records[0].id}/messages`, { data: { body: "Private investigation", visibility: "internal" } });
  await page.reload();
  await expect(row).toContainText("Customer awaiting reply");
  await request.post(`${api}/feedback/${records[0].id}/messages`, { data: { body: "We are looking into checkout." } });
  await page.reload();
  await expect(row).not.toContainText("Customer awaiting reply");
  await expect(row).toContainText("Overdue");
  await panel.getByRole("button", { name: "Remove due date", exact: true }).click();
  await panel.getByRole("button", { name: "Save triage", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Triage saved");
  await expect(row).not.toContainText("Overdue");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../test-results/${info.project.name}-triage.png`, fullPage: true });
});

test("stale triage shows a conflict and reloads the saved settings", async ({ page, request }, info) => {
  const project = await (await request.post(`${api}/projects`, { data: { name: `Triage conflict ${info.project.name}` } })).json();
  const item = await (await request.post(`${api}/feedback`, { data: { project_id: project.id, text: "Conflicting triage edits" } })).json();
  await page.goto(`/workspace?report=${item.id}`);
  const panel = page.getByRole("region", { name: "Report priority and deadline" });
  await expect(panel.getByLabel("Report priority", { exact: true })).toHaveValue("normal");
  await panel.getByLabel("Report priority", { exact: true }).selectOption("high");
  expect((await request.patch(`${api}/feedback/${item.id}/triage`, { data: { version: 0, priority: "urgent", due_date: "2028-01-01" } })).ok()).toBe(true);
  await panel.getByRole("button", { name: "Save triage", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Report changed in another tab");
  await panel.getByRole("button", { name: "Reload triage", exact: true }).click();
  await expect(panel.getByLabel("Report priority", { exact: true })).toHaveValue("urgent");
  await expect(panel.getByLabel(/Due date/)).toHaveValue("2028-01-01");
  await expect(panel.getByRole("button", { name: "Save triage", exact: true })).toBeDisabled();
});
