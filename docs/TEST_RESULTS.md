# Actual verification — 15 October 2026

- **35 pytest checks passed** in 1.10 seconds. Includes English/Hindi/Hinglish text persistence, schema validation, fabricated evidence quotations, provider HTTP failures/timeouts, quota pause, single-job lock, daily cap, consent/billing guards, original feedback preservation, manual-edit preservation through regeneration, explicit proposal application, stale save rejection, body size limit and migration/restart persistence.
- **4 Playwright checks passed** in 22.3 seconds in installed Google Chrome: desktop 1280 × 720 and mobile 390 × 844. Real disposable FastAPI + SQLite server, project creation, draft saving/reloading without duplication, missing-key preservation, navigation, no horizontal overflow, manual report editing/saving/reopening, and preserved source feedback. No AI response mocking in browser tests; report editing uses an explicitly manual fixture saved through the API.
- **Production build passed:** TypeScript compilation and Vite bundling. No build warning after moving the font stylesheet reference to the document head.
- **Alembic upgrade to head passed** for the local database and a separate disposable restart-test database.
- **Live check SKIPPED**, exit code 2: no API credentials supplied. No external inference request executed; real API connectivity, model access, language interpretation, useful questions and factual accuracy remain unverified.
- Running development services responded successfully: backend health OK at port 8001, frontend HTTP 200 at port 5173. AI is explicitly unconfigured.
- Official provider availability/pricing/billing/rate/data documentation was read. Account-specific quotas cannot be verified without the operator's account.
- Desktop and mobile screenshots were inspected. Fixed the sidebar's overflow on short viewports and enlarged supporting text.

The pytest suite uses explicitly injected fake generators or mocked HTTP transport for generation checks. Those checks prove handling and validation, not real AI quality. Restart persistence is verified using separate Python processes and a real migrated SQLite file.

One non-failing test dependency warning remains: current Starlette deprecates its httpx TestClient transport in favor of httpx2. Production uses direct httpx; this warning affects the isolated test harness only. Browser runs also report a harmless FORCE_COLOR/NO_COLOR environment warning.

Screenshots and traces go to ignored `test-results/` folders. No test data is added to the development database.
