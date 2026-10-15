# Actual verification — Phase 2, 15 October 2026

- **69 pytest checks passed.** Includes the 35 Phase 1 checks plus real PNG/JPEG decoding, format mismatch/corruption, byte/pixel/count caps, explicit review and consent, metadata stripping, transparent-pixel flattening, preview/deletion, per-feedback attachment paths, clarification language/history/corrections/caps, screenshot evidence restrictions, manual-edit preservation, shared text/vision quotas and actual concurrent job rejection.
- **8 Playwright checks passed** in 19.8 seconds in installed Google Chrome: desktop 1280 × 720 and mobile 390 × 844. Real disposable FastAPI + migrated SQLite + local attachment storage. Checks include project/draft/report regression, review confirmation, keyboard redaction, saved opaque pixels (`17,17,17,255`), reload persistence, missing-key preservation, screenshot deletion, suggested clarification answers, corrections, unsaved report edit preservation and failed revised-generation preservation.
- **Production build passed:** TypeScript compilation and Vite bundling. Browser JavaScript is approximately 87 KiB gzipped. No build warnings.
- **Migration and restart checks passed:** upgrade an existing `0001` database to `0002`, preserve original feedback and manual report content, and read screenshot bytes/analysis, clarification history, usage count and quota pause from a separate Python process after restart.
- **Development database migrated to `0002` (head).** Before migration, a SQLite backup was created at `data/backups/before-phase2-20261015T074053Z.db` while BugBrief’s backend was stopped. No browser-test data was written to this database.
- **Live text and vision checks PASSED after credentials were configured.** The explicit text-only CLI check returned a validated report; the screenshot-assisted CLI check returned validated remote image observations and a report citing the screenshot and saved clarification. The image was captured from the local non-sensitive demo site and visually reviewed before submission. One initial report attempt returned the application’s provider-failure response (HTTP 502); the cause was not established and the next manually triggered request succeeded. No automatic retry, model fallback or billing change was introduced.
- Official provider pricing, image-understanding and unpaid-data terms were checked again. Account-specific free quota and billing status cannot be verified without the operator's account.
- Desktop/mobile screenshot review and clarification views were visually inspected. Redaction has pointer and keyboard controls, saves opaque pixels, flattens transparency, and uploads only the reviewed version. The backend strips image metadata independently.

The pytest suite uses explicitly injected fake generators or mocked HTTP transport for provider checks. Browser report/clarification tests use explicitly manual report fixtures and the real missing-key path; they never simulate successful inference. These tests prove validation and application behavior, not model accuracy. The live script exercised image understanding with `--screenshot PATH --reviewed` through the normal capped endpoints.

One non-failing dependency warning remains: current Starlette deprecates its httpx TestClient transport in favor of httpx2. Production uses direct httpx; this warning affects the isolated test harness only. Browser runs also report a harmless FORCE_COLOR/NO_COLOR environment warning.

The reviewed live screenshot correctly identified the demo’s overlapping mobile panels and explicitly said still images cannot prove interaction history or causality. The sample report included only the stated click as a reproduction step, cited the saved clarification and image observations, and asked for the missing page URL. This is a single English scenario; broad language/accuracy evaluation remains pending.

Screenshots and traces are in ignored `test-results/` folders. No credentials, local database contents or uploaded screenshots are committed.

## Earlier Phase 1 checkpoint

35 pytest checks and 4 desktop/mobile browser checks passed; production build and migration passed. Live text generation was skipped without credentials. Phase 2 retains those regression checks.
