# BugBrief AI

A lightweight feedback-to-fix workspace for software agencies. **Phase 2 checkpoint:** add reviewed and redacted screenshots, request hosted vision observations, answer clarification questions, and generate revised reports with traceable evidence while preserving manual edits.

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

## Upgrade an existing Phase 1 checkout

Stop only BugBrief’s backend, preserve `backend/.env`, and back up `data/bugbrief.db` before migrating. Then run:

```sh
.venv/bin/pip install -r backend/requirements.lock.txt
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

Restart the backend with the command below. The migration upgrades to `0002` and preserves existing projects, original feedback, saved reports and usage records. An automatic pre-migration development backup was created for this workspace under `data/backups/`; migrations themselves do not create backups.

## Run

Terminal 1, repository root:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Terminal 2, repository root:

```sh
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. API documentation: http://127.0.0.1:8001/docs. Restart the backend after editing `.env`. Run only **one worker** so the single-job lock applies. This is a local development checkpoint, without authentication; bind to loopback. Do not expose it publicly before Phase 8.

## What works

- Project creation with optional URL; original feedback plus optional page, browser and device context.
- Local browser draft recovery and durable SQLite saves. Draft IDs survive reload so re-saving does not duplicate a submission.
- Reviewed PNG/JPEG screenshots: browser preview, opaque rectangle redaction by drag or keyboard coordinates, undo/reset, and explicit save confirmation. Original bytes stay in the browser tab; only the reviewed image is uploaded locally.
- Three screenshots per feedback, 2 MiB per file, at most four megapixels. Backend verifies decoded format and dimensions, rejects animation/corruption, strips metadata, stores attachment records and supports deletion.
- Separate consent and explicit action for hosted vision analysis. Image bytes never go to the provider automatically. Structured visible observations are labelled as unverified machine interpretations.
- Suggested clarification questions and append-only user answers/corrections. Answers are independently saved and can be cited in revised reports. Maximum 20 entries per feedback item.
- Replaceable hosted text and vision adapters, JSON-schema output, strict Pydantic validation and exact source quotations. No local vision or language model.
- Explicit unknown details, suggested questions, observations and separate hypotheses. AI category and priority stay labelled as suggestions.
- Editable reports; stale saves are rejected. Regenerating saves manual changes first and stores a separate AI proposal. Applying it requires an explicit action and shows a preview.
- Missing-key, billing confirmation, timeout, provider rejection, invalid-output, network and quota handling. Original feedback, reviewed screenshots, answers and reports survive errors.
- Shared daily request/token/latency accounting for text and vision, a single job lock, 429 pause, bounded input/output, and no automatic retry or model fallback. Each screenshot analysis consumes one attempt; a report request consumes another.
- Basic inbox and project navigation, search and report viewing. Responsive desktop and mobile UI, keyboard focus, accessible form labels.

Report regeneration uses saved screenshot observations and user answers with stable source references; it does not resend image bytes. Screenshots cannot be cited as reproduction steps or expected behaviour. A quoted source does **not** establish semantic support. In particular, a real quote could be used by AI to justify an invented interpretation. Title, description and claims require human review; the app does not claim to solve hallucinations automatically.

## What is incomplete

Stop here to test Phase 2. Approval, Markdown/JSON export and revision history are Phase 3. Semantic duplicates, audio, video, GitHub/Jira, agency accounts and production deployment remain deferred. No unavailable features are represented as working functionality. Live hosted text and vision requests have succeeded with the user’s configured key. A single English demo scenario was reviewed; broader accuracy and Hindi/Hinglish evaluation remain pending.

Still images cannot establish prior actions, responsiveness, causal errors or root causes. Machine observations can be wrong. Verify the screenshot against each observation, then add a clarification to correct it. An analyzed image is immutable; upload a new reviewed image for a different version. Deleting a screenshot removes stored bytes and analysis; a metadata tombstone remains for old report provenance. Existing reports are preserved and marked for review when evidence changes. Pending proposals are discarded after an evidence change.

The report editor retains manual changes in this browser and saves them in SQLite on “Save report”. Review old reports again after changing their source feedback. There is no multi-user coordination beyond report version checks. Keep this checkpoint local.

## Verification

```sh
.venv/bin/pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Browser tests use installed Google Chrome, two viewports and a disposable real SQLite backend. Browser tests reserve separate localhost ports 18000 and 15173 and never use your development database. Alternatively install Playwright Chromium and adapt `channel` in `frontend/playwright.config.ts` if Chrome is unavailable. These tests use no live AI.

Separate opt-in live checks, with the backend running and credentials configured:

```sh
.venv/bin/python scripts/live_check.py
# Optional vision + clarification + report check; inspect/redact the file first:
.venv/bin/python scripts/live_check.py --screenshot /absolute/path/to/reviewed.png --reviewed
```

This creates a visible “Live API check” project, feedback and a test clarification, then performs one real generation through the same capped endpoint. With `--screenshot` and `--reviewed`, it first uploads that reviewed local image and performs one real vision call. That path consumes two provider attempts. It prints SKIPPED and sends no request when credentials are absent. Do not interpret mocked provider tests as evidence of real model accuracy. Actual results are recorded in [TEST_RESULTS.md](docs/TEST_RESULTS.md).

## Manual checkpoint checklist

1. Create a project. Save written feedback, reload and resave it: one draft should remain. English, Hindi and Hinglish text are preserved.
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

SQLite is at `data/bugbrief.db`. Stop the backend and back up this file **and `data/attachments/` together** for a development backup. A database-only backup cannot restore deleted screenshot bytes. Browser-local unsaved edits are separate; save them before moving devices. Reviewed attachments are stored at `data/attachments/`. Unsaved screenshot previews/redaction masks exist only in the current tab and are discarded on reload. SQLAlchemy allows PostgreSQL later, storage/provider protocols allow replacing local storage and free APIs, and the generation boundary allows a durable queue later. See [architecture and checklist](docs/ARCHITECTURE.md).

An optional intentionally buggy self-test website is at [demo/index.html](demo/index.html). Serve it independently with `python3.12 -m http.server 4174 --bind 127.0.0.1 --directory demo` and open http://127.0.0.1:4174. It contains no AI or dependencies. Its four defects are deliberate and documented on the page.
