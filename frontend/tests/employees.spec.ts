import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:15173";
const password = "A personal employee phrase 42!";

test("new employee joins with invitation; existing employee signs in from another browser", async ({
  browser,
  request,
}, info) => {
  const email = `employee-${crypto.randomUUID()}@example.com`;
  const name = `Alex ${info.project.name}`;
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto(base + "/");
  await page.getByRole("link", { name: /I’m with the company/ }).click();
  await expect(
    page.getByRole("link", { name: /I’m a new employee/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /I’m an existing employee/ }),
  ).toBeVisible();
  await page.screenshot({
    path: `../test-results/${info.project.name}-employee-entry.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: /I’m a new employee/ }).click();
  await page.getByLabel("Your name", { exact: true }).fill(name);
  await page.getByLabel("Work email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("A different password.");
  await page
    .getByLabel("Workspace invitation code", { exact: true })
    .fill("wrong-code");
  await page
    .getByRole("button", { name: "Create employee account", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Your passwords don’t match",
  );
  await page.getByLabel("Confirm password", { exact: true }).fill(password);
  // Exercise the server-side invalid invitation once; all browser cases share a local IP limiter.
  if (info.project.name === "desktop") {
    await page
      .getByRole("button", { name: "Create employee account", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "invitation code is incorrect",
    );
  }
  expect((await context.request.get(base + "/api/projects")).status()).toBe(
    401,
  );
  expect(
    (
      await request.post(base + "/api/team/invitations", { data: { email } })
    ).status(),
  ).toBe(201);
  const outbox = await (await request.get(base + "/api/team/outbox")).json();
  const invitation = outbox.find(
    (item: { recipient: string; body: string }) =>
      item.recipient === email && item.body.includes("/invite/"),
  );
  const token = invitation.body.match(/invite\/([A-Za-z0-9_-]{43})/)[1];
  await page
    .getByLabel("Workspace invitation code", { exact: true })
    .fill(token);
  await page
    .getByRole("button", { name: "Create employee account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your work, with a clear next step." }),
  ).toBeVisible();
  await expect(page.locator(".top-avatar")).toHaveAttribute("title", name);
  await page.goto(base + "/");
  await page.getByRole("link", { name: /I’m with the company/ }).click();
  await expect(
    page.getByRole("link", { name: /I’m a new employee/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: `Continue as ${name}`, exact: true })
    .click();
  await expect(page.locator(".top-avatar")).toHaveAttribute("title", name);
  expect(
    await (await context.request.get(base + "/api/customer/session")).json(),
  ).toEqual({ authenticated: false });
  const project = await (
    await context.request.post(base + "/api/projects", {
      data: { name: `Employee shared project ${info.project.name}` },
    })
  ).json();
  const feedback = await (
    await context.request.post(base + "/api/feedback", {
      data: {
        project_id: project.id,
        text: "An issue for the employee team to review.",
      },
    })
  ).json();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /I’m an existing employee/ }),
  ).toBeVisible();
  expect((await context.request.get(base + "/api/projects")).status()).toBe(
    401,
  );
  await context.close();

  const returning = await browser.newContext({ extraHTTPHeaders: {} });
  const returned = await returning.newPage();
  await returned.goto(base + "/workspace");
  await returned
    .getByRole("link", { name: /I’m an existing employee/ })
    .click();
  await expect(
    returned.getByLabel("Workspace invitation code", { exact: true }),
  ).toHaveCount(0);
  await returned.getByLabel("Work email", { exact: true }).fill(email);
  await returned
    .getByLabel("Password", { exact: true })
    .fill("An incorrect password.");
  await returned
    .getByRole("button", { name: "Sign in to workspace", exact: true })
    .click();
  await expect(returned.getByRole("alert")).toContainText(
    "Email or password is incorrect",
  );
  await returned.getByLabel("Password", { exact: true }).fill(password);
  await returned
    .getByRole("button", { name: "Sign in to workspace", exact: true })
    .click();
  await expect(
    returned.getByRole("heading", {
      name: "Your work, with a clear next step.",
    }),
  ).toBeVisible();
  await expect(returned.locator(".top-avatar")).toHaveAttribute("title", name);
  await returned.getByRole("button", { name: "Open project inbox", exact: true }).click();
  await returned
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  await returned
    .locator(".feedback-row")
    .filter({ hasText: "An issue for the employee team" })
    .click();
  await expect(returned.getByRole("button", { name: "Delete report", exact: true })).toBeDisabled();
  const employeeId = (await (await returning.request.get(base + "/api/auth/session")).json()).employee.id;
  expect((await request.patch(`${base}/api/projects/${project.id}/members/employee/${employeeId}`, { data: { role: "manager", can_delete: true } })).ok()).toBe(true);
  await returned.evaluate(() => window.dispatchEvent(new Event("focus")));
  await returned
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await returned
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    returned
      .locator(".feedback-row")
      .filter({ hasText: "An issue for the employee team" }),
  ).toHaveCount(0);
  expect(
    (
      await returning.request.get(`${base}/api/feedback/${feedback.id}`)
    ).status(),
  ).toBe(404);
  if (info.project.name === "mobile")
    await returned.getByRole("button", { name: "Open navigation" }).click();
  await expect(returned.locator(".employee-identity")).toContainText(name);
  await expect(returned.locator(".employee-identity")).toContainText(email);
  await returned.locator(".employee-identity").scrollIntoViewIfNeeded();
  await expect(returned.locator(".employee-identity")).toBeVisible();
  await returned.screenshot({
    path: `../test-results/${info.project.name}-employee-workspace.png`,
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await returned.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await returning.close();
});
