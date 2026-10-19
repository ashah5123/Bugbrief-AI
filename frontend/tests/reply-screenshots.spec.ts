import { test, expect } from "@playwright/test";
const api = "http://127.0.0.1:18000/api";
const base = "http://127.0.0.1:15173";

test("reviewed reply screenshots survive retry and keep private team images out of customer access", async ({ page, browser, request }, info) => {
  const project = await (await request.post(`${api}/projects`, { data: { name: `Reply images ${info.project.name}` } })).json();
  const link = await (await request.post(`${api}/projects/${project.id}/intake-link`, { data: {} })).json();
  const context = await browser.newContext({ extraHTTPHeaders: {} });
  try {
    const record = await (await context.request.post(`${api}/public/intake/${link.token}/submissions`, { data: {
      client_nonce: `reply-images-${info.project.name}-nonce-123456789`, text: "Checkout still does not respond.",
    } })).json();
    expect((await context.request.post(`${api}/public/submissions/${record.access_token}/submit`, { data: { draft_version: record.draft_version } })).ok()).toBe(true);
    const items = await (await request.get(`${api}/feedback`)).json();
    const feedback = items.find((row: { project_id: string }) => row.project_id === project.id);
    const portal = await context.newPage();
    await portal.goto(`${base}/s/${record.access_token}`);
    const conversation = portal.getByRole("region", { name: "Report conversation", exact: true });
    await conversation.getByLabel("Your reply", { exact: true }).fill("Here is the button that still fails.");
    await conversation.getByRole("button", { name: "Add screenshots to reply", exact: true }).click();
    const source = await portal.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.width=600; canvas.height=300;
      const ctx=canvas.getContext("2d")!; ctx.fillStyle="white"; ctx.fillRect(0,0,600,300);
      ctx.fillStyle="red"; ctx.fillRect(0,0,100,40); ctx.fillStyle="black"; ctx.font="24px sans-serif"; ctx.fillText("Checkout",180,120);
      return canvas.toDataURL("image/png").split(",")[1];
    });
    await conversation.getByLabel("Choose reply screenshot", { exact: true }).setInputFiles({ name:"checkout.png", mimeType:"image/png", buffer:Buffer.from(source,"base64") });
    await expect(conversation.getByRole("button", { name: "Attach reviewed screenshot", exact: true })).toBeDisabled();
    await expect(conversation.getByRole("button", { name: "Send reply", exact: true })).toBeDisabled();
    await conversation.getByText("Redact with keyboard coordinates", { exact: true }).click();
    await conversation.getByRole("button", { name: "Add opaque rectangle", exact: true }).click();
    expect((await (await context.request.get(`${api}/public/submissions/${record.access_token}/messages`)).json()).length).toBe(0);
    await conversation.getByLabel("I reviewed this version").check();
    await conversation.getByRole("button", { name: "Attach reviewed screenshot", exact: true }).click();
    await conversation.getByLabel("Screenshot caption 1", { exact: true }).fill("The checkout button stays on this screen.");
    await expect(conversation.getByRole("img", { name: "Reviewed reply screenshot 1", exact: true })).toBeVisible();
    expect((await (await context.request.get(`${api}/public/submissions/${record.access_token}/messages`)).json()).length).toBe(0);
    let loseResponse = true;
    await portal.route(`**/api/public/submissions/${record.access_token}/messages`, async route => {
      if (loseResponse && route.request().method()==="POST") { loseResponse=false; await route.fetch(); await route.abort("failed"); }
      else await route.continue();
    });
    await conversation.getByRole("button", { name: "Send reply", exact: true }).click();
    await expect(conversation.getByRole("alert")).toContainText("Cannot reach");
    await portal.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(conversation.getByLabel("Your reply", { exact: true })).toHaveValue("Here is the button that still fails.");
    await expect(conversation.getByRole("img", { name: "Reviewed reply screenshot 1", exact: true })).toBeVisible();
    await conversation.getByRole("button", { name: "Send reply", exact: true }).click();
    await expect(conversation.locator(".report-message")).toHaveCount(1);
    await expect(conversation.locator(".reply-images figcaption")).toContainText("The checkout button stays on this screen.");
    await expect(conversation.locator(".pending-reply-image")).toHaveCount(0);
    const message = (await (await context.request.get(`${api}/public/submissions/${record.access_token}/messages`)).json())[0];
    const customerImage = `/api/public/submissions/${record.access_token}/messages/${message.id}/attachments/${message.attachments[0].id}/content`;
    const pixel = await portal.evaluate(async path => {
      const response=await fetch(path); const bitmap=await createImageBitmap(await response.blob());
      const canvas=document.createElement("canvas");canvas.width=bitmap.width;canvas.height=bitmap.height;
      const ctx=canvas.getContext("2d")!;ctx.drawImage(bitmap,0,0);return Array.from(ctx.getImageData(10,10,1,1).data);
    }, customerImage);
    expect(pixel).toEqual([17,17,17,255]);
    await page.goto(`/workspace?report=${feedback.id}`);
    const team = page.getByRole("region", { name: "Report conversation", exact: true });
    await expect(team.locator(".reply-images img")).toHaveCount(1);
    await team.getByLabel("Message visibility", { exact: true }).selectOption("internal");
    await team.getByLabel("Private team note", { exact: true }).fill("Internal investigation screenshot.");
    await team.getByRole("button", { name: "Add screenshots to reply", exact: true }).click();
    await team.getByLabel("Choose reply screenshot", { exact: true }).setInputFiles({ name:"internal.png", mimeType:"image/png", buffer:Buffer.from(source,"base64") });
    await team.getByLabel("I reviewed this version").check();
    await team.getByRole("button", { name: "Attach reviewed screenshot", exact: true }).click();
    await team.getByLabel("Screenshot caption 1", { exact: true }).fill("Private team reference");
    await team.getByRole("button", { name: "Save private note", exact: true }).click();
    await expect(team.locator(".reply-images img")).toHaveCount(2);
    const ownerMessages = await (await request.get(`${api}/feedback/${feedback.id}/messages`)).json();
    const privateMessage = ownerMessages.find((value: { visibility: string }) => value.visibility === "internal");
    const guessed = `${api}/public/submissions/${record.access_token}/messages/${privateMessage.id}/attachments/${privateMessage.attachments[0].id}/content`;
    expect((await context.request.get(guessed)).status()).toBe(404);
    await portal.reload();
    await expect(conversation.locator(".reply-images img")).toHaveCount(1);
    await expect(conversation).not.toContainText("Private team reference");
    expect(await portal.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await conversation.screenshot({ path:`../test-results/${info.project.name}-reply-screenshots.png` });
    expect((await context.request.delete(`${api}/public/submissions/${record.access_token}`)).ok()).toBe(true);
    expect((await context.request.get(base+customerImage)).status()).toBe(404);
    expect((await request.get(`${api}/feedback/${feedback.id}/messages/${privateMessage.id}/attachments/${privateMessage.attachments[0].id}/content`)).status()).toBe(404);
  } finally { await context.close(); }
});
