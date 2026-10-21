import { test, expect, type APIRequestContext } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";
const base = "http://127.0.0.1:15173";
async function post(request: APIRequestContext, path: string, data: unknown) {
  const response = await request.post(`${api}${path}`, { data });
  expect(response.ok(), `${path}: ${response.status()}`).toBe(true);
  return response.json();
}

test("one shared fix, separate customer conversations and independent retest results", async ({ browser, page, request }, info) => {
  const project = await post(request, "/projects", { name: `Duplicate checkout ${info.project.name}` });
  const link = await post(request, `/projects/${project.id}/intake-link`, {});
  await post(request, `/projects/${project.id}/members/employee`, { email: "workflow-employee@example.com" });
  const employees = await (await request.get(`${api}/employees`)).json();
  const employee = employees.find((row: { name: string }) => row.name === "Workflow Employee");
  const contexts = await Promise.all([browser.newContext({ extraHTTPHeaders: {} }), browser.newContext({ extraHTTPHeaders: {} })]);
  try {
    const records: { id: string; token: string }[] = [];
    for (let index = 0; index < 2; index++) {
      const record = await post(contexts[index].request, `/public/intake/${link.token}/submissions`, {
        text: `Checkout duplicate ${index} ${info.project.name}`, reporter_name: `Private customer ${index}`,
        client_nonce: `duplicates-${info.project.name}-${index}-nonce-123456789`,
      });
      await post(contexts[index].request, `/public/submissions/${record.access_token}/submit`, { draft_version: record.draft_version });
      const items = await (await request.get(`${api}/feedback`)).json();
      const row = items.find((value: { text: string; project_id: string }) => value.project_id === project.id && value.text === `Checkout duplicate ${index} ${info.project.name}`);
      records.push({ id: row.id, token: record.access_token });
    }
    const [main, child] = records;
    await post(request, `/feedback/${main.id}/messages`, { visibility: "internal", body: "Private team investigation on main report" });
    await post(contexts[0].request, `/public/submissions/${main.token}/messages`, { body: "Customer zero confidential details" });
    await page.goto(`/workspace?report=${child.id}`);
    const panel = page.getByRole("region", { name: "Linked reports", exact: true });
    await panel.getByLabel("Find the main report", { exact: true }).fill(main.id);
    await panel.getByLabel("Main report", { exact: true }).selectOption(main.id);
    await panel.getByRole("button", { name: "Link as duplicate", exact: true }).click();
    await expect(panel).toContainText("2 linked reports");
    await expect(page.locator(`.feedback-row[data-report-id="${child.id}"] .duplicate-badge`)).toHaveText("Linked duplicate");
    await panel.getByRole("link", { name: new RegExp(`the main report:`) }).click();
    await expect(panel.getByRole("heading", { name: "Manage the shared fix", exact: true })).toBeVisible();
    await panel.getByLabel("Shared fix owner", { exact: true }).selectOption(employee.id);
    await panel.getByLabel("Shared customer update", { exact: true }).fill("We are investigating the checkout bug.");
    await panel.getByRole("button", { name: "Start shared work", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("Updated 2 open reports");
    await panel.getByLabel("Shared customer update", { exact: true }).fill("Checkout is fixed. Repeat your original payment steps, then confirm the result.");
    await panel.getByLabel("Shared: What changed", { exact: true }).fill("Checkout handler corrected.");
    await panel.getByLabel("Shared: Where the fix is available", { exact: true }).fill("Current test website.");
    await panel.getByLabel("Shared: Steps to retest", { exact: true }).fill("Open checkout and press Pay now.");
    await panel.getByRole("button", { name: "Request shared retest", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("Customers can now test independently");
    const portals = await Promise.all(contexts.map(context => context.newPage()));
    for (let index = 0; index < 2; index++) {
      await portals[index].goto(`${base}/s/${records[index].token}`);
      await expect(portals[index].getByRole("button", { name: "It works", exact: true })).toBeVisible();
    }
    await expect(portals[1].locator(".report-message")).not.toContainText(["Customer zero confidential details", "Private team investigation"]);
    await expect(portals[1].locator("body")).not.toContainText("Private customer 0");
    await portals[0].getByRole("button", { name: "It works", exact: true }).click();
    await expect(portals[0].getByRole("region", { name: "Report progress", exact: true }).getByRole("heading", { name: "Resolved", exact: true })).toBeVisible();
    await portals[1].getByLabel("Retest details", { exact: true }).fill("Checkout still does not respond on my phone.");
    await portals[1].getByRole("button", { name: "Still happening", exact: true }).click();
    await page.reload();
    await expect(panel).toContainText("1 resolved · 1 still open");
    await panel.getByLabel("Shared customer update", { exact: true }).fill("We corrected the remaining mobile issue. Please retry checkout.");
    await panel.getByLabel("Shared: What changed", { exact: true }).fill("Checkout handler corrected.");
    await panel.getByLabel("Shared: Where the fix is available", { exact: true }).fill("Current test website.");
    await panel.getByLabel("Shared: Steps to retest", { exact: true }).fill("Open checkout and press Pay now.");
    await panel.getByRole("button", { name: "Request shared retest", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("Updated 1 open reports");
    await portals[0].reload();
    await expect(portals[0].getByRole("button", { name: "It works", exact: true })).toHaveCount(0);
    await portals[1].reload();
    await portals[1].getByRole("button", { name: "It works", exact: true }).click();
    await page.reload();
    await expect(panel).toContainText("All reports resolved");
    await panel.getByLabel("Update for all linked reports", { exact: true }).fill("Thanks for testing. The checkout fix is complete.");
    let loseResponse = true;
    await page.route("**/duplicates/updates", async route => {
      if (loseResponse) { loseResponse = false; await route.fetch(); await route.abort("failed"); }
      else await route.continue();
    });
    await panel.getByRole("button", { name: "Send update to 2 reports", exact: true }).click();
    await expect(panel.getByRole("alert")).toContainText("Cannot reach");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await panel.getByRole("button", { name: "Send update to 2 reports", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("Update posted separately to 2 reports");
    for (const portal of portals) {
      await portal.reload();
      await expect(portal.locator(".report-message").filter({ hasText: "Thanks for testing. The checkout fix is complete." })).toHaveCount(1);
      await expect(portal.locator(".report-message")).not.toContainText(["Private team investigation"]);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await panel.screenshot({ path: `../test-results/${info.project.name}-linked-reports.png` });
    await page.goto(`/workspace?report=${child.id}`);
    await panel.getByRole("button", { name: "Unlink this report", exact: true }).click();
    await panel.getByRole("button", { name: "Keep linked", exact: true }).click();
    await expect(panel).toContainText("2 linked reports");
    await panel.getByRole("button", { name: "Unlink this report", exact: true }).click();
    await panel.getByRole("button", { name: "Confirm unlink", exact: true }).click();
    await expect(panel.getByRole("button", { name: "Link as duplicate", exact: true })).toBeVisible();
    expect((await (await request.get(`${api}/feedback/${main.id}/duplicates`)).json()).group).toBeNull();
    expect((await (await request.get(`${api}/feedback/${child.id}/workflow`)).json()).status).toBe("resolved");
  } finally { await Promise.all(contexts.map(context => context.close())); }
});

test("stale link selection reloads safely and unlinking the main report preserves every report", async ({ page, request }, info) => {
  const project = await post(request, "/projects", { name: `Stale duplicates ${info.project.name}` });
  const rows = [];
  for (const text of ["Main shared issue", "First duplicate", "Second duplicate"]) rows.push(await post(request, "/feedback", { project_id: project.id, text }));
  const [main, first, second] = rows;
  await page.goto(`/workspace?report=${second.id}`);
  const panel = page.getByRole("region", { name: "Linked reports", exact: true });
  await panel.getByLabel("Main report", { exact: true }).selectOption(main.id);
  await post(request, `/feedback/${first.id}/duplicates`, { main_feedback_id: main.id, version: 0 });
  await panel.getByRole("button", { name: "Link as duplicate", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("Linked reports changed");
  await panel.getByRole("button", { name: "Reload linked reports", exact: true }).click();
  await panel.getByLabel("Main report", { exact: true }).selectOption(main.id);
  await panel.getByRole("button", { name: "Link as duplicate", exact: true }).click();
  await expect(panel).toContainText("3 linked reports");
  await page.goto(`/workspace?report=${main.id}`);
  await panel.getByRole("button", { name: "Unlink all reports", exact: true }).click();
  await panel.getByRole("button", { name: "Confirm unlink", exact: true }).click();
  await expect(panel.getByRole("status")).toContainText("Reports unlinked");
  for (const row of rows) {
    const value = await (await request.get(`${api}/feedback/${row.id}`)).json();
    expect(value.text).toBe(row.text);
    expect(value.duplicate_group).toBeNull();
  }
});
