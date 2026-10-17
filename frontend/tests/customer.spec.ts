import { test, expect } from "@playwright/test";

test("anonymous customer submits through embedded button; agency receives captured context", async ({
  browser,
  page,
  request,
}, info) => {
  const project = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: {
        name: `Embedded customer ${info.project.name}`,
        url: "https://example.com",
      },
    })
  ).json();
  const link = await (
    await request.post(
      `http://127.0.0.1:18000/api/projects/${project.id}/intake-link`,
      { data: {} },
    )
  ).json();
  const customer = await browser.newContext({
    extraHTTPHeaders: {},
    viewport:
      info.project.name === "mobile"
        ? { width: 390, height: 844 }
        : { width: 1280, height: 800 },
  });
  const anonymous = await customer.newPage();
  const failures: string[] = [];
  anonymous.on("pageerror", (error) => failures.push(error.message));
  await anonymous.goto(`http://127.0.0.1:15173/demo/${link.token}`);
  await anonymous
    .getByRole("button", { name: "Report a problem", exact: true })
    .click();
  const form = anonymous.frameLocator('iframe[title="Report a problem"]');
  await expect(
    form.getByRole("heading", { name: "Something not quite right?" }),
  ).toBeVisible();
  await expect(
    form.getByLabel("Where did it happen?", { exact: true }),
  ).toHaveValue(new RegExp(`/demo/${link.token}$`));
  await form
    .getByLabel("What went wrong?", { exact: true })
    .fill(
      "I clicked Pay now but nothing happened. I expected the payment form.",
    );
  await form.getByLabel("Your name").fill("Test customer");
  await form.getByLabel("This is the browser I used").check();
  // A fake parent context for another origin must not replace the real captured URL.
  await anonymous.evaluate(() => {
    const host = document.getElementById("bugbrief-launcher")!;
    const frame = host.shadowRoot!.querySelector("iframe")!;
    frame.contentWindow!.postMessage(
      {
        type: "bugbrief:context",
        pageUrl: "https://unrelated.example/private",
        viewportWidth: 999,
        viewportHeight: 999,
      },
      location.origin,
    );
  });
  await expect(
    form.getByLabel("Where did it happen?", { exact: true }),
  ).toHaveValue(new RegExp(`/demo/${link.token}$`));
  await form.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    form.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  const before = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  expect(
    before.filter(
      (item: { project_id: string }) => item.project_id === project.id,
    ),
  ).toHaveLength(0);
  await form
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    form.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const resume = await form
    .getByLabel("Keep your private return link")
    .inputValue();
  const unauthorized = await customer.request.get(
    "http://127.0.0.1:18000/api/feedback",
  );
  expect(unauthorized.status()).toBe(401);
  await anonymous.screenshot({
    path: `../test-results/${info.project.name}-customer-receipt.png`,
    fullPage: false,
  });
  await page.goto("/workspace");
  await page
    .getByLabel("Filter by project", { exact: true })
    .selectOption(project.id);
  const row = page
    .locator(".feedback-row")
    .filter({ hasText: "I clicked Pay now but nothing happened." });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Customer");
  await row.click();
  await expect(
    page.getByRole("heading", { name: "Collected directly from the customer" }),
  ).toBeVisible();
  const context = page.locator(".agency-customer-context");
  await expect(context).toContainText("Test customer");
  await expect(context).toContainText("Demo preview");
  await expect(context).toContainText("Customer confirmed");
  const received = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  const item = received.find(
    (entry: { project_id: string }) => entry.project_id === project.id,
  );
  expect(item.customer.context.viewport_width).toBe(
    info.project.name === "mobile" ? 390 : 1280,
  );
  expect(item.customer.context.source).toBe("demo");
  expect(item.browser).toContain("Customer-confirmed");
  await anonymous.goto(resume);
  await expect(
    anonymous.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  expect(failures).toEqual([]);
  await customer.close();
});

