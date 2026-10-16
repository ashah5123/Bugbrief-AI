// Opt-in real hosted check. No generated responses or provider test doubles.
import { chromium } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
const base = "http://127.0.0.1:5173";
const backend = "http://127.0.0.1:8001";
const code = (
  process.env.AGENCY_ACCESS_CODE ||
  (await readFile(
    new URL("../../data/agency-access.txt", import.meta.url),
    "utf8",
  ))
).trim();
const browser = await chromium.launch({ channel: "chrome" });
try {
  const agency = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  const login = await agency.request.post(backend + "/api/auth/login", {
    data: { code },
  });
  if (!login.ok())
    throw new Error(
      "Agency sign-in failed. Check the local access-code configuration.",
    );
  const health = await (
    await agency.request.get(backend + "/api/health")
  ).json();
  if (
    !health.ai_configured ||
    !health.free_tier_confirmed ||
    health.usage.paused ||
    health.usage.limit - health.usage.attempts < 2
  ) {
    console.log(
      "SKIPPED: credentials, confirmed free tier and two available local attempts are required. No inference request sent.",
    );
    process.exitCode = 2;
  } else {
    const project = await (
      await agency.request.post(backend + "/api/projects", {
        data: { name: "Customer workflow demo", url: base },
      })
    ).json();
    const link = await (
      await agency.request.post(
        backend + `/api/projects/${project.id}/intake-link`,
        { data: {} },
      )
    ).json();
    const customer = await browser.newContext({
      viewport: { width: 1280, height: 800 },
    });
    const page = await customer.newPage();
    await page.goto(base + "/demo/" + link.token);
    await page.getByRole("button", { name: "Pay now", exact: true }).click();
    await page
      .getByRole("button", { name: "Report a problem", exact: true })
      .click();
    const form = page.frameLocator('iframe[title="Report a problem"]');
    await form
      .getByLabel("What went wrong?", { exact: true })
      .fill("Checkout isn't working.");
    await form.getByLabel("Your name").fill("Demo customer");
    await form.getByLabel("This is the browser I used").check();
    await form.getByLabel("I agree to this external processing").check();
    await form
      .getByRole("button", { name: "Continue with a quick check" })
      .click();
    await form
      .getByRole("heading", { name: "A couple of quick details." })
      .waitFor({ timeout: 65000 });
    const questions = form.locator(".customer-question");
    const count = await questions.count();
    if (!count)
      throw new Error(
        "The ambiguous test feedback produced no clarification questions. Inspect the saved draft.",
      );
    await mkdir(new URL("../../test-results/", import.meta.url), {
      recursive: true,
    });
    await page.screenshot({
      path: new URL(
        "../../test-results/live-customer-questions.png",
        import.meta.url,
      ).pathname,
      fullPage: false,
    });
    for (let i = 0; i < count; i++) {
      const row = questions.nth(i);
      const question = (await row.locator("label").innerText()).toLowerCase();
      let answer = "I’m not sure.";
      if (/browser|device|platform|operating/.test(question))
        answer =
          "Chrome in this desktop browser for the demo. I don't know the device model.";
      else if (/expect|should|intended/.test(question))
        answer = "I expected the payment form to open.";
      else if (/often|always|frequency|repeat/.test(question))
        answer =
          "I tried once in this demo. I haven't tested whether it always happens.";
      else if (
        /happen|see|response|error|message|click|step|action|behavior|behaviour|observ/.test(
          question,
        )
      )
        answer =
          "I clicked Pay now once. Nothing changed on the page and no error appeared.";
      await row.locator("textarea").fill(answer);
    }
    await form.getByRole("button", { name: "Save details & review" }).click();
    await form
      .getByRole("heading", { name: "Ready for the team?" })
      .waitFor({ timeout: 65000 });
    await form
      .getByText("A draft brief is prepared for agency review.", {
        exact: true,
      })
      .waitFor();
    const pending = await (
      await agency.request.get(backend + "/api/feedback")
    ).json();
    if (pending.some((item) => item.project_id === project.id))
      throw new Error("Unsent customer draft appeared in the agency inbox.");
    await form
      .getByRole("button", { name: "Send to the agency", exact: true })
      .click();
    await form
      .getByRole("heading", { name: "The team has your feedback." })
      .waitFor();
    const all = await (
      await agency.request.get(backend + "/api/feedback")
    ).json();
    const received = all.find((item) => item.project_id === project.id);
    if (
      !received?.report ||
      !received.proposal ||
      !received.clarifications.length ||
      received.customer?.context.source !== "demo"
    )
      throw new Error(
        "The saved handoff is missing report, revision, answers or captured context.",
      );
    if (
      (await customer.request.get(backend + "/api/feedback")).status() !== 401
    )
      throw new Error("Anonymous customer could access the agency inbox.");
    const owner = await agency.newPage();
    await owner.goto(base + "/workspace");
    await owner
      .getByLabel("Filter by project", { exact: true })
      .selectOption(project.id);
    await owner.locator(".feedback-row").click();
    await owner
      .getByText("A new AI proposal is ready.", { exact: true })
      .waitFor();
    await owner.screenshot({
      path: new URL(
        "../../test-results/live-agency-handoff.png",
        import.meta.url,
      ).pathname,
      fullPage: false,
    });
    console.log(
      "LIVE CUSTOMER FLOW PASSED: real follow-up questions, saved answers, real revised proposal, captured page/browser context, final receipt and protected agency inbox.",
    );
    console.log("Questions answered:", count);
    console.log("Revised title:", received.proposal.title);
    console.log("Try the demo:", base + "/demo/" + link.token);
  }
} catch (error) {
  console.error("LIVE CUSTOMER CHECK FAILED:", error.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
