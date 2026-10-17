import { test, expect } from "@playwright/test";

test("review, redact, save, preserve on missing key, reload and delete screenshot", async ({
  page,
  request,
}, info) => {
  const p = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `Screenshot project ${info.project.name}` },
    })
  ).json();
  await page.goto("/workspace");
  await page.locator(".agency-capture > summary").click();
  await page.locator("#project").selectOption(p.id);
  const source = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 600;
    canvas.height = 300;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, 600, 300);
    ctx.fillStyle = "#e57c5a";
    ctx.fillRect(0, 0, 100, 40);
    ctx.fillStyle = "#244b3d";
    ctx.font = "24px sans-serif";
    ctx.fillText("Checkout", 180, 120);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("Choose screenshot").setInputFiles({
    name: "checkout.png",
    mimeType: "image/png",
    buffer: Buffer.from(source, "base64"),
  });
  await expect(
    page.getByRole("button", { name: "Save reviewed screenshot", exact: true }),
  ).toBeDisabled();
  await page
    .getByText("Redact with keyboard coordinates", { exact: true })
    .click();
  await page.getByRole("button", { name: "Add opaque rectangle" }).click();
  await expect(page.getByText("1 redaction · 600 × 300")).toBeVisible();
  await page.getByLabel("I reviewed this version").check();
  await page.screenshot({
    path: `../test-results/${info.project.name}-redaction.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Save reviewed screenshot", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "Reviewed screenshot: checkout.png" }),
  ).toBeVisible();
  const data = await (
    await request.get("http://127.0.0.1:18000/api/feedback")
  ).json();
  const item = data.find(
    (entry: { project_id: string }) => entry.project_id === p.id,
  );
  expect(item.text).toBe("");
  expect(item.attachments).toHaveLength(1);
  expect(item.attachments[0].analysis).toBeNull();
  const pixel = await page.evaluate(async (path) => {
    const response = await fetch(path);
    const bitmap = await createImageBitmap(await response.blob());
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(bitmap, 0, 0);
    return Array.from(ctx.getImageData(10, 10, 1, 1).data);
  }, `/api/feedback/${item.id}/attachments/${item.attachments[0].id}/content`);
  expect(pixel).toEqual([17, 17, 17, 255]);
  await expect(
    page.getByRole("button", { name: "Analyze reviewed screenshot" }),
  ).toBeDisabled();
  await page
    .getByLabel("I agree to send the saved, reviewed screenshot")
    .check();
  await page
    .getByRole("button", { name: "Analyze reviewed screenshot" })
    .click();
  await expect(page.getByRole("alert")).toContainText("GEMINI_API_KEY");
  await expect(
    page.getByRole("img", { name: "Reviewed screenshot: checkout.png" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("img", { name: "Reviewed screenshot: checkout.png" }),
  ).toBeVisible();
  await page.screenshot({
    path: `../test-results/${info.project.name}-screenshot-saved.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Delete screenshot checkout.png" })
    .click();
  await expect(
    page.getByRole("img", { name: "Reviewed screenshot: checkout.png" }),
  ).toHaveCount(0);
  expect(
    (
      await request.get(
        `http://127.0.0.1:18000/api/feedback/${item.id}/attachments/${item.attachments[0].id}/content`,
      )
    ).status(),
  ).toBe(404);
});

test("answer suggested questions, keep corrections and preserve unsaved manual report edits", async ({
  page,
  request,
}, info) => {
  const p = await (
    await request.post("http://127.0.0.1:18000/api/projects", {
      data: { name: `Clarification project ${info.project.name}` },
    })
  ).json();
  const item = await (
    await request.post("http://127.0.0.1:18000/api/feedback", {
      data: { project_id: p.id, text: "I clicked Pay now. Nothing happened." },
    })
  ).json();
  const report = {
    title: `Clarification fixture ${info.project.name}`,
    description: "Manual fixture for clarification UI testing.",
    expected_behaviour: null,
    actual_behaviour: null,
    reproduction_steps: [],
    observations: [],
    hypotheses: [],
    unknowns: ["Browser unknown."],
    questions: ["Which browser and device?"],
    category: "Functionality",
    priority: "Medium",
  };
  await request.put(`http://127.0.0.1:18000/api/feedback/${item.id}/report`, {
    data: { version: item.version, report },
  });
  await page.goto("/workspace");
  await page.getByLabel("Filter by project", { exact: true }).selectOption(p.id);
  await page.getByRole("button", { name: new RegExp(report.title) }).click();
  const drawer = page.getByRole("dialog", { name: "Review bug report" });
  const manualTitle = `Keep these manual edits ${info.project.name}`;
  await drawer.getByLabel("Title", { exact: true }).fill(manualTitle);
  await drawer
    .getByRole("button", { name: "Evidence & answers", exact: true })
    .click();
  await drawer
    .getByRole("button", { name: /Which browser and device/ })
    .click();
  await drawer
    .getByLabel("Your clarification", { exact: true })
    .fill("Android pe Chrome use kiya.");
  await drawer
    .getByRole("button", { name: "Save answer", exact: true })
    .click();
  await expect(drawer.locator(".answer-history")).toHaveCount(1);
  await drawer
    .getByRole("button", { name: "Add a correction", exact: true })
    .click();
  await drawer
    .getByLabel("Your clarification", { exact: true })
    .fill("Correction: Safari on iPhone.");
  await drawer
    .getByRole("button", { name: "Save answer", exact: true })
    .click();
  await expect(drawer.locator(".answer-history")).toHaveCount(2);
  await drawer.getByRole("button", { name: "Bug report", exact: true }).click();
  await expect(drawer.getByLabel("Title", { exact: true })).toHaveValue(
    manualTitle,
  );
  await drawer
    .getByRole("button", { name: "Evidence & answers", exact: true })
    .click();
  await drawer
    .getByLabel("I agree to send saved feedback, clarification answers")
    .check();
  await drawer
    .getByRole("button", { name: "Generate revised proposal" })
    .click();
  await expect(drawer.getByRole("alert")).toContainText("GEMINI_API_KEY");
  await page.screenshot({
    path: `../test-results/${info.project.name}-clarifications.png`,
    fullPage: false,
  });
  await page.reload();
  await page.getByLabel("Filter by project", { exact: true }).selectOption(p.id);
  await page.getByRole("button", { name: new RegExp(manualTitle) }).click();
  await page
    .getByRole("dialog", { name: "Review bug report" })
    .getByRole("button", { name: "Evidence & answers", exact: true })
    .click();
  await expect(page.locator(".report-drawer .answer-history")).toHaveCount(2);
  const saved = await (
    await request.get(`http://127.0.0.1:18000/api/feedback/${item.id}`)
  ).json();
  expect(saved.report.title).toBe(manualTitle);
  expect(
    saved.clarifications.map((entry: { answer: string }) => entry.answer),
  ).toEqual(["Android pe Chrome use kiya.", "Correction: Safari on iPhone."]);
});
