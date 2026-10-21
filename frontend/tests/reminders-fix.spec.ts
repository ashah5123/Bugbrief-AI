import { test, expect } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";
const base = "http://127.0.0.1:15173";

test("owner configures reminders with conflict protection; customer reminder opens its own fix instructions", async ({ page, request, browser }, info) => {
  const original = await (await request.get(`${api}/team/reminders`)).json();
  await page.goto("/workspace/team");
  const settings = page.getByRole("region", { name: "Automatic reminders", exact: true });
  await expect(settings.getByLabel("Enable automatic reminders")).toBeChecked();
  await settings.getByLabel("Deadline timezone").fill("America/Phoenix");
  await settings.getByLabel("Hours before reminding the employee to respond").fill("36");
  await settings.getByRole("button", { name: "Save reminder settings", exact: true }).click();
  await expect(settings.getByRole("status")).toHaveText("Reminder settings saved");
  await settings.getByLabel("Hours before reminding the customer to retest").fill("72");
  const current = await (await request.get(`${api}/team/reminders`)).json();
  expect((await request.patch(`${api}/team/reminders`, { data: { ...current, reply_hours: 40 } })).ok()).toBe(true);
  await settings.getByRole("button", { name: "Save reminder settings", exact: true }).click();
  await expect(settings.getByRole("alert")).toContainText("Reminder settings changed");
  await expect(settings.getByLabel("Hours before reminding the customer to retest")).toHaveValue("72");
  await settings.getByRole("button", { name: "Reload reminder settings", exact: true }).click();
  await expect(settings.getByLabel("Hours before reminding the employee to respond")).toHaveValue("40");
  await settings.scrollIntoViewIfNeeded();
  await settings.screenshot({ path: `../test-results/${info.project.name}-reminder-settings.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const latest = await (await request.get(`${api}/team/reminders`)).json();
  expect((await request.patch(`${api}/team/reminders`, { data: { ...original, version: latest.version } })).ok()).toBe(true);

  const customer = await browser.newContext({ extraHTTPHeaders: {}, viewport: info.project.name === "mobile" ? { width: 390, height: 844 } : { width: 1280, height: 900 } });
  try {
    const token = Buffer.alloc(32, info.project.name === "desktop" ? "t" : "u").toString("base64url");
    await customer.addCookies([{ name: "bugbrief_customer", value: token, url: base }]);
    const portal = await customer.newPage();
    await portal.goto(`${base}/customer`);
    await portal.getByRole("button", { name: /Notifications/ }).click();
    const inbox = portal.getByRole("region", { name: "Notification inbox", exact: true });
    await expect(inbox).toContainText("Reminder: a fix is waiting for your retest");
    await inbox.getByRole("link", { name: /Reminder: a fix is waiting for your retest/ }).click();
    const progress = portal.getByRole("region", { name: "Report progress", exact: true });
    await expect(progress.getByRole("region", { name: "Fix details", exact: true })).toContainText("Staging build 42.");
    await expect(progress).toContainText("Open checkout and press Pay now.");
    await progress.screenshot({ path: `../test-results/${info.project.name}-fix-instructions.png` });
    expect(await portal.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  } finally { await customer.close(); }
});

test("retest blocks incomplete instructions and preserves edited details through a stale progress reload", async ({ page, request }, info) => {
  const project = await (await request.post(`${api}/projects`, { data: { name: `Fix details ${info.project.name}` } })).json();
  expect((await request.post(`${api}/projects/${project.id}/members/employee`, { data: { email: "workflow-employee@example.com" } })).ok()).toBe(true);
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find((value: { name: string }) => value.name === "Workflow Employee");
  const row = await (await request.post(`${api}/feedback`, { data: { project_id: project.id, text: "Checkout needs testing." } })).json();
  expect((await request.patch(`${api}/feedback/${row.id}/workflow`, { data: { version: 0, status: "in_progress", assigned_employee_id: employee.id } })).ok()).toBe(true);
  await page.goto(`/workspace?report=${row.id}`);
  const panel = page.getByRole("region", { name: "Assignment and progress", exact: true });
  await panel.getByLabel("Issue status", { exact: true }).selectOption("ready_to_retest");
  const save = panel.getByRole("button", { name: "Save progress", exact: true });
  await expect(save).toBeDisabled();
  await panel.getByLabel("What changed", { exact: true }).fill("Checkout handler corrected.");
  await panel.getByLabel("Where the fix is available", { exact: true }).fill("Staging build 43.");
  await expect(save).toBeDisabled();
  await panel.getByLabel("Steps to retest", { exact: true }).fill("Open checkout.\nPress Pay now.");
  await expect(save).toBeEnabled();
  const state = await (await request.get(`${api}/feedback/${row.id}/workflow`)).json();
  expect((await request.patch(`${api}/feedback/${row.id}/triage`, { data: { version: state.version, priority: "high", due_date: null } })).ok()).toBe(true);
  await save.click();
  await expect(panel.getByRole("alert")).toContainText("changed in another tab");
  await panel.getByRole("button", { name: "Reload progress", exact: true }).click();
  await panel.getByLabel("Issue status", { exact: true }).selectOption("ready_to_retest");
  await expect(panel.getByLabel("Where the fix is available", { exact: true })).toHaveValue("Staging build 43.");
  await save.click();
  await expect(panel.getByRole("status")).toContainText("Progress saved");
  await page.reload();
  await expect(panel.getByLabel("Steps to retest", { exact: true })).toHaveValue("Open checkout.\nPress Pay now.");
});
