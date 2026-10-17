import { test, expect, type APIRequestContext } from "@playwright/test";

const api = "http://127.0.0.1:18000/api";
async function projectLink(request: APIRequestContext, name: string) {
  const project = await (
    await request.post(`${api}/projects`, { data: { name } })
  ).json();
  const link = await (
    await request.post(`${api}/projects/${project.id}/intake-link`, {
      data: {},
    })
  ).json();
  return { project, link };
}

test("welcome routes company through sign-in and customers through a scoped link", async ({
  browser,
  request,
}, info) => {
  await projectLink(request, `Role selection ${info.project.name}`);
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:15173/");
  await expect(
    page.getByRole("heading", { name: "Welcome. What brings you here?" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../test-results/${info.project.name}-welcome.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: /I’m with the company/ }).click();
  await expect(
    page.getByRole("link", { name: /I’m an existing employee/ }),
  ).toBeVisible();
  await page.getByText("Workspace owner access", { exact: true }).click();
  await expect(page.getByLabel("Workspace access code")).toBeVisible();
  expect((await context.request.get(`${api}/feedback`)).status()).toBe(401);
  await page.getByLabel("Workspace access code").fill("e2e-agency-access-code");
  await page
    .getByRole("button", { name: "Open workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A little feedback. A lot of clarity." }),
  ).toBeVisible();
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Switch role", exact: true }).click();
  await page.getByRole("link", { name: /I’m a customer/ }).click();
  await expect(
    page.getByRole("heading", { name: "Let’s get it to the right team." }),
  ).toBeVisible();
  await page.getByRole("link", { name: /I’m a new customer/ }).click();
  await expect(
    page.getByRole("heading", { name: "A place for your reports." }),
  ).toBeVisible();
  await expect(page.getByLabel("Your name", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your reports." }),
  ).toBeVisible();
  await expect(page.getByLabel("Email address", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});

test("customer manages and deletes only their saved report with confirmation", async ({
  browser,
  request,
}, info) => {
  const { project, link } = await projectLink(
    request,
    `My reports ${info.project.name}`,
  );
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await page
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("The checkout button did not respond.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const privateUrl = await page
    .getByLabel("Keep your private return link")
    .inputValue();
  const token = new URL(privateUrl).pathname.split("/").pop();
  const other = await (
    await request.post(`${api}/public/intake/${link.token}/submissions`, {
      data: {
        client_nonce: `another-customer-${crypto.randomUUID()}`,
        text: "Another customer issue.",
      },
    })
  ).json();
  const stranger = await browser.newContext({ extraHTTPHeaders: {} });
  const strangerPage = await stranger.newPage();
  await strangerPage.goto("http://127.0.0.1:15173/customer");
  await expect(
    strangerPage.getByRole("link", { name: /I’m a returning customer/ }),
  ).toBeVisible();
  await page.goto("http://127.0.0.1:15173/customer");
  await expect(page.locator(".customer-report-list article")).toHaveCount(1);
  await expect(page.locator(".customer-report-list")).toContainText(
    project.name,
  );
  await page.screenshot({
    path: `../test-results/${info.project.name}-my-reports.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Delete my report", exact: true })
    .click();
  await page.getByRole("button", { name: "Keep report", exact: true }).click();
  expect(
    (await context.request.get(`${api}/public/submissions/${token}`)).status(),
  ).toBe(200);
  await page
    .getByRole("button", { name: "Delete my report", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Delete your report?" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: /I’m a new customer/ }),
  ).toBeVisible();
  expect(
    (await context.request.get(`${api}/public/submissions/${token}`)).status(),
  ).toBe(404);
  expect(
    (
      await context.request.get(
        `${api}/public/submissions/${other.access_token}`,
      )
    ).status(),
  ).toBe(200);
  expect(
    (await context.request.delete(`${api}/feedback/anything`)).status(),
  ).toBe(401);
  await page.goto(privateUrl);
  await expect(
    page.getByRole("heading", { name: "This feedback link is unavailable." }),
  ).toBeVisible();
  // A fresh report after deletion gets a new identity and can also be deleted in-place.
  await page.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await page
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("A new, separate draft.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  const freshUrl = page.url();
  await page
    .getByRole("button", { name: "Delete my report", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your report has been deleted." }),
  ).toBeVisible();
  await page.goto(freshUrl);
  await expect(
    page.getByRole("heading", { name: "This feedback link is unavailable." }),
  ).toBeVisible();
  await stranger.close();
  await context.close();
});

test("company can delete a report and a draft while preserving another report", async ({
  page,
  request,
}, info) => {
  const { project } = await projectLink(
    request,
    `Company deletion ${info.project.name}`,
  );
  const first = await (
    await request.post(`${api}/feedback`, {
      data: {
        project_id: project.id,
        text: "Delete this company report.",
      },
    })
  ).json();
  const draft = await (
    await request.post(`${api}/feedback`, {
      data: {
        project_id: project.id,
        text: "Delete this saved draft.",
      },
    })
  ).json();
  const keep = await (
    await request.post(`${api}/feedback`, {
      data: {
        project_id: project.id,
        text: "Keep this unrelated report.",
      },
    })
  ).json();
  const report = {
    title: "Company report to delete",
    description: "Manually prepared deletion test report.",
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
      await request.put(`${api}/feedback/${first.id}/report`, {
        data: { version: first.version, report },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/workspace");
  await page
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  await page
    .locator(".feedback-row")
    .filter({ hasText: "Company report to delete" })
    .click();
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await page.getByRole("button", { name: "Keep report", exact: true }).click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Company report to delete",
  );
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    page
      .locator(".feedback-row")
      .filter({ hasText: "Company report to delete" }),
  ).toHaveCount(0);
  await page
    .locator(".feedback-row")
    .filter({ hasText: "Delete this saved draft." })
    .click();
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    page
      .locator(".feedback-row")
      .filter({ hasText: "Delete this saved draft." }),
  ).toHaveCount(0);
  expect((await request.get(`${api}/feedback/${first.id}`)).status()).toBe(404);
  expect((await request.get(`${api}/feedback/${draft.id}`)).status()).toBe(404);
  expect((await request.get(`${api}/feedback/${keep.id}`)).status()).toBe(200);
  await page.reload();
  // The last saved draft has been cleared instead of being restored after deletion.
  await page.getByRole("button", { name: "New feedback", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Client feedback" }),
  ).toHaveValue("");
});
