import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:15173";
const api = "http://127.0.0.1:18000/api";

test("company assigns and progresses a customer issue; customer sees owner, status and history", async ({
  browser,
  page,
  request,
}, info) => {
  const project = await (
    await request.post(`${api}/projects`, {
      data: { name: `Progress ${info.project.name}` },
    })
  ).json();
  const link = await (
    await request.post(`${api}/projects/${project.id}/intake-link`, {
      data: {},
    })
  ).json();
  expect(
    (
      await request.post(`${api}/projects/${project.id}/members/employee`, {
        data: { email: "workflow-employee@example.com" },
      })
    ).ok(),
  ).toBe(true);
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find(
    (item: { name: string }) => item.name === "Workflow Employee",
  );
  const customer = await browser.newContext({ extraHTTPHeaders: {} });
  expect(
    (
      await customer.request.post(`${base}/api/customer/login`, {
        data: {
          email: "workflow-customer@example.com",
          password: "Workflow test phrase 42!",
        },
      })
    ).ok(),
  ).toBe(true);
  const portal = await customer.newPage();
  await portal.goto(`${base}/c/${link.token}`);
  const feedback = `Checkout does not respond in ${info.project.name}.`;
  await portal.getByRole("textbox", { name: /What went wrong/ }).fill(feedback);
  await portal.getByRole("button", { name: "Continue", exact: true }).click();
  await portal
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    portal.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const reportUrl = portal.url();
  const tracking = portal.getByRole("region", {
    name: "Report progress",
    exact: true,
  });
  await expect(
    tracking.getByRole("heading", { name: "New", exact: true }),
  ).toBeVisible();
  await page.goto("/workspace");
  await page
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  await page.locator(".feedback-row").filter({ hasText: feedback }).click();
  const panel = page.getByRole("region", {
    name: "Assignment and progress",
    exact: true,
  });
  await panel
    .getByLabel("Assigned employee", { exact: true })
    .selectOption(employee.id);
  await panel
    .getByLabel("Issue status", { exact: true })
    .selectOption("in_progress");
  await panel
    .getByLabel(/Customer-visible update/)
    .fill("We are investigating checkout.");
  await panel
    .getByRole("button", { name: "Save progress", exact: true })
    .click();
  await expect(panel.getByRole("status")).toContainText("Progress saved");
  await portal.reload();
  await expect(
    tracking.getByRole("heading", { name: "In progress", exact: true }),
  ).toBeVisible();
  await expect(tracking).toContainText("Assigned to Workflow Employee");
  await expect(tracking).toContainText("We are investigating checkout.");
  await portal
    .getByRole("link", { name: /View all your reports in your account/ })
    .click();
  const card = portal
    .locator(".customer-report-list article")
    .filter({ hasText: project.name });
  await expect(card).toContainText("In progress");
  await expect(card).toContainText("Assigned to Workflow Employee");
  const transitions = [
    [
      "needs_information",
      "Needs information",
      "Please tell us which browser showed the issue.",
    ],
    ["in_progress", "In progress", "Continuing our investigation."],
    [
      "ready_to_retest",
      "Ready to retest",
      "Checkout is ready for you to try again.",
    ],
    ["resolved", "Resolved", "The company has marked the issue resolved."],
  ];
  for (const [status, label, note] of transitions) {
    await panel
      .getByLabel("Issue status", { exact: true })
      .selectOption(status);
    await panel.getByLabel(/Customer-visible update/).fill(note);
    await panel
      .getByRole("button", { name: "Save progress", exact: true })
      .click();
    await expect(panel.locator(".workflow-badge").first()).toHaveText(label);
    await portal.goto(reportUrl);
    await expect(
      tracking.getByRole("heading", { name: label, exact: true }),
    ).toBeVisible();
    await expect(tracking).toContainText(note);
    await expect(tracking.locator("li").first()).toContainText(note);
  }
  await portal.screenshot({
    path: `../test-results/${info.project.name}-customer-progress.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByLabel("Filter by issue progress", { exact: true })
    .selectOption("resolved");
  await page
    .getByLabel("Filter by assigned employee", { exact: true })
    .selectOption(employee.id);
  await expect(
    page.locator(".feedback-row").filter({ hasText: feedback }),
  ).toBeVisible();
  await page
    .getByLabel("Filter by assigned employee", { exact: true })
    .selectOption("unassigned");
  await expect(page.locator(".feedback-row")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Clear filters", exact: true })
    .click();
  await expect(
    page.locator(".feedback-row").filter({ hasText: feedback }),
  ).toBeVisible();
  expect(
    await portal.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await customer.close();
});

test("progress updates preserve unsaved report edits and reject a stale save", async ({
  page,
  request,
}, info) => {
  const project = await (
    await request.post(`${api}/projects`, {
      data: { name: `Concurrent progress ${info.project.name}` },
    })
  ).json();
  const record = await (
    await request.post(`${api}/feedback`, {
      data: { project_id: project.id, text: "A manual checkout issue." },
    })
  ).json();
  expect(
    (
      await request.post(`${api}/projects/${project.id}/members/employee`, {
        data: { email: "workflow-employee@example.com" },
      })
    ).ok(),
  ).toBe(true);
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find(
    (item: { name: string }) => item.name === "Workflow Employee",
  );
  const report = {
    title: "A manual progress test report",
    description: "Explicitly manual test report.",
    expected_behaviour: null,
    actual_behaviour: null,
    reproduction_steps: [],
    observations: [],
    hypotheses: [],
    unknowns: [],
    questions: [],
    category: "Functionality",
    priority: "Medium",
  };
  expect(
    (
      await request.put(`${api}/feedback/${record.id}/report`, {
        data: { version: record.version, report },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/workspace");
  await page
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  await page.locator(".feedback-row").filter({ hasText: report.title }).click();
  const title = page.getByLabel("Title", { exact: true });
  await title.fill("My unsaved report edits must stay.");
  const panel = page.getByRole("region", {
    name: "Assignment and progress",
    exact: true,
  });
  await panel
    .getByLabel("Assigned employee", { exact: true })
    .selectOption(employee.id);
  await panel
    .getByLabel("Issue status", { exact: true })
    .selectOption("in_progress");
  await panel
    .getByRole("button", { name: "Save progress", exact: true })
    .click();
  await expect(panel.getByRole("status")).toContainText("Progress saved");
  await expect(title).toHaveValue("My unsaved report edits must stay.");
  const state = await (
    await request.get(`${api}/feedback/${record.id}/workflow`)
  ).json();
  expect(
    (
      await request.patch(`${api}/feedback/${record.id}/workflow`, {
        data: {
          version: state.version,
          status: "ready_to_retest",
          assigned_employee_id: employee.id,
          note: "Updated by another employee.",
        },
      })
    ).ok(),
  ).toBe(true);
  await panel
    .getByLabel("Issue status", { exact: true })
    .selectOption("needs_information");
  await panel
    .getByLabel(/Customer-visible update/)
    .fill("My unsent update should stay.");
  await panel
    .getByRole("button", { name: "Save progress", exact: true })
    .click();
  await expect(panel.getByRole("alert")).toContainText(
    "changed in another tab",
  );
  await expect(title).toHaveValue("My unsaved report edits must stay.");
  await panel
    .getByRole("button", { name: "Reload progress", exact: true })
    .click();
  await expect(panel.getByLabel("Issue status", { exact: true })).toHaveValue(
    "ready_to_retest",
  );
  await expect(panel.getByLabel(/Customer-visible update/)).toHaveValue(
    "My unsent update should stay.",
  );
  await expect(title).toHaveValue("My unsaved report edits must stay.");
  await panel
    .getByRole("heading", { name: "Assignment & progress", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `../test-results/${info.project.name}-company-progress.png`,
    fullPage: false,
    animations: "disabled",
  });
});
