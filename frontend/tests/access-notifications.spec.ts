import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:15173";

test("owner scopes projects; employee and customer receive private, unread report alerts", async ({
  page,
  request,
  browser,
}, info) => {
  const alpha = await (
    await request.post("/api/projects", {
      data: { name: `Members only ${info.project.name}` },
    })
  ).json();
  const beta = await (
    await request.post("/api/projects", {
      data: { name: `Other project ${info.project.name}` },
    })
  ).json();
  const forbidden = await (
    await request.post("/api/feedback", {
      data: { project_id: beta.id, text: "This belongs to another project." },
    })
  ).json();
  const link = await (
    await request.post(`/api/projects/${alpha.id}/intake-link`, { data: {} })
  ).json();
  await page.goto("/workspace/team");
  const access = page.getByRole("region", {
    name: "Project access",
    exact: true,
  });
  await access
    .getByLabel("Manage project", { exact: true })
    .selectOption(alpha.id);
  await access
    .getByLabel("Customer submissions", { exact: true })
    .selectOption("members");
  await expect(access).toContainText("Guest access is blocked");
  await access
    .getByLabel("Member email", { exact: true })
    .fill("workflow-employee@example.com");
  await access
    .getByRole("button", { name: "Add to project", exact: true })
    .click();
  await expect(
    access
      .locator(".team-member")
      .filter({ hasText: "workflow-employee@example.com" }),
  ).toBeVisible();
  await access
    .getByLabel("Account type", { exact: true })
    .selectOption("customer");
  await access
    .getByLabel("Member email", { exact: true })
    .fill("workflow-customer@example.com");
  await access
    .getByRole("button", { name: "Add to project", exact: true })
    .click();
  await expect(
    access
      .locator(".team-member")
      .filter({ hasText: "workflow-customer@example.com" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../test-results/${info.project.name}-project-access.png`,
    fullPage: true,
  });
  const customer = await browser.newContext({ extraHTTPHeaders: {} });
  const employee = await browser.newContext({ extraHTTPHeaders: {} });
  await customer.addCookies([
    {
      name: "bugbrief_customer",
      value: Buffer.from("c".repeat(32)).toString("base64url"),
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);
  await employee.addCookies([
    {
      name: "bugbrief_employee",
      value: Buffer.from("e".repeat(32)).toString("base64url"),
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);
  await employee.request.post(
    base + "/api/auth/notifications/company/read-all",
  );
  await customer.request.post(
    base + "/api/auth/notifications/customer/read-all",
  );
  await customer.request.patch(
    base + "/api/auth/notifications/customer/preferences",
    { data: { email_enabled: false } },
  );
  expect(
    (
      await employee.request.get(base + `/api/feedback/${forbidden.id}`)
    ).status(),
  ).toBe(404);
  const guest = await browser.newContext({ extraHTTPHeaders: {} });
  expect(
    (
      await guest.request.get(base + `/api/public/intake/${link.token}`)
    ).status(),
  ).toBe(401);
  await guest.close();
  // Keep an older read report alert in the same project to exercise mixed inbox history.
  const previous = await (
    await customer.request.post(
      base + `/api/public/intake/${link.token}/submissions`,
      {
        data: {
          client_nonce: crypto.randomUUID(),
          text: "Previous issue for notification history.",
        },
      },
    )
  ).json();
  expect(
    (
      await customer.request.post(
        base + `/api/public/submissions/${previous.access_token}/submit`,
        { data: {} },
      )
    ).ok(),
  ).toBe(true);
  expect(
    (
      await employee.request.post(
        base + "/api/auth/notifications/company/read-all",
      )
    ).ok(),
  ).toBe(true);
  const portal = await customer.newPage();
  await portal.goto(base + `/c/${link.token}`);
  await portal
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("Checkout stops after pressing Pay now.");
  await portal.getByRole("button", { name: "Continue", exact: true }).click();
  await portal
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    portal.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const receipt = portal.url();
  const company = await employee.newPage();
  await company.goto(base + "/workspace");
  const visible = await (
    await employee.request.get(base + "/api/projects")
  ).json();
  expect(visible.some((item: { id: string }) => item.id === alpha.id)).toBe(
    true,
  );
  expect(visible.some((item: { id: string }) => item.id === beta.id)).toBe(
    false,
  );
  await company
    .getByRole("button", { name: /Notifications, 1 unread/ })
    .click();
  const inbox = company.getByRole("region", {
    name: "Notification inbox",
    exact: true,
  });
  await expect(inbox).toContainText("New customer report");
  await inbox
    .locator(".notification-item.unread")
    .filter({ hasText: "New customer report" })
    .click();
  await expect(company).toHaveURL(/report=/);
  await expect(
    company.getByRole("region", { name: "Report conversation", exact: true }),
  ).toBeVisible();
  const recordId = new URL(company.url()).searchParams.get("report")!;
  await portal.goto(base + "/customer");
  await portal.getByRole("button", { name: /^Notifications/ }).click();
  const customerInbox = portal.getByRole("region", {
    name: "Notification inbox",
    exact: true,
  });
  await customerInbox.getByLabel("Email alerts", { exact: true }).check();
  await expect(
    customerInbox.getByLabel("Email alerts", { exact: true }),
  ).toBeChecked();
  await customerInbox
    .getByRole("button", { name: "Close notifications", exact: true })
    .click();
  expect(
    (
      await employee.request.post(base + `/api/feedback/${recordId}/messages`, {
        data: { body: "Private investigation detail", visibility: "internal" },
      })
    ).ok(),
  ).toBe(true);
  expect(
    (
      await customer.request.get(base + "/api/auth/notifications/customer")
    ).ok(),
  ).toBe(true);
  expect(
    (
      await (
        await customer.request.get(base + "/api/auth/notifications/customer")
      ).json()
    ).unread_count,
  ).toBe(0);
  expect(
    (
      await employee.request.post(base + `/api/feedback/${recordId}/messages`, {
        data: { body: "We are checking checkout." },
      })
    ).ok(),
  ).toBe(true);
  await portal.evaluate(() => window.dispatchEvent(new Event("focus")));
  await portal.getByRole("button", { name: /Notifications, 1 unread/ }).click();
  await expect(customerInbox).toContainText("Company replied");
  await expect(customerInbox).not.toContainText("Private investigation detail");
  await portal.screenshot({
    path: `../test-results/${info.project.name}-notification-inbox.png`,
    fullPage: false,
  });
  expect(
    await portal.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await customerInbox.getByRole("link", { name: /Company replied/ }).click();
  await expect(portal).toHaveURL(receipt);
  await expect(
    portal.getByRole("region", { name: "Report conversation", exact: true }),
  ).toContainText("We are checking checkout.");
  const outbox = await (await request.get("/api/team/outbox")).json();
  expect(
    outbox.some(
      (item: { recipient: string; subject: string; delivery: string }) =>
        item.recipient === "workflow-customer@example.com" &&
        item.subject.includes(recordId.slice(0, 8).toUpperCase()) &&
        item.delivery === "local",
    ),
  ).toBe(true);
  const employees = await (await request.get("/api/employees")).json();
  const assignee = employees.find(
    (item: { name: string }) => item.name === "Workflow Employee",
  );
  let progress = await (
    await employee.request.patch(base + `/api/feedback/${recordId}/workflow`, {
      data: {
        version: 0,
        status: "in_progress",
        assigned_employee_id: assignee.id,
        note: "Investigating.",
      },
    })
  ).json();
  progress = await (
    await employee.request.patch(base + `/api/feedback/${recordId}/workflow`, {
      data: {
        version: progress.version,
        status: "ready_to_retest",
        assigned_employee_id: assignee.id,
        note: "Please try the fix.",
      },
    })
  ).json();
  expect(progress.status).toBe("ready_to_retest");
  await portal.reload();
  await portal.getByRole("button", { name: "It works", exact: true }).click();
  await expect(
    portal.getByRole("heading", { name: "Resolved", exact: true }),
  ).toBeVisible();
  await company.goto(base + "/workspace");
  await company.getByRole("button", { name: /^Notifications/ }).click();
  await expect(
    company.getByRole("region", { name: "Notification inbox", exact: true }),
  ).toContainText("Customer confirmed the fix");
  page.once("dialog", (dialog) => dialog.accept());
  await access
    .locator(".team-member")
    .filter({ hasText: "workflow-employee@example.com" })
    .getByRole("button", { name: "Remove from project", exact: true })
    .click();
  await expect(
    access
      .locator(".team-member")
      .filter({ hasText: "workflow-employee@example.com" }),
  ).toHaveCount(0);
  expect(
    (await employee.request.get(base + `/api/feedback/${recordId}`)).status(),
  ).toBe(404);
  expect(
    (
      await (
        await employee.request.get(base + "/api/auth/notifications/company")
      ).json()
    ).unread_count,
  ).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  const member = access
    .locator(".team-member")
    .filter({ hasText: "workflow-customer@example.com" });
  await member
    .getByRole("button", { name: "Remove from project", exact: true })
    .click();
  await expect(member).toContainText("Access removed");
  expect(
    (
      await customer.request.get(
        base +
          `/api/public/submissions/${new URL(receipt).pathname.split("/")[2]}`,
      )
    ).status(),
  ).toBe(403);
  await customer.request.patch(
    base + "/api/auth/notifications/customer/preferences",
    { data: { email_enabled: false } },
  );
  await customer.close();
  await employee.close();
});
