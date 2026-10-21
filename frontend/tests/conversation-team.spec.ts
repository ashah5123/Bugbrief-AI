import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:15173";

test("customer replies, private notes and fix confirmation stay with the report", async ({
  page,
  request,
  browser,
}, info) => {
  const project = await (
    await request.post("/api/projects", {
      data: { name: `Conversation ${info.project.name}` },
    })
  ).json();
  const link = await (
    await request.post(`/api/projects/${project.id}/intake-link`, { data: {} })
  ).json();
  const customer = await browser.newContext({ extraHTTPHeaders: {} });
  const record = await (
    await customer.request.post(
      `${base}/api/public/intake/${link.token}/submissions`,
      {
        data: {
          client_nonce: crypto.randomUUID(),
          text: "Checkout fails when I press Pay now.",
        },
      },
    )
  ).json();
  expect(
    (
      await customer.request.post(
        `${base}/api/public/submissions/${record.access_token}/submit`,
        { data: { draft_version: record.draft_version } },
      )
    ).ok(),
  ).toBe(true);
  const feedback = (
    await (await request.get(`/api/feedback?project_id=${project.id}`)).json()
  ).find((item: { project_id: string }) => item.project_id === project.id);
  expect(
    (
      await request.post(`/api/projects/${project.id}/members/employee`, {
        data: { email: "workflow-employee@example.com" },
      })
    ).ok(),
  ).toBe(true);
  const employees = await (await request.get("/api/employees")).json();
  const assigned = employees.find(
    (item: { name: string }) => item.name === "Workflow Employee",
  );
  await page.goto("/workspace");
  await page
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  await page
    .locator(".feedback-row")
    .filter({ hasText: "Checkout fails when I press Pay now." })
    .click();
  const company = page.getByRole("region", {
    name: "Report conversation",
    exact: true,
  });
  await company
    .getByLabel("Message visibility", { exact: true })
    .selectOption("internal");
  await company
    .getByLabel("Private team note", { exact: true })
    .fill("Keep this private: checking the billing logs.");
  await company
    .getByRole("button", { name: "Save private note", exact: true })
    .click();
  await expect(company).toContainText("Private · team only");
  await company
    .getByLabel("Message visibility", { exact: true })
    .selectOption("public");
  await company
    .getByLabel("Your reply", { exact: true })
    .fill("Which browser did you use?");
  await company
    .getByRole("button", { name: "Send reply", exact: true })
    .click();
  await expect(company).toContainText("Which browser did you use?");
  const portal = await customer.newPage();
  await portal.goto(`${base}/s/${record.access_token}`);
  const thread = portal.getByRole("region", {
    name: "Report conversation",
    exact: true,
  });
  await expect(thread).toContainText("Which browser did you use?");
  await expect(
    portal.getByText("Keep this private: checking the billing logs."),
  ).toHaveCount(0);
  await thread
    .getByLabel("Your reply", { exact: true })
    .fill("Safari on my phone.");
  await thread.getByRole("button", { name: "Send reply", exact: true }).click();
  await expect(thread).toContainText("Safari on my phone.");
  let progress = await (
    await request.patch(`/api/feedback/${feedback.id}/workflow`, {
      data: {
        version: 0,
        status: "in_progress",
        assigned_employee_id: assigned.id,
        note: "Working on this.",
      },
    })
  ).json();
  progress = await (
    await request.patch(`/api/feedback/${feedback.id}/workflow`, {
      data: {
        version: progress.version,
        status: "ready_to_retest", fix_details: { summary: "Checkout corrected.", location: "Test website, current version.", steps: "Open checkout and press Pay now." },
        assigned_employee_id: assigned.id,
        note: "Please try checkout again.",
      },
    })
  ).json();
  await portal.reload();
  await portal
    .getByLabel("Retest details", { exact: true })
    .fill("Still stuck after pressing Pay now.");
  await portal
    .getByRole("button", { name: "Still happening", exact: true })
    .click();
  await expect(
    portal.getByRole("heading", { name: "In progress", exact: true }),
  ).toBeVisible();
  progress = await (
    await request.get(`/api/feedback/${feedback.id}/workflow`)
  ).json();
  await request.patch(`/api/feedback/${feedback.id}/workflow`, {
    data: {
      version: progress.version,
      status: "ready_to_retest", fix_details: { summary: "Checkout corrected.", location: "Test website, current version.", steps: "Open checkout and press Pay now." },
      assigned_employee_id: assigned.id,
      note: "Second fix ready.",
    },
  });
  await portal.reload();
  await portal.getByRole("button", { name: "It works", exact: true }).click();
  await expect(
    portal.getByRole("heading", { name: "Resolved", exact: true }),
  ).toBeVisible();
  await expect(portal.locator("body")).toContainText(
    "Customer confirmed the fix",
  );
  await portal.screenshot({
    path: `../test-results/${info.project.name}-customer-conversation.png`,
    fullPage: true,
  });
  expect(
    await portal.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await customer.close();
});

test("owner invites an employee using test outbox, verifies email and removes access", async ({
  page,
  browser,
}, info) => {
  const email = `team-${crypto.randomUUID()}@example.com`;
  await page.goto("/workspace/team");
  await page.getByLabel("Employee email", { exact: true }).fill(email);
  await page
    .getByRole("button", { name: "Create invitation", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Invitation prepared");
  const invitationMail = page
    .locator(".outbox-message")
    .filter({ hasText: email })
    .filter({ hasText: "employee invitation" });
  await invitationMail.locator("summary").click();
  const inviteUrl = await invitationMail
    .getByRole("link", { name: /Open account link/ })
    .getAttribute("href");
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const employee = await context.newPage();
  await employee.goto(inviteUrl!);
  await employee
    .getByLabel("Your name", { exact: true })
    .fill("Invited Teammate");
  await employee.getByLabel("Work email", { exact: true }).fill(email);
  await employee
    .getByLabel("Password", { exact: true })
    .fill("An invited employee phrase!");
  await employee
    .getByLabel("Confirm password", { exact: true })
    .fill("An invited employee phrase!");
  await employee
    .getByRole("button", { name: "Create employee account", exact: true })
    .click();
  await expect(
    employee.getByRole("heading", {
      name: "Your work, with a clear next step.",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Refresh outbox", exact: true })
    .click();
  const verification = page
    .locator(".outbox-message")
    .filter({ hasText: email })
    .filter({ hasText: "Verify your BugBrief email" });
  await verification.locator("summary").click();
  await employee.goto(
    (await verification
      .getByRole("link", { name: /Open account link/ })
      .getAttribute("href"))!,
  );
  await employee
    .getByRole("button", { name: "Verify email", exact: true })
    .click();
  await expect(employee.getByRole("status")).toContainText("Email verified");
  await employee.goto(base + "/workspace/team");
  await expect(employee).toHaveURL(/workspace\/team/);
  await expect(
    employee.getByText("✓ Email verified", { exact: true }),
  ).toBeVisible();
  await expect(
    employee.getByRole("heading", {
      name: "Team access is managed by your workspace owner",
    }),
  ).toBeVisible();
  await employee.goto(base + "/account?role=employee");
  await employee.getByLabel("Account email", { exact: true }).fill(email);
  await employee
    .getByRole("button", { name: "Send reset link", exact: true })
    .click();
  await expect(employee.getByRole("status")).toContainText(
    "If the account is eligible",
  );
  await page
    .getByRole("button", { name: "Refresh outbox", exact: true })
    .click();
  const reset = page
    .locator(".outbox-message")
    .filter({ hasText: email })
    .filter({ hasText: "Reset your BugBrief password" });
  await reset.locator("summary").click();
  await employee.goto(
    (await reset
      .getByRole("link", { name: /Open account link/ })
      .getAttribute("href"))!,
  );
  await employee
    .getByLabel("New password", { exact: true })
    .fill("My changed employee phrase!");
  await employee
    .getByLabel("Confirm password", { exact: true })
    .fill("My changed employee phrase!");
  await employee
    .getByRole("button", { name: "Update password", exact: true })
    .click();
  await expect(employee.getByRole("status")).toContainText("Password updated");
  expect((await context.request.get(base + "/api/projects")).status()).toBe(
    401,
  );
  await employee
    .getByRole("link", { name: "Return to sign in", exact: true })
    .click();
  await employee.getByLabel("Work email", { exact: true }).fill(email);
  await employee
    .getByLabel("Password", { exact: true })
    .fill("My changed employee phrase!");
  await employee
    .getByRole("button", { name: "Sign in to workspace", exact: true })
    .click();
  await expect(
    employee.getByRole("heading", {
      name: "Your work, with a clear next step.",
    }),
  ).toBeVisible();
  await page.reload();
  const member = page.locator(".team-member").filter({ hasText: email });
  await expect(member).toContainText("email verified");
  page.once("dialog", (dialog) => dialog.accept());
  await member
    .getByRole("button", { name: "Remove access", exact: true })
    .click();
  await expect(member).toContainText("Access removed");
  expect((await context.request.get(base + "/api/projects")).status()).toBe(
    401,
  );
  await page.screenshot({
    path: `../test-results/${info.project.name}-team-management.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});
