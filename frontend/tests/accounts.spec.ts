import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
const base = "http://127.0.0.1:15173";
const api = "http://127.0.0.1:18000/api";
const password = "A memorable customer phrase 42!";
async function invitation(request: APIRequestContext, name: string) {
  const project = await (
    await request.post(`${api}/projects`, { data: { name } })
  ).json();
  return (
    await request.post(`${api}/projects/${project.id}/intake-link`, {
      data: {},
    })
  ).json();
}
async function signup(page: Page, email: string) {
  await page.getByLabel("Your name", { exact: true }).fill("Test customer");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create customer account", exact: true })
    .click();
}
async function signin(page: Page, email: string) {
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("new customer signs up; returning customer finds and deletes report from a fresh browser", async ({
  browser,
  request,
}, info) => {
  const email = `customer-${crypto.randomUUID()}@example.com`;
  const link = await invitation(
    request,
    `Account project ${info.project.name}`,
  );
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto(base + "/customer");
  await page.screenshot({
    path: `../test-results/${info.project.name}-customer-entry.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: /I’m a new customer/ }).click();
  await signup(page, email);
  await expect(
    page.getByRole("heading", { name: "Hello, Test customer." }),
  ).toBeVisible();
  await page
    .getByLabel("Project invitation", { exact: true })
    .fill("https://external.example/c/private");
  await page
    .getByRole("button", { name: "Connect project", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "from this BugBrief site",
  );
  await page
    .getByLabel("Project invitation", { exact: true })
    .fill(`${base}/c/${link.token}`);
  await page
    .getByRole("button", { name: "Connect project", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Report a problem", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("The account checkout button did not respond.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const reportUrl = page.url();
  await page
    .getByRole("link", { name: /View all your reports in your account/ })
    .click();
  await expect(page.locator(".customer-report-list article")).toHaveCount(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /I’m a returning customer/ }),
  ).toBeVisible();
  await context.close();
  const returning = await browser.newContext({ extraHTTPHeaders: {} });
  const returned = await returning.newPage();
  await returned.goto(base + "/customer");
  await returned
    .getByRole("link", { name: /I’m a returning customer/ })
    .click();
  await returned.getByLabel("Email address", { exact: true }).fill(email);
  await returned
    .getByLabel("Password", { exact: true })
    .fill("An incorrect password.");
  await returned.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(returned.getByRole("alert")).toContainText(
    "Email or password is incorrect",
  );
  await signin(returned, email);
  await expect(returned.locator(".customer-report-list article")).toHaveCount(
    1,
  );
  await returned.screenshot({
    path: `../test-results/${info.project.name}-customer-account.png`,
    fullPage: true,
  });
  await returned.locator(".customer-report-list article > a").click();
  await expect(
    returned.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  expect(returned.url()).toBe(reportUrl);
  const outsider = await browser.newContext({ extraHTTPHeaders: {} });
  expect(
    (await outsider.request.get(base + "/api/customer/reports")).status(),
  ).toBe(401);
  const signedOutPage = await outsider.newPage();
  await signedOutPage.goto(reportUrl);
  await expect(
    signedOutPage.getByRole("heading", {
      name: "Sign in to view your report.",
    }),
  ).toBeVisible();
  await expect(
    signedOutPage.getByRole("link", { name: "Customer sign in", exact: true }),
  ).toBeVisible();
  const token = new URL(reportUrl).pathname.split("/").pop();
  expect(
    (await outsider.request.get(`${api}/public/submissions/${token}`)).status(),
  ).toBe(404);
  await returned
    .getByRole("button", { name: "Delete my report", exact: true })
    .click();
  await returned
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    returned.getByRole("heading", { name: "Your report has been deleted." }),
  ).toBeVisible();
  await returned
    .getByRole("link", { name: "Back to your reports", exact: true })
    .click();
  await expect(
    returned.getByRole("heading", { name: "Your reports will appear here." }),
  ).toBeVisible();
  expect(
    await returned.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await outsider.close();
  await returning.close();
});

test("existing guest report can be saved to a new account and reopened after sign-in", async ({
  browser,
  request,
}, info) => {
  const link = await invitation(request, `Claimed guest ${info.project.name}`);
  const email = `guest-${crypto.randomUUID()}@example.com`;
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto(`${base}/c/${link.token}`);
  await page
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("This guest report should not be lost.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Create an account", exact: true })
    .click();
  await expect(
    page.getByText("This report will be added to your account."),
  ).toBeVisible();
  await signup(page, email);
  await expect(
    page.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  await expect(page.locator(".customer-main")).toContainText(
    "This guest report should not be lost.",
  );
  await page.goto(base + "/customer");
  await expect(page.locator(".customer-report-list article")).toHaveCount(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("link", { name: /I’m a returning customer/ }).click();
  await signin(page, email);
  await expect(page.locator(".customer-report-list article")).toHaveCount(1);
  await context.close();
});
