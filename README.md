# BugBrief AI

A lightweight feedback-to-fix workspace for software agencies. **Customer-to-agency checkpoint:** customers submit directly, share reviewed screenshots and browser context, answer hosted follow-up questions, and send one evidence-backed handoff to the agency for human review.

React + TypeScript + Vite + Tailwind frontend; Python + FastAPI + Pydantic backend; SQLAlchemy, Alembic and SQLite. No Docker or local models. One backend process and one frontend process.

## Setup

Run from the repository root. Python 3.12 and Node 22 were used for verification.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
cp -n backend/.env.example backend/.env
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

No key is needed to create projects, capture feedback, save reviewed screenshots or store clarification answers. The app never substitutes mock AI responses.

To enable real AI, create a key in [Google AI Studio](https://aistudio.google.com/apikey) using a **Free Tier project with billing disabled**. Add the following to `backend/.env` using your editor; never put the key in the frontend or commit it:

```dotenv
GEMINI_API_KEY=your_key_here
FREE_TIER_CONFIRMED=true
GEMINI_MODEL=gemini-3.5-flash-lite
AI_DAILY_LIMIT=20
AI_TIMEOUT_SECONDS=45
```

Do not link billing, provide payment details or enable paid fallback. Confirm the model has active free quota in your own AI Studio project. The app cannot verify a key's billing status. Google’s unpaid service may use submitted content and outputs for product improvement and human review. Use only non-sensitive test feedback. [Provider verification and official sources](docs/PROVIDER.md), checked 15 October 2026.

## Upgrade an existing checkout

Stop only BugBrief’s backend, preserve `backend/.env`, and back up `data/bugbrief.db` before migrating. Then run:

```sh
.venv/bin/pip install -r backend/requirements.lock.txt
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

Restart the backend with the command below. The migration upgrades to `0005` and preserves existing projects, original feedback, saved reports and usage records. An automatic pre-migration development backup was created for this workspace under `data/backups/`; migrations themselves do not create backups.

## Run

Terminal 1, repository root:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Terminal 2, repository root:

```sh
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173** and choose **I’m with the company** or **I’m a customer**. The company workspace is at `/workspace`; the customer portal is at `/customer`. API documentation: http://127.0.0.1:8001/docs. Restart the backend after editing `.env`. Run only **one worker** so the single-job lock applies. This is a local development checkpoint with single-agency access protection; bind to loopback. First startup creates a private `data/agency-access.txt` file. Enter that code at the agency sign-in screen. Customers use scoped links and need no agency code. Keep the code out of chat, version control and client-side source.

## Try the customer workflow

1. Sign into the agency workspace with the code in `data/agency-access.txt`.
2. Click **Collect customer feedback**, select a project and open **Try the embedded demo**. Alternatively open the customer form link in a private browser window.
3. On the demo site, try the intentionally unresponsive Pay now button. Open **Report a problem**. The widget captures that page's origin/path and viewport; it excludes query strings and fragments. The customer can omit browser details and must separately confirm whether this is the browser used for the issue.
4. Describe the problem and optionally attach reviewed/redacted screenshots. Opt into external processing if appropriate. Continue to receive up to three genuine follow-up questions; answer what you know, then review and **Send to the agency**.
5. Return to the agency inbox. It refreshes on tab focus and every 15 seconds. Open the customer submission to review its original words, answers, captured context and revised report proposal. Apply the proposal only after checking the evidence.

The local demo runs on this Mac. **A localhost link is not reachable by remote customers.** No site was deployed publicly. External customer use needs a reachable HTTPS deployment and the remaining production-readiness work below.

To embed the button on a website you control, set the project's website URL in the sharing dialog and copy the generated script snippet before the site's closing body tag. The widget opens an isolated iframe; it does not replace fetch/console, scrape form fields, read cookies or record browsing history. Context messages are accepted only from the configured site origin or the explicitly labelled local demo preview. An ordinary standalone link cannot automatically know which other webpage had the issue; it asks for that URL.

## Choose a role and manage reports

The home page first asks whether you are with the company or are a customer. **Company workspace** opens `/workspace` behind the existing agency sign-in. **Customer portal** opens `/customer` with **New customer → Create an account** and **Returning customer → Sign in**. Customers register with a name, email and password, connect their project invitation once, and see their own projects/reports after signing in on any browser. Direct project links and embedded forms still go straight to the customer workflow. **Switch role** returns to the chooser; it does not grant workspace access or end an existing company session.

Customers can use **Delete my report** on their saved-report card or within a submission, including after sending it. Company users can open any report or draft and use **Delete report**. Both require a confirmation with a **Keep report** option. Deletion removes original text, report/proposal contents, answers, customer/browser details and uploaded image files from the active workspace, and closes the private return link. Reports cannot be restored through the interface. Minimal content-free identifiers and usage counters remain to enforce daily limits and prevent old save requests from recreating a deleted report; existing operator backups and any provider-held copies are outside this deletion operation.

Account-owned reports require the matching customer session for reading, editing, screenshot access and deletion, even if someone else knows the report URL. Earlier guest reports remain available through their private capability and can be explicitly saved to a customer account. The dashboard lists only the signed-in account’s reports and connected projects; no public customer/project directory is exposed. Names and matching email addresses never establish report ownership.

## Access and customer privacy

The agency API requires a signed HttpOnly SameSite=Strict session cookie or a backend/operator `X-Agency-Key` header. Sessions expire after 12 hours; cookies use Secure on HTTPS. The auto-generated access code persists locally with owner-only file permissions. You may override it with `AGENCY_ACCESS_CODE` in the backend environment. Company staff still share one agency workspace/code; staff roles and agency-to-agency isolation remain unimplemented. Customer accounts use a separate session and never grant agency access.

Each project link can be revoked. Guest submissions receive a separate random private return link. Account-owned submissions appear in the customer dashboard without requiring a return link. Customers can read only their own submission and reviewed image files; public responses never include internal report/proposal JSON, other customer submissions, usage counters or credentials. Submitted entries become read-only to the customer, with an option to delete their report. Private capability paths are redacted from backend access logs and API responses are not cacheable.

Draft text and answers are recovered in the customer's browser. Saved drafts and reviewed images are stored on the agency's local backend but do not appear in its review inbox until **Send to the agency**. A guest return link permits access to its submission, so keep it private. Revoking a project invitation prevents new reports and closes guest return links. Already account-owned reports remain available to their owner and the company; they can still be deleted.

Automatic checking is optional. If credentials, quotas or the provider are unavailable, original feedback and reviewed images stay saved and the customer can send a manual-review handoff. No invented follow-up questions or report responses are substituted. Processing uses one job at a time and the existing global request cap. By default a project link permits 10 new submissions and 6 processing attempts per UTC day; an individual submission permits 5 attempts. Configure `PUBLIC_SUBMISSIONS_DAILY_LIMIT` and `PUBLIC_AI_DAILY_LIMIT` on the backend if needed. These local counters do not guarantee provider billing limits. Keep provider billing disabled.

Customer authentication uses salted scrypt password hashes and database-backed seven-day HttpOnly/SameSite=Strict sessions (Secure on HTTPS). Logout revokes the current session; only hashes of random session tokens are stored. Login/registration have separate per-address attempt limits in this single-process checkpoint. No email service is connected: email verification, password recovery and staff-assisted account recovery are not implemented. An email address is a sign-in identifier, not verified proof of project membership. Embedded sign-in/sign-up links open a separate tab to avoid third-party iframe cookie restrictions.

## What works

- Customer account creation, sign-in/sign-out, projects and reports across browsers, plus recovery of earlier guest reports.
- Customer-facing project forms, private resume links, idempotent saves, final receipts, project-link revocation and an embeddable Report a problem button.
- Captured browser user agent, language, timezone, screen and viewport context; explicit issue-browser confirmation. No device model or historical interaction is inferred from this context. Optional customer names stay with the agency and are excluded from generation input.
- Project creation with optional URL; original feedback plus optional page, browser and device context.
- Local browser draft recovery and durable SQLite saves. Draft IDs survive reload so re-saving does not duplicate a submission.
- Reviewed PNG/JPEG screenshots: browser preview, opaque rectangle redaction by drag or keyboard coordinates, undo/reset, and explicit save confirmation. Original bytes stay in the browser tab; only the reviewed image is uploaded locally.
- Three screenshots per feedback, 2 MiB per file, at most four megapixels. Backend verifies decoded format and dimensions, rejects animation/corruption, strips metadata, stores attachment records and supports deletion.
- Separate consent and explicit action for hosted vision analysis. In agency capture, analyze actions are separate. In customer intake, an explicitly consented quick check analyzes reviewed screenshots sequentially before generating follow-up questions. Image bytes never go to the provider without that consent. Structured visible observations are labelled as unverified machine interpretations.
- Suggested clarification questions and append-only user answers/corrections. Answers are independently saved and can be cited in revised reports. Maximum 20 entries per feedback item.
- Replaceable hosted text and vision adapters, JSON-schema output, strict Pydantic validation and exact source quotations. No local vision or language model.
- Explicit unknown details, suggested questions, observations and separate hypotheses. AI category and priority stay labelled as suggestions.
- Editable reports; stale saves are rejected. Regenerating saves manual changes first and stores a separate AI proposal. Applying it requires an explicit action and shows a preview.
- Missing-key, billing confirmation, timeout, provider rejection, invalid-output, network and quota handling. Original feedback, reviewed screenshots, answers and reports survive errors.
- Shared daily request/token/latency accounting for text and vision, a single job lock, 429 pause, bounded input/output, and no automatic retry or model fallback. Each screenshot analysis consumes one attempt; a report request consumes another.
- Basic inbox and project navigation, search and report viewing. Responsive desktop and mobile UI, keyboard focus, accessible form labels.

Report regeneration uses saved screenshot observations and user answers with stable source references; it does not resend image bytes. Screenshots cannot be cited as reproduction steps or expected behaviour. A quoted source does **not** establish semantic support. In particular, a real quote could be used by AI to justify an invented interpretation. Title, description and claims require human review; the app does not claim to solve hallucinations automatically.

## What is incomplete

Stop here to test the customer-to-agency workflow. Approval, Markdown/JSON export and revision history are Phase 3. Semantic duplicates, audio, video, GitHub/Jira, multi-user agency accounts, workspace isolation and production deployment remain deferred. No unavailable features are represented as working functionality. Live hosted text and vision requests have succeeded with the user’s configured key. English report/vision examples and a real customer-to-agency clarification/revision flow were reviewed; broader accuracy and Hindi/Hinglish evaluation remain pending.

Still images cannot establish prior actions, responsiveness, causal errors or root causes. Machine observations can be wrong. Verify the screenshot against each observation, then add a clarification to correct it. An analyzed image is immutable; upload a new reviewed image for a different version. Deleting a screenshot removes stored bytes and analysis; a metadata tombstone remains for old report provenance. Existing reports are preserved and marked for review when evidence changes. Pending proposals are discarded after an evidence change.

The report editor retains manual changes in this browser and saves them in SQLite on “Save report”. Review old reports again after changing their source feedback. There is no multi-user coordination beyond report version checks. Keep this checkpoint local.

## Verification

```sh
.venv/bin/pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Browser tests use installed Google Chrome, two viewports and a disposable real SQLite backend. Browser tests reserve separate localhost ports 18000, 15173 and 14174 and never use your development database. Alternatively install Playwright Chromium and adapt `channel` in `frontend/playwright.config.ts` if Chrome is unavailable. These tests use no live AI.

Separate opt-in live checks, with the backend running and credentials configured:

```sh
.venv/bin/python scripts/live_check.py
# Optional vision + clarification + report check; inspect/redact the file first:
.venv/bin/python scripts/live_check.py --screenshot /absolute/path/to/reviewed.png --reviewed
```

This creates a visible “Live API check” project, feedback and a test clarification, then performs one real generation through the same capped endpoint. With `--screenshot` and `--reviewed`, it first uploads that reviewed local image and performs one real vision call. That path consumes two provider attempts. It prints SKIPPED and sends no request when credentials are absent. Do not interpret mocked provider tests as evidence of real model accuracy. Actual results are recorded in [TEST_RESULTS.md](docs/TEST_RESULTS.md).

Opt-in live customer-to-agency browser check (creates a visible demo project and uses up to two hosted text calls; Chrome must be installed):

```sh
node frontend/scripts/live-customer-check.mjs
```

It uses the local agency code to sign in with a cookie, creates an anonymous customer browser, reports the demo's checkout problem, answers actual hosted follow-up questions, sends the submission, verifies the revised proposal/context in the agency inbox and checks anonymous denial of the agency API. Agency credentials are never installed as global browser headers.

## Customer checkpoint checklist

1. Open the agency workspace in a private window: the access-code screen must appear. An unauthenticated request to `/api/feedback` must return 401. Sign in with the local code.
2. Share a project link. Open it in another private window; no agency code should be required and no agency navigation or report JSON should be shown.
3. Use the embedded demo and verify captured page URL/viewport. In a standalone link, enter the affected URL yourself. Omit browser context or leave issue-browser confirmation unchecked and verify the agency sees that uncertainty.
4. Save a redacted screenshot, refresh, and confirm the reviewed image remains. Private return links must only expose their own images.
5. Consent to a quick check, answer the actual follow-up questions and send. Verify the agency inbox contains the original feedback, answers, context and a proposed revision. Existing manual edits must remain until the agency explicitly applies the revision.
6. Without provider access, send anyway: the agency receives the original evidence for manual review. Unsent drafts should stay out of the inbox. Repeated Send must not create another submission.
7. Revoke a project link: the form and existing private return links must stop working; the agency's saved reports must remain.
8. Restart the backend and verify the access code, links and submissions persist. Test phone-width intake and keyboard screenshot redaction.

## Manual agency-capture checklist

1. Expand **Add feedback on a customer’s behalf** or click **New feedback**. Create a project. Save written feedback, reload and resave it: one draft should remain. English, Hindi and Hinglish text are preserved.
2. Select a non-sensitive PNG/JPEG. Before saving, draw a black rectangle over a detail or use keyboard coordinates. Undo and redraw; confirm review and save. Nothing should reach the hosted provider yet.
3. Reload: the reviewed screenshot should still be visible. Open its preview and verify that the masked pixels are opaque. Try a corrupt file, unsupported type, a file over 2 MiB, or an image over four megapixels: reject them without losing text or existing attachments. A fourth screenshot must also be rejected.
4. Without a key, consent and click Analyze reviewed screenshot. Confirm the setup error and preserved image. Saving clarification answers should still work.
5. Configure a free, unbilled key, restart the backend, consent and analyze. Check every visible observation and its limitations against the image. No actions before the screenshot should be claimed.
6. Generate a report from text plus analyzed screenshots, or from analyzed screenshots alone. For an image-only submission, expected behaviour and interaction history should remain unknown; reproduction steps must not be invented.
7. In **Evidence & answers**, choose a suggested question and save an answer. Add a correction: both entries should remain. Try contradictory answers and check that the next report identifies uncertainty rather than silently picking one.
8. Edit the report title, then save an answer without first clicking Save report. Your manual edits should be saved before the evidence changes. Generate a new proposal: your title stays until you explicitly apply it. New answers or screenshot changes discard stale proposals.
9. Delete a screenshot: its preview/content URL should stop working, while the original text and manual report remain. Restart both processes: saved screenshots, observations, answers, reports and usage should persist.
10. Set `AI_DAILY_LIMIT=1`, restart and try another text or vision call after an earlier attempt. Processing must pause while local saves continue to work. Restore your normal cap afterwards.
11. Resize to a phone width and test navigation, redaction, evidence tabs and keyboard access. Use the [evaluation cases](docs/EVALUATION.md) to record actual model quality separately from handling checks.

## Storage and upgrades

SQLite is at `data/bugbrief.db`. Also preserve `data/agency-access.txt` for the same agency code and valid signed sessions; replacing it rotates access and invalidates old sessions. Stop the backend and back up this file **and `data/attachments/` together** for a development backup. A database-only backup cannot restore deleted screenshot bytes. Browser-local unsaved edits are separate; save them before moving devices. Reviewed attachments are stored at `data/attachments/`. Unsaved screenshot previews/redaction masks exist only in the current tab and are discarded on reload. SQLAlchemy allows PostgreSQL later, storage/provider protocols allow replacing local storage and free APIs, and the generation boundary allows a durable queue later. See [architecture and checklist](docs/ARCHITECTURE.md).

An optional intentionally buggy self-test website is at [demo/index.html](demo/index.html). Serve it independently with `python3.12 -m http.server 4174 --bind 127.0.0.1 --directory demo` and open http://127.0.0.1:4174. It contains no AI or dependencies. Its four defects are deliberate and documented on the page.