test("standalone customer keeps reviewed screenshot when automatic check is unavailable", async ({
  browser,
  request,
}, info) => {
  const project = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `Public screenshot ${info.project.name}` },
    })
  ).json();
  const link = await (
    await request.post(
      `http://127.0.0.1:18000/api/projects/${project.id}/intake-link`,
      { data: {} },
    )
  ).json();
  const context = await browser.newContext({
    extraHTTPHeaders: {},
    viewport: { width: 390, height: 844 },
  });
  const customer = await context.newPage();
  await customer.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await customer
    .getByLabel("What went wrong?", { exact: true })
    .fill("Checkout pe click kiya but kuch nahi hua.");
  const source = await customer.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 300;
    canvas.height = 140;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, 300, 140);
    ctx.fillStyle = "#d87955";
    ctx.fillRect(0, 0, 100, 40);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await customer.getByLabel("Choose screenshot").setInputFiles({
    name: "review.png",
    mimeType: "image/png",
    buffer: Buffer.from(source, "base64"),
  });
  await customer
    .getByText("Redact with keyboard coordinates", { exact: true })
    .click();
  await customer.getByRole("button", { name: "Add opaque rectangle" }).click();
  await customer.getByLabel("I reviewed this version").check();
  await customer
    .getByRole("button", { name: "Save reviewed screenshot", exact: true })
    .click();
  await expect(
    customer.getByRole("img", { name: "Reviewed screenshot: review.png" }),
  ).toBeVisible();
  await customer.getByLabel("I agree to this external processing").check();
  await customer
    .getByRole("button", { name: "Continue with a quick check" })
    .click();
  await expect(
    customer.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  await expect(customer.getByRole("status")).toContainText(
    "Your work is saved",
  );
  await customer.screenshot({
    path: `../test-results/${info.project.name}-customer-review.png`,
    fullPage: true,
  });
  await customer.reload();
  await expect(
    customer.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  await customer
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    customer.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const response = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  const item = response.find(
    (entry: { project_id: string }) => entry.project_id === project.id,
  );
  expect(item.attachments).toHaveLength(1);
  expect(item.report).toBeNull();
  expect(item.text).toBe("Checkout pe click kiya but kuch nahi hua.");
  const file = await request.get(
    `http://127.0.0.1:18000/api/feedback/${item.id}/attachments/${item.attachments[0].id}/content`,
  );
  expect(file.ok()).toBe(true);
  expect(
    await customer.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.close();
});

test("agency code protects workspace and project links can be revoked", async ({
  browser,
  request,
  page,
}, info) => {
  const context = await browser.newContext({
    extraHTTPHeaders: {},
    viewport: { width: 390, height: 844 },
  });
  const login = await context.newPage();
  await login.goto("http://127.0.0.1:15173/workspace");
  await expect(
    login.getByRole("heading", { name: "Your workspace. Your clients." }),
  ).toBeVisible();
  await login.getByText("Workspace owner access", { exact: true }).click();
  await login
    .getByLabel("Workspace access code")
    .fill("e2e-agency-access-code");
  await login.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    login.getByRole("heading", {
      name: "A little feedback. A lot of clarity.",
    }),
  ).toBeVisible();
  const p = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `Share controls ${info.project.name}` },
    })
  ).json();
  await page.goto("/workspace");
  await page
    .getByRole("button", { name: "Collect customer feedback", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Collect customer feedback",
  });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project", { exact: true }).selectOption(p.id);
  await expect(dialog.getByLabel("Customer feedback link")).toHaveValue(
    /\/c\//,
  );
  const url = await dialog.getByLabel("Customer feedback link").inputValue();
  await dialog
    .getByLabel("Website URL for embedded capture")
    .fill("https://customer.example");
  await dialog.getByRole("button", { name: "Save website URL" }).click();
  await expect(
    dialog.getByRole("button", { name: "Website URL saved" }),
  ).toBeVisible();
  await expect(dialog.getByLabel("Embed code")).toHaveValue(/widget\.js/);
  await page.screenshot({
    path: `../test-results/${info.project.name}-share-controls.png`,
    fullPage: false,
  });
  await dialog.getByText("Close this project link", { exact: true }).click();
  await dialog.getByRole("button", { name: "Revoke current link" }).click();
  const visitor = await context.newPage();
  await visitor.goto(url);
  await expect(
    visitor.getByRole("heading", {
      name: "This feedback link is unavailable.",
    }),
  ).toBeVisible();
  const projects = await (
    await request.get("http://127.0.0.1:18000/api/projects")
  ).json();
  expect(projects.find((entry: { id: string }) => entry.id === p.id).url).toBe(
    "https://customer.example",
  );
  await context.close();
});

