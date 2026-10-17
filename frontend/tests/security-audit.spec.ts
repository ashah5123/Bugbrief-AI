import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:15173";
const sessionCookie = (name: string, byte: string) => ({
  name,
  value: Buffer.from(byte.repeat(32)).toString("base64url"),
  domain: "127.0.0.1",
  path: "/",
  httpOnly: true,
  sameSite: "Strict" as const,
});

test("switching employees clears another account's local draft and sign-out removes it", async ({
  browser,
}, info) => {
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  await context.addCookies([sessionCookie("bugbrief_employee", "e")]);
  const first = await (
    await context.request.post(base + "/api/projects", {
      data: { name: `First employee ${info.project.name}` },
    })
  ).json();
  const page = await context.newPage();
  await page.goto(base + "/workspace");
  await page.getByRole("button", { name: "New feedback", exact: true }).click();
  await page.getByLabel("Project *", { exact: true }).selectOption(first.id);
  const field = page.getByLabel("Client feedback or add a screenshot", {
    exact: true,
  });
  await field.fill("Private unsaved text from the first employee.");
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("bugbrief-draft")))
    .toContain("Private unsaved text");
  await page.reload();
  await expect(field).toHaveValue(
    "Private unsaved text from the first employee.",
  );
  await context.addCookies([
    sessionCookie(
      "bugbrief_employee",
      info.project.name === "mobile" ? "b" : "a",
    ),
  ]);
  const second = await (
    await context.request.post(base + "/api/projects", {
      data: { name: `Other employee ${info.project.name}` },
    })
  ).json();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".top-avatar")).toHaveAttribute(
    "title",
    "Audit Employee",
  );
  await page.getByRole("button", { name: "New feedback", exact: true }).click();
  await expect(field).toHaveValue("");
  await page.getByLabel("Project *", { exact: true }).selectOption(second.id);
  await expect(page.getByLabel("Project *", { exact: true })).toHaveValue(
    second.id,
  );
  expect(
    (
      await context.request.get(base + `/api/projects/${first.id}/intake-link`)
    ).status(),
  ).toBe(404);
  await field.fill("Second employee's own draft.");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /I’m an existing employee/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("bugbrief-draft")),
  ).toBeNull();
  expect((await context.request.get(base + "/api/projects")).status()).toBe(
    401,
  );
  await context.close();
});

test("customer account changes cannot recover another customer's unsubmitted browser text", async ({
  browser,
  request,
}, info) => {
  const project = await (
    await request.post("/api/projects", {
      data: { name: `Customer privacy ${info.project.name}` },
    })
  ).json();
  const link = await (
    await request.post(`/api/projects/${project.id}/intake-link`, { data: {} })
  ).json();
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  await context.addCookies([sessionCookie("bugbrief_customer", "c")]);
  const page = await context.newPage();
  await page.goto(base + `/c/${link.token}`);
  const text = page.getByRole("textbox", { name: /What went wrong/ });
  await text.fill("Unsubmitted personal details for customer one.");
  await expect
    .poll(() =>
      page.evaluate(() =>
        Object.keys(localStorage)
          .map((key) => localStorage.getItem(key))
          .join(" "),
      ),
    )
    .toContain("Unsubmitted personal details");
  await context.addCookies([sessionCookie("bugbrief_customer", "d")]);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(text).toHaveValue("");
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage)
        .map((key) => localStorage.getItem(key))
        .join(" "),
    ),
  ).not.toContain("Unsubmitted personal details");
  await context.close();
});

test("a customer can submit when the browser blocks local storage", async ({
  browser,
  request,
}, info) => {
  const project = await (
    await request.post("/api/projects", {
      data: { name: `Storage blocked ${info.project.name}` },
    })
  ).json();
  const link = await (
    await request.post(`/api/projects/${project.id}/intake-link`, { data: {} })
  ).json();
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  await context.addInitScript(() => {
    for (const method of ["getItem", "setItem", "removeItem"]) {
      Object.defineProperty(Storage.prototype, method, {
        configurable: true,
        value() {
          throw new DOMException("Storage unavailable", "SecurityError");
        },
      });
    }
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base + `/c/${link.token}`);
  await page
    .getByRole("textbox", { name: /What went wrong/ })
    .fill("Submit this even when browser storage is blocked.");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});
