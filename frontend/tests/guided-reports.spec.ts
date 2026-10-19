import { test, expect } from "@playwright/test";

const contextLabel = "Include browser, language, timezone and screen dimensions";
const root = "http://127.0.0.1:18000/api";

test("guided answers recover across reload and lost save, then arrive with a screenshot in the workspace", async ({ browser, request, page }, info) => {
  const project = await (await request.post(`${root}/projects`, { data: { name: `Guided bug ${info.project.name}` } })).json();
  const link = await (await request.post(`${root}/projects/${project.id}/intake-link`, { data: {} })).json();
  const customerContext = await browser.newContext({
    extraHTTPHeaders: {}, viewport: info.project.name === "mobile" ? { width: 390, height: 844 } : { width: 1280, height: 900 },
  });
  const customer = await customerContext.newPage();
  await customer.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await expect(customer.getByLabel(contextLabel)).not.toBeChecked();
  await customer.getByLabel("What were you trying to do?", { exact: true }).fill("Complete my order");
  await customer.getByLabel("What went wrong?", { exact: true }).fill("Clicking Pay now did nothing.");
  await customer.getByLabel("What did you expect to happen?", { exact: true }).fill("Payment opens.");
  await customer.getByLabel("How often does it happen?", { exact: true }).selectOption("sometimes");
  await customer.getByText("Add the steps you took", { exact: false }).click();
  await customer.getByLabel("Steps you took", { exact: true }).fill("1. Open cart\n2. Click Pay now");
  await customer.reload();
  await expect(customer.getByLabel("Steps you took", { exact: true })).toHaveValue("1. Open cart\n2. Click Pay now");
  await expect(customer.getByLabel("How often does it happen?", { exact: true })).toHaveValue("sometimes");
  await customer.screenshot({ path: `../test-results/${info.project.name}-guided-form.png`, fullPage: true });
  await customer.route("**/api/public/intake/*/submissions", async (route) => {
    await route.fetch();
    await route.abort("failed");
  }, { times: 1 });
  await customer.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(customer.getByRole("alert")).toBeVisible();
  await customer.getByLabel("What did you expect to happen?", { exact: true }).fill("The payment form should open.");
  await customer.getByRole("button", { name: "Continue", exact: true }).click();
  const summary = customer.getByRole("region", { name: "Customer's bug details" });
  await expect(summary).toContainText("The payment form should open.");
  await expect(summary).toContainText("Sometimes");
  await customer.getByRole("button", { name: "Edit your feedback" }).click();
  const bytes = await customer.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 120; canvas.height = 80;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "white"; ctx.fillRect(0, 0, 120, 80);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await customer.getByLabel("Choose screenshot", { exact: true }).setInputFiles({ name: "checkout.png", mimeType: "image/png", buffer: Buffer.from(bytes, "base64") });
  await customer.getByLabel("I reviewed this version").check();
  await customer.getByRole("button", { name: "Save reviewed screenshot", exact: true }).click();
  await expect(customer.getByRole("img", { name: "Reviewed screenshot: checkout.png" })).toBeVisible();
  // Read directly from the saved server draft in a fresh browser tab, without local draft state.
  const resume = customer.url();
  const fresh = await browser.newContext({ extraHTTPHeaders: {}, viewport: { width: 390, height: 844 } });
  const restored = await fresh.newPage();
  await restored.goto(resume);
  await expect(restored.getByLabel("What were you trying to do?", { exact: true })).toHaveValue("Complete my order");
  await expect(restored.getByLabel("What did you expect to happen?", { exact: true })).toHaveValue("The payment form should open.");
  await expect(restored.getByLabel(contextLabel)).not.toBeChecked();
  await fresh.close();
  await customer.getByRole("button", { name: "Continue", exact: true }).click();
  await customer.getByRole("button", { name: "Send to the agency", exact: true }).click();
  await expect(customer.getByRole("heading", { name: "The team has your feedback." })).toBeVisible();
  const reports = (await (await request.get(`${root}/feedback`)).json()).filter((item: { project_id: string }) => item.project_id === project.id);
  expect(reports).toHaveLength(1);
  expect(reports[0].customer.guided_details).toEqual({ goal: "Complete my order", expected: "The payment form should open.", steps: "1. Open cart\n2. Click Pay now", frequency: "sometimes" });
  expect(reports[0].customer.context.user_agent).toBe("");
  expect(reports[0].attachments).toHaveLength(1);
  await page.goto("/workspace");
  await page.getByLabel("Filter by project", { exact: true }).selectOption(project.id);
  await page.locator(".feedback-row").filter({ hasText: "Clicking Pay now did nothing." }).click();
  await expect(page.getByRole("region", { name: "Customer's bug details" })).toContainText("The payment form should open.");
  await expect(page.getByRole("region", { name: "Customer's bug details" })).toContainText("1. Open cart");
  await page.getByRole("region", { name: "Customer's bug details" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `../test-results/${info.project.name}-guided-workspace.png`, fullPage: false });
  for (const target of [page, customer]) expect(await target.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await customerContext.close();
});

test("browser details require opt-in and turning them off clears the saved context", async ({ browser, request }, info) => {
  const project = await (await request.post(`${root}/projects`, { data: { name: `Guided privacy ${info.project.name}` } })).json();
  const link = await (await request.post(`${root}/projects/${project.id}/intake-link`, { data: {} })).json();
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  const customer = await context.newPage();
  await customer.goto(`http://127.0.0.1:15173/c/${link.token}`);
  await customer.getByLabel("What went wrong?", { exact: true }).fill("The page freezes.");
  await customer.getByLabel(contextLabel).check();
  await customer.getByLabel("This is the browser I used").check();
  await customer.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(customer.locator(".customer-review-details")).toContainText("Included · customer confirmed");
  const path = new URL(customer.url()).pathname.replace("/s/", "/public/submissions/");
  expect((await (await context.request.get(root + path)).json()).context.user_agent).not.toBe("");
  await customer.getByRole("button", { name: "Edit your feedback" }).click();
  await customer.getByLabel(contextLabel).uncheck();
  await customer.reload();
  await expect(customer.getByLabel(contextLabel)).not.toBeChecked();
  await customer.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(customer.locator(".customer-review-details")).toContainText("Not included");
  const saved = await (await context.request.get(root + path)).json();
  expect(saved.context.user_agent).toBe("");
  expect(saved.context.same_browser_confirmed).toBe(false);
  expect(saved.context.viewport_width).toBe(0);
  expect(saved.guided_details.expected).toBe("");
  expect(saved.guided_details.frequency).toBe("");
  await customer.getByRole("button", { name: "Send to the agency", exact: true }).click();
  await expect(customer.getByRole("heading", { name: "The team has your feedback." })).toBeVisible();
  await context.close();
});