test("widget captures a separate website origin and excludes URL secrets", async ({
  browser,
  request,
}, info) => {
  const origin = "http://127.0.0.1:14174";
  const project = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `External widget ${info.project.name}`, url: origin },
    })
  ).json();
  const link = await (
    await request.post(
      `http://127.0.0.1:18000/api/projects/${project.id}/intake-link`,
      { data: {} },
    )
  ).json();
  const context = await browser.newContext({
    extraHTTPHeaders: {},
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto(
    origin + "/index.html?private_parameter=not-for-capture#private-fragment",
  );
  await page.evaluate((token) => {
    const script = document.createElement("script");
    script.src = "http://127.0.0.1:15173/widget.js";
    script.dataset.project = token;
    document.body.appendChild(script);
  }, link.token);
  const pageViewportWidth = await page.evaluate(() => innerWidth);
  await expect(page.locator("#bugbrief-launcher")).toBeVisible();
  await page
    .getByRole("button", { name: "Report a problem", exact: true })
    .click();
  const form = page.frameLocator('iframe[title="Report a problem"]');
  await expect(
    form.getByLabel("Where did it happen?", { exact: true }),
  ).toHaveValue(origin + "/index.html");
  await expect(
    form.getByRole("link", { name: "Sign in", exact: true }),
  ).toHaveAttribute("target", "_blank");
  await form
    .getByLabel("What went wrong?", { exact: true })
    .fill("Pay now is unresponsive on this test page.");
  await form.getByRole("button", { name: "Continue", exact: true }).click();
  await form
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    form.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const inbox = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  const item = inbox.find(
    (entry: { project_id: string }) => entry.project_id === project.id,
  );
  expect(item.page_url).toBe(origin + "/index.html");
  expect(item.customer.context.source).toBe("embedded");
  expect(item.customer.context.viewport_width).toBe(pageViewportWidth);
  expect(item.browser).toBe("");
  await page.screenshot({
    path: `../test-results/${info.project.name}-cross-origin-widget.png`,
    fullPage: false,
  });
  await context.close();
});

test("retry after a lost save response preserves latest edits without duplicates", async ({
  browser,
  request,
}, info) => {
  const project = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: {
        name: `Interrupted save ${info.project.name}`,
        url: "https://example.com",
      },
    })
  ).json();
  const link = await (
    await request.post(
      `http://127.0.0.1:18000/api/projects/${project.id}/intake-link`,
      { data: {} },
    )
  ).json();
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await page
    .getByLabel("What went wrong?", { exact: true })
    .fill("The checkout button failed.");
  await page.route(
    "**/api/public/intake/*/submissions",
    async (route) => {
      await route.fetch(); // Persist on the real backend, then lose the response.
      await route.abort("failed");
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const updated = "The checkout button failed twice after entering my address.";
  await page.getByRole("textbox", { name: /What went wrong/ }).fill(updated);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ready for the team?" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Send to the agency", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "The team has your feedback." }),
  ).toBeVisible();
  const records = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  const received = records.filter(
    (item: { project_id: string }) => item.project_id === project.id,
  );
  expect(received).toHaveLength(1);
  expect(received[0].text).toBe(updated);
  await context.close();
});
