# Customer-account verification — 16 October 2026

- **126 backend checks passed** (11.85 seconds). Covers salted password storage, normalized/unique credentials, validation, generic failed-login responses, login/signup attempt limits, hashed HttpOnly session tokens, expiry, logout/revocation, HTTPS cookies, origin checks, company/customer session separation, account-scoped report/project lists, report/image mutation isolation, explicit guest claims, revoked invitations, and account/session persistence across independent processes.
- **All 28 distinct desktop/mobile browser checks passed.** The full run had one Chrome page-setup timeout before app steps (27 passed); that mobile clarification test passed when rerun (3.1 seconds). After final sign-in-link changes, all 14 affected account/customer checks passed again (29.9 seconds). These checks use a disposable backend and no hosted model calls.
- **Production build passed** after TypeScript compilation and Vite bundling.
- Actual browser workflow: create an account, connect a project once, submit a report, sign out, open a fresh browser context, sign in without a return link, find the same report and delete it. Guest-to-account recovery and signed-out report sign-in guidance were also checked. Desktop customer-entry and mobile account-dashboard screenshots were visually inspected.
- Local database upgraded to **0005** after backup `data/backups/before-customer-accounts-20261016T082316Z.db`. Existing feedback, submission, project-link and usage rows were compared before/after migration and preserved. Live read-only checks confirmed account entry pages, protected session/report endpoints, company access and schema revision. No sample accounts or hosted model requests were added to the operator’s database.

Email verification and password recovery are not implemented; the email address is a local sign-in identifier. The application remains local, with a shared company code and separate customer accounts.

# Role selection and deletion verification — 16 October 2026

- **110 backend tests passed.** New checks cover signed-company deletion, customer capability isolation, removal of text/reports/proposals, attachment bytes and rows, clarification answers and browser/name data; deleted-link reads and old nonce replay fail. Deletion cannot race an active processing job. Daily attempt/pause and submission limits survive erasure. Migration from `0003` and deletion persistence were checked across independent processes.
- **24 desktop/mobile Playwright tests passed** in installed Chrome (38.1 seconds), using disposable SQLite and no hosted model calls. Includes role entry/sign-in/switching, same-site scoped link validation, browser-local customer report lists, other-browser isolation, cancel/confirm deletion, customer receipt/draft deletion, a fresh draft after deletion, company report/draft deletion and all prior workflow regressions.
- **Production build passed** after TypeScript compilation and Vite bundling (approximately 99 KiB gzipped browser JavaScript).
- Desktop welcome and mobile customer-report screens were rendered and visually inspected. Screenshots are in ignored `test-results/`.
- Local database upgraded to **`0004` (head)** after creating `data/backups/before-report-deletion-20261016T073309Z.db`. All existing feedback rows were preserved during migration. Live read-only checks confirmed the three entry pages, agency API protection and the migrated database. Existing user reports were not deleted for testing; no extra model requests were needed.

The customer list is local to a browser and possession of the private return link authorizes access/deletion. There are no separate customer accounts. Active report contents are erased, while content-free quota/idempotency tombstones remain; existing operator backups and provider-retained inputs are not modified.

## Earlier customer-to-agency verification — 15 October 2026

- **101 backend checks passed.** Includes earlier regressions plus agency sessions, anonymous isolation, scoped/revoked links, idempotent drafts, reviewed uploads, consent, quota enforcement, actual follow-up processing, answer/revision preservation, explicit final send, original customer evidence protection, cache headers and restart persistence.
- **18 Playwright checks passed** in installed Google Chrome across desktop and mobile (2.0 minutes). Real disposable backend, SQLite and separate website origin; covers anonymous embedded submission, reviewed screenshot preservation, workspace protection, link revocation, query/fragment exclusion, overflowing mobile host pages and retry after a deliberately lost save response without duplicate submissions. These browser tests make no hosted model calls.
- **Production build passed:** TypeScript and Vite; browser JavaScript approximately 97 KiB gzipped.
- **Live hosted customer workflow passed:** an anonymous browser entered “Checkout isn't working” on the embedded demo, received three genuine follow-up questions, saved answers, received a revised report proposal and sent the submission. The agency received original feedback, answers, confirmed browser/page/viewport context and the proposal. Anonymous agency access returned 401. This used the normal configured provider and capped endpoints, without mocked inference.
- **Development database migrated to `0003` (head).** Backup before migration: `data/backups/before-customer-intake-20261016T021721Z.db` (UTC filename). Existing records preserved; disposable browser tests use a separate database.
- Customer form, receipt, agency handoff and desktop/mobile layouts were visually inspected. Screenshots and traces remain in ignored `test-results/` folders.

The application remains local. Public links need a reachable HTTPS deployment before remote customers can use them. This live check validates one non-sensitive English scenario; broad accuracy and evidence of customer demand remain unproven. No deployment, billing change or automated fallback was performed.

## Earlier Phase 2 checkpoint — 15 October 2026

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
