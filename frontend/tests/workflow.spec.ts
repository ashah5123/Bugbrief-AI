import { test, expect } from "@playwright/test";

test("real API: project, draft, reload, missing key and responsive navigation", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/workspace");
  await expect(
    page.getByRole("heading", { name: "A little feedback. A lot of clarity." }),
  ).toBeVisible();
  await page.screenshot({
    path: `../test-results/${testInfo.project.name}-initial.png`,
    fullPage: true,
  });
  const initialCount = await page.locator(".feedback-row").count();
  const initialTotal = (await (await page.request.get("/api/feedback")).json())
    .length;
  await page.locator(".agency-capture > summary").click();
  await page
    .locator("main")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Give your project a home.",
  });
  await expect(dialog).toBeVisible();
  await dialog
    .getByLabel("Project name")
    .fill(`Browser test ${testInfo.project.name}`);
  await dialog.getByLabel("Project URL").fill("https://example.com");
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  const text = "Checkout pe Pay now click kiya, but kuch nahi hua.";
  await page.getByLabel("Client feedback").fill(text);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Feedback saved");
  await page.reload();
  await expect(page.getByLabel("Client feedback")).toHaveValue(text);
  await expect(page.locator(".feedback-row")).toHaveCount(
    Math.min(initialCount + 1, 5),
  );
  await page.getByLabel("I’ve removed sensitive information").check();
  await page
    .getByRole("button", { name: "Generate report", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("GEMINI_API_KEY");
  await expect(page.getByLabel("Client feedback")).toHaveValue(text);
  // Reloading and re-saving must update the same draft, not create a duplicate.
  await page.reload();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Feedback saved");
  await expect(page.locator(".feedback-row")).toHaveCount(
    Math.min(initialCount + 1, 5),
  );
  expect((await (await page.request.get("/api/feedback")).json()).length).toBe(
    initialTotal + 1,
  );
  const noOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );
  expect(noOverflow).toBe(true);
  await page.screenshot({
    path: `../test-results/${testInfo.project.name}-overview.png`,
    fullPage: true,
  });
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A home for every project." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: `Browser test ${testInfo.project.name}`,
      exact: true,
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("manual report fixture: edit, save, reopen and retain source evidence", async ({
  page,
  request,
}, testInfo) => {
  // This is an explicitly manual report fixture; it does not simulate a successful AI response.
  const p = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `Manual report ${testInfo.project.name}` },
    })
  ).json();
  const feedback = await (
    await request.post("http://127.0.0.1:18000/api/feedback", {
      data: {
        project_id: p.id,
        text: "I clicked Pay now. Nothing happened. I expected the payment form.",
      },
    })
  ).json();
  const report = {
    title: `Manual checkout report ${testInfo.project.name}`,
    description: "Manually prepared report fixture for testing editing.",
    expected_behaviour: null,
    actual_behaviour: {
      text: "Nothing happened.",
      evidence_quote: "Nothing happened.",
      source: "feedback",
    },
    reproduction_steps: [],
    observations: [],
    hypotheses: [],
    unknowns: ["Browser not supplied."],
    questions: ["Which browser?"],
    category: "Functionality",
    priority: "Medium",
  };
  const result = await request.put(
    `http://127.0.0.1:18000/api/feedback/${feedback.id}/report`,
    { data: { version: feedback.version, report } },
  );
  expect(result.ok()).toBe(true);
  await page.goto("/workspace");
  await page.getByRole("button", { name: report.title }).click();
  const drawer = page.getByRole("dialog", { name: "Review bug report" });
  await expect(drawer).toBeVisible();
  const editedTitle = `Manually edited checkout ${testInfo.project.name}`;
  await drawer.getByLabel("Title", { exact: true }).fill(editedTitle);
  const expected = drawer
    .locator(".claim-editor")
    .filter({ hasText: "Expected behaviour" });
  await expected
    .getByRole("button", { name: "Add from submitted evidence" })
    .click();
  await expected
    .getByLabel("Expected behaviour")
    .fill("The payment form should open.");
  await expected.locator("summary").click();
  await expected
    .getByLabel("Exact source quotation")
    .fill("I expected the payment form.");
  await drawer
    .getByRole("button", { name: "Save report", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Report saved");
  await page.screenshot({
    path: `../test-results/${testInfo.project.name}-report.png`,
    fullPage: false,
  });
  await drawer.getByRole("button", { name: "Close report" }).click();
  await page.reload();
  await page.getByRole("button", { name: new RegExp(editedTitle) }).click();
  await expect(drawer.getByLabel("Title", { exact: true })).toHaveValue(
    editedTitle,
  );
  await expect(drawer.getByLabel("Expected behaviour")).toHaveValue(
    "The payment form should open.",
  );
  await drawer
    .getByRole("button", { name: "Original feedback", exact: true })
    .click();
  await expect(drawer.locator("blockquote")).toHaveText(feedback.text);
});
