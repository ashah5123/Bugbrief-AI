# Phase 1 architecture and checklist

Browser (React + TypeScript + Vite + Tailwind) → same-origin /api proxy → FastAPI → SQLAlchemy → SQLite.
FastAPI → ReportGenerator protocol → Gemini HTTPS API. No model or inference runs locally.

- [x] Project creation; feedback capture in English, Hindi or Hinglish.
- [x] Alembic migration; durable drafts and editable structured reports.
- [x] Real API integration; Pydantic validation and evidence quotations.
- [x] Missing-key, timeout, invalid-output, provider failure and quota handling.
- [x] One in-process AI job; persistent daily attempt cap; no automatic retries or fallback.
- [x] Accessible responsive interface; setup and manual test instructions.
- [x] Automated isolated tests; separate opt-in live check.

Run exactly one backend worker. The in-process lock is deliberately simple and replaceable with a durable queue later. SQLite and local attachment interfaces can be replaced by PostgreSQL and object storage. Phase 2 implements the image analysis and local attachment storage protocols. Transcription and embedding protocols remain extension seams. No duplicate, voice, video, company staff roles or external issue-publishing integrations are enabled. Customer accounts are implemented separately from the shared company workspace.

Reports use evidence quotations with validated exact substrings. That rejects fabricated quotations, not every semantic hallucination; factual correctness still requires human review. A regeneration stores a new AI proposal; existing manual edits stay untouched until the user explicitly applies that proposal. No customer data or keys go into logs.

- [x] Execute a real hosted report request and screenshot-assisted vision/report requests with the user’s configured free-tier credentials.


Phase 2 adds an evidence router for reviewed screenshots and append-only clarification answers. Upload validation bounds compressed bytes and decoded pixels and strips metadata before storage. The frontend flattens opaque redaction rectangles into exported pixels before uploading. A separate consented hosted vision request records visible observations and limitations. Report generation receives those observation texts plus original feedback and user answers; image bytes are not resent. Screenshot-derived citations cannot establish reproduction steps or expected behaviour.

`jobs.py` owns the single lock, persistent quota reservations and provider failure handling for both text and vision. Mutations execute without intervening awaits on the single backend event loop after the lock check, preventing report or evidence writes during remote processing. GETs remain available. Screenshot analysis is immutable; evidence changes invalidate proposals, mark reports for review and retain existing manual report content. Clarification corrections append rather than overwrite history.

Before any evidence mutation in an open report, the frontend saves the current manual report edits. Stable references use clarification IDs or attachment ID plus observation index internally; the UI displays readable answer and screenshot numbers. Removed screenshot references are explicitly labelled for review.


## Customer collection checkpoint

Alembic `0003` adds project intake links and per-submission capabilities. The customer namespace returns an explicit minimal snapshot, never agency serialization. Signed agency sessions and a private persistent access code protect existing agency endpoints. Customer drafts are idempotent by project link plus random browser nonce and remain out of the review inbox until final Send. Capability URLs are redacted in backend access logs; sensitive API responses are no-store.

A plain JavaScript launcher uses Shadow DOM and an iframe. The parent sends only its origin/path and viewport after a ready handshake; the iframe checks the sender/window and configured project origin. Direct forms ask for the affected URL. Customer-confirmed browser context is distinguished from unconfirmed submission context; captured context cannot establish reproduction steps or expected behaviour. No event/console/network recorder is added.

Public processing reserves through the existing job service with tighter project/submission caps. Reviewed images are analyzed sequentially, then a real report supplies up to three customer-facing questions. Answers remain append-only. A second request stores a proposed report revision; it never overwrites agency edits. Provider failures preserve the intake and permit manual handoff. Mutations to the active feedback are blocked during its job, while unrelated customers may continue local saves. Refresh can poll an in-flight submission without starting another job.


## Role entry and report deletion

`/` is an explicit company/customer chooser; `/workspace` retains signed agency authentication and `/customer` offers account creation/sign-in and an authenticated customer dashboard; prior guest capabilities remain available for explicit account claims. Direct `/c/` and `/s/` links retain their customer context. A role selection never authorizes an agency API request.

Alembic `0004` adds `Feedback.deleted_at`. A shared deletion service enforces the active-job guard, deletes local image files and all attachment/clarification rows, and erases report, proposal, raw feedback and customer context. A minimal tombstone retains IDs and attempt relationships to preserve global/project quotas and idempotency; all reads/mutations reject deleted records and list queries exclude them. Owner deletion requires agency authentication. Customer deletion accepts only the matching high-entropy submission capability, including after project-link revocation. Retries using an erased draft nonce return 410 instead of recreating its contents. Operator backups are not modified.


## Customer accounts — migration 0005

`CustomerAccount` stores normalized unique email, name and a salted password hash. `CustomerSession` stores only the SHA-256 hash of a random 256-bit cookie token and its seven-day expiry; logout deletes the server row. Password derivation uses scrypt N=32768, r=8, p=3, one of [OWASP’s documented configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). No credential hashing library or email provider was added. Registration requires 12–128 characters, and login errors do not distinguish an unknown email from a wrong password. The local process limits registration to five and login to eight attempts per address/ten minutes. Existing same-origin write checks protect these routes too.

A `CustomerMembership` is established only by a valid project capability. An optional `CustomerSubmission.account_id` assigns ownership when a signed-in customer creates a report; an explicit claim can assign an old guest report using its existing private capability. Claims use a conditional update and cannot take another account’s submission. Public report/image/mutation routes enforce the assigned account even when the private token is known. The authenticated report and project lists filter by the current account. Revoking an invitation prevents new reports while preserving the owner’s access to already-owned reports. Guest submissions retain their earlier revocation behavior.

No email verification, password reset, MFA or company employee accounts are implemented. The email field is a local login identifier and never auto-enrolls a customer or claims reports. Source, tests and screenshots use only non-sensitive sample accounts. All browser tests run against disposable SQLite; no sample account is created in the operator’s database.
