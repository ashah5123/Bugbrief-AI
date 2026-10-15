# BugBrief AI

A lightweight feedback-to-fix workspace for software agencies. **Phase 1 checkpoint:** create projects, save English / Hindi / Hinglish feedback, generate a real evidence-linked report through a hosted API, and edit and save it.

React + TypeScript + Vite + Tailwind frontend; Python + FastAPI + Pydantic backend; SQLAlchemy, Alembic and SQLite. No Docker or local models. One backend process and one frontend process.

## Setup

Run from the repository root. Python 3.12 and Node 22 were used for verification.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
cp backend/.env.example backend/.env
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

No key is needed to create projects, capture feedback or save drafts. The app never substitutes mock AI responses.

To enable real AI, create a key in [Google AI Studio](https://aistudio.google.com/apikey) using a **Free Tier project with billing disabled**. Add the following to `backend/.env` using your editor; never put the key in the frontend or commit it:

```dotenv
GEMINI_API_KEY=your_key_here
FREE_TIER_CONFIRMED=true
GEMINI_MODEL=gemini-3.5-flash-lite
AI_DAILY_LIMIT=20
AI_TIMEOUT_SECONDS=45
```

Do not link billing, provide payment details or enable paid fallback. Confirm the model has active free quota in your own AI Studio project. The app cannot verify a key's billing status. Google’s unpaid service may use submitted content and outputs for product improvement and human review. Use only non-sensitive test feedback. [Provider verification and official sources](docs/PROVIDER.md), checked 15 October 2026.

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
- Real hosted API adapter, JSON-schema output, strict Pydantic validation and exact evidence quotations.
- Explicit unknown details, suggested questions, observations and separate hypotheses. AI category and priority stay labelled as suggestions.
- Editable reports; stale saves are rejected. Regenerating saves manual changes first and stores a separate AI proposal. Applying it requires an explicit action and shows a preview.
- Missing-key, billing confirmation, timeout, provider rejection, invalid-output, network and quota handling. Original feedback and reports survive errors.
- Persistent daily request/token/latency accounting, 429 pause, bounded input and output, no automatic retry or model fallback.
- Basic inbox and project navigation, search and report viewing. Responsive desktop and mobile UI, keyboard focus, accessible form labels.

A quoted source does **not** establish semantic support. In particular, a real quote could be used by AI to justify an invented interpretation. Title, description and claims require human review; the app does not claim to solve hallucinations automatically.

## What is incomplete

Stop here to test Phase 1. Screenshots, upload/redaction, stored clarification answers and attachment metadata are Phase 2. Approval, export and revision history are Phase 3. Embeddings, duplicates, audio, video, GitHub/Jira, agency accounts and production deployment remain deferred. Provider and storage protocols exist as extension seams only. No unavailable features are represented as working AI.

The report editor retains manual changes in this browser and saves them in SQLite on “Save report”. Review old reports again after changing their source feedback. There is no multi-user coordination beyond report version checks. Keep this checkpoint local.

## Verification

```sh
.venv/bin/pytest backend/tests -q
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Browser tests use installed Google Chrome, two viewports and a disposable real SQLite backend. Browser tests reserve separate localhost ports 18000 and 15173 and never use your development database. Alternatively install Playwright Chromium and adapt `channel` in `frontend/playwright.config.ts` if Chrome is unavailable. These tests use no live AI.

Separate opt-in live check, with the backend running and credentials configured:

```sh
.venv/bin/python scripts/live_check.py
```

This creates a visible “Live API check” project and feedback, then performs one real generation through the same capped endpoint. It prints SKIPPED and sends no request when credentials are absent. Do not interpret mocked provider tests as evidence of real model accuracy. Actual results are recorded in [TEST_RESULTS.md](docs/TEST_RESULTS.md).

## Manual checkpoint checklist

1. Create a project. Enter checkout feedback and save a draft. Reload, edit and save again: one draft should remain.
2. Without a key, consent and click Generate report. Verify a clear setup error and preserved text.
3. Configure a free, unbilled key; restart the backend. Generate a report. Verify the original text, unknowns, questions and every evidence reference.
4. Try English, Hindi and Hinglish examples in [evaluation cases](docs/EVALUATION.md). Check whether questions actually help and whether any actions were invented.
5. Change a report title and save. Reload and reopen it. Regenerate and inspect the proposal: your edited title should remain until you apply the new proposal.
6. Stop and restart both processes. Projects, saved feedback and reports should still exist.
7. Set `AI_DAILY_LIMIT=1`, restart and attempt generation after an earlier attempt that day. AI must pause and saving drafts must still work. Restore your normal limit afterwards.
8. Resize to a phone width; test navigation, project dialog and keyboard tab order.

## Storage and upgrades

SQLite is at `data/bugbrief.db`. Stop the backend and copy this file for a development backup. Browser-local unsaved edits are separate; save them before moving devices. Future attachments will use `data/attachments/`; Phase 1 accepts no upload files. SQLAlchemy allows PostgreSQL later, storage/provider protocols allow replacing local storage and free APIs, and the generation boundary allows a durable queue later. See [architecture and checklist](docs/ARCHITECTURE.md).

An optional intentionally buggy self-test website is at [demo/index.html](demo/index.html). Serve it independently with `python3.12 -m http.server 4174 --bind 127.0.0.1 --directory demo` and open http://127.0.0.1:4174. It contains no AI or dependencies. Its four defects are deliberate and documented on the page.
