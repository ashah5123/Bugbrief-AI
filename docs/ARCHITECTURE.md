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

`/` is an explicit company/customer chooser; `/workspace` retains database-backed company authentication and `/customer` offers account creation/sign-in and an authenticated customer dashboard; prior guest capabilities remain available for explicit account claims. Direct `/c/` and `/s/` links retain their customer context. A role selection never authorizes an agency API request.

Alembic `0004` adds `Feedback.deleted_at`. A shared deletion service enforces the active-job guard, deletes local image files and all attachment/clarification rows, and erases report, proposal, raw feedback and customer context. A minimal tombstone retains IDs and attempt relationships to preserve global/project quotas and idempotency; all reads/mutations reject deleted records and list queries exclude them. Owner deletion requires agency authentication. Customer deletion accepts only the matching high-entropy submission capability, including after project-link revocation. Retries using an erased draft nonce return 410 instead of recreating its contents. Operator backups are not modified.


## Customer accounts — migration 0005

`CustomerAccount` stores normalized unique email, name and a salted password hash. `CustomerSession` stores only the SHA-256 hash of a random 256-bit cookie token and its seven-day expiry; logout deletes the server row. Password derivation uses scrypt N=32768, r=8, p=3, one of [OWASP’s documented configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). No credential hashing library or email provider was added. Registration requires 12–128 characters, and login errors do not distinguish an unknown email from a wrong password. The local process limits registration to five and login to eight attempts per address/ten minutes. Existing same-origin write checks protect these routes too.

A `CustomerMembership` is established only by a valid project capability. An optional `CustomerSubmission.account_id` assigns ownership when a signed-in customer creates a report; an explicit claim can assign an old guest report using its existing private capability. Claims use a conditional update and cannot take another account’s submission. Public report/image/mutation routes enforce the assigned account even when the private token is known. The authenticated report and project lists filter by the current account. Revoking an invitation prevents new reports while preserving the owner’s access to already-owned reports. Guest submissions retain their earlier revocation behavior.

Email verification and password reset are implemented in migration 0008 below. MFA is not implemented. Company employee accounts are implemented separately below. The email field is a local login identifier and never auto-enrolls a customer or claims reports. Source, tests and screenshots use only non-sensitive sample accounts. All browser tests run against disposable SQLite; no sample account is created in the operator’s database.


## Company employees — migration 0006

`EmployeeAccount` and `EmployeeSession` keep company identities separate from customer tables/cookies. Signup initially required the operator/workspace code; migration 0008 restricts that code to owner-authorized or first-employee setup, and otherwise requires an individual invitation. Employee credentials reuse the validated email/name schemas and scrypt password helper. Login uses the same generic failure response and separate `employee-login`/`employee-register` attempt counters. No project membership or customer session can authorize employee signup.

Agency authorization accepts an active employee session in addition to existing operator credentials. Middleware reads employee sessions through `app.state.session_factory`, configured with the same database as route dependencies; tests replace both with their disposable factory. Twelve-hour sessions store token hashes only. Signing into an employee account clears the old owner-cookie fallback; logout removes the current server session and clears both company cookies. The customer session remains independent. Named identity reaches the workspace via React context, not browser-local profile storage.

The company entry link uses `/workspace?employee=choose`, including for an already signed-in employee. `/workspace/signup` and `/workspace/signin` show the appropriate form, and successful authentication opens `/workspace`. There is one company per installation; employees have project/report permissions only for assigned projects after migration 0009. Migration 0008 adds owner-only team administration; ordinary employees retain project/report management within assigned projects.


## Assignment and issue progress — migration 0007

`IssueProgress` stores a per-feedback status, optional employee FK, independent version and update timestamp. `IssueEvent` stores customer-visible update text and history; no internal-only note field was added. Existing feedback reads as New with a derived Report received event without a GET mutating the database. The first real update creates the state and initial event. This preserves earlier report/evidence `Feedback.status` and `Feedback.version` semantics.

Only company-authorized requests can read the employee directory or mutate issue progress. Assignments must reference a real employee. Allowed transitions prevent skipping straight to resolution, and In progress / Ready to retest / Resolved require an owner. Needs information requires an explanatory public update. Updates use compare-and-swap on the progress version; stale requests and concurrent first inserts fail with 409. No inference call or report/evidence mutation is involved. Customer drafts cannot be assigned before final submission.

Public/customer snapshots expose only the status, assignee display name, timestamps and public event text. Employee IDs, emails, progress versions and internal report/proposal data are excluded. Customer account lists include a small progress summary; individual submission access retains existing guest/account ownership enforcement. The latest 50 events are returned, while the UI presents newest first. Deleting a report erases progress and history alongside its evidence.

The workspace has assignee/status filters and an unresolved count. Public tracking and the signed-in customer dashboard poll every 15 seconds and on focus. Form saves keep unsaved report edits intact; a stale workflow form retains its note and asks to reload progress. This remains a single-company local SQLite application. Migration 0008 adds customer retests and account security emails; migration 0009 adds general report notifications and project isolation. Automatic source-code modifications remain outside this checkpoint.


## Conversations, retests and account management — migration 0008

`ReportMessage` stores public replies and private team notes independently of report content and progress events. Public queries apply the visibility predicate before ordering/limiting, return no internal fields, and reuse submission ownership and sent-stage enforcement. Customer writers cannot choose internal visibility. Company writers derive their author name from the active employee, or the workspace owner. Notes are never included in report-generation evidence. Both message types are erased by report deletion.

Customer retests are permitted only for the current Ready to retest state. A public `retest_version` is exposed only while ready; a conditional update checks that version and status atomically before resolving or reopening. Still happening requires an explanation. Each accepted decision creates a public history event, leaves report/evidence versions untouched, and makes retries/stale confirmations return 409.

`AccountAction` stores SHA-256 hashes of random security tokens, normalized email, customer/employee scope, purpose, expiry and consumption timestamp. Reset, verification and employee invitation purposes cannot substitute for each other. Consume uses a conditional update in the same transaction as the protected change. New links invalidate older links of the same scope/purpose/email. Reset revokes all sessions in that role; verification records a timestamp without granting project membership or employee access. Accounts can use their existing role while verification is pending. Generic recovery acknowledgements do not reveal whether an email exists. Throttles remain process-local.

`MailMessage` is a development outbox with owner-only access. Local mode retains the email body, including sensitive action links, in the ignored development database. Production SMTP uses mandatory STARTTLS and retains only status/recipient/subject metadata after attempted delivery; local preview links are not exposed in SMTP mode. No SMTP credentials or external delivery are needed for the local workflow. Links use the configured frontend base URL and put tokens in fragments. Recover/verify endpoints never echo a token; the owner-only local outbox intentionally exposes test email contents.

Existing employee rows migrate as active, with unverified email status. `disabled_at` blocks employee session lookup and login; access removal also deletes all employee sessions, consumes unused security actions and unassigns owned work while recording a public assignment event. Restoring access requires owner authorization and a new login. Invitation issuance, revocation, removal/restoration and outbox inspection require the owner cookie or operator key, not an ordinary employee cookie. The shared owner code cannot register additional employees after initial setup without an owner-authorized request. One-use invitations are email-bound and last seven days. Migration 0008 preserves existing accounts, credentials, projects and reports.


## Project access and notifications — migration 0009

`EmployeeProject` grants employee membership. Company lists filter by membership, and the API middleware checks the project of every direct `/api/projects/{id}` and `/api/feedback/{id}` request, including nested screenshot, conversation, progress and generation routes. Feedback creation/moves also validate the destination project. Owner credentials bypass project restrictions but remain required for membership management and collection mode changes. New project creators receive membership. The employee directory is restricted to colleagues on accessible projects, and progress assignment validates project membership independently of the caller’s own access.

`Project.customer_access` defaults to link-based collection for existing deployments. Members-only mode requires a signed-in customer with an active `CustomerMembership` before form configuration, submission creation or receipt access. `CustomerMembership.revoked_at` preserves an explicit denial: old links/claims cannot silently restore membership. Public submission authorization enforces both project permission and existing individual ownership, including evidence, replies and retests. Customer lists omit revoked projects/reports. Customer membership grants never expose another customer’s submissions. Public guest capabilities continue in link-based mode; members-only mode is necessary to restrict collection to named accounts. The owner can restore membership explicitly.

`Notification` is addressed to an employee/customer account or the installation owner, stores a feedback FK and a generic event title, and commits in the same transaction as its event. Private-note events target company members only; customer replies/retest results target current company project members, and company replies/progress target only the reporting customer. The actor is excluded. Repeat submission/no-op progress requests do not create duplicate alerts. Every list, count, read operation and email delivery checks current access. Counts use the complete filtered query; display uses the latest 50 entries. Reading one report or all notifications uses separate authenticated POSTs. Notification state never changes report/evidence/progress versions.

`NotificationPreference` stores opt-in email settings per role/account. Email addresses come from the authenticated account. Local mode creates owner-visible test outbox entries. SMTP mode requires verified email and queues durable pending outbox rows linked to notification IDs. Background delivery runs after commit and on a periodic/startup worker; a process lock prevents concurrent send loops. It rechecks membership and preferences, cancels inaccessible deliveries, and records SMTP failure without rolling back the report action. Failure statuses are visible in the owner outbox; failed deliveries require a fresh event or manual operational recovery rather than automatic repeated sends. This continues to require a single backend process. Email contents omit report/reply/private-note text. Report deletion erases notifications and linked outbox rows.

Migration 0009 adds membership, notification and preference tables, preserves existing mail rows during the SQLite table rebuild, and grants existing active employees their prior projects once. Subsequent employee registrations do not get those grants. Explicit owner review is available immediately in the project access screen. Membership removal unassigns affected issues and increments workflow versions so stale saves fail. The UI drops inaccessible selected reports on refresh, and customer tracking clears on authorization failures.


## Security audit and owner session revocation — migration 0010

`OwnerSession` contains a SHA-256 token hash, current owner credential hash and expiry. Owner access accepts the operator header or a live random cookie token; legacy signed cookies are not accepted. Reauthentication deletes the incoming owner session and current employee session. Employee authentication similarly deletes the incoming owner session. Logout revokes both company session types, and current actor reporting prioritizes valid owner access consistently with authorization. Credential rotation invalidates stored owner sessions by fingerprint. Independent-process tests verify session persistence and copied-token denial after logout.

The company API guard rejects unsent `CustomerSubmission` rows before every direct feedback/evidence operation. Public customer routes keep their existing ownership, project and stage checks. Legacy manual report content remains preserved during customer processing, without permitting new company edits before submission. Manual report project moves release an assignee who is not an active destination member. Customer membership restoration updates a stale membership link to an existing active link while retaining deliberately closed collection when no active link exists.

Browser persistence access is wrapped to tolerate blocked/quota-limited storage. Separate company/customer identity markers prevent account switches from restoring another actor’s draft. Authentication is checked before cached company draft rendering; inaccessible report caches are pruned. Focus/session checks reload stale account identities, including unsent customer forms and account dashboards. Guest capability recovery remains available across guest-to-account claims. This is a shared-browser privacy measure, not protection against someone who controls the browser or an active session.

Notification sending enumerates pending IDs, then opens a new database session per message. Each iteration refreshes current recipient membership, account status and preferences and tolerates deletion of another queued row during an earlier send. A transient SQLAlchemy error is contained by the worker wrapper so it cannot kill the periodic loop or surface as a failed committed reply. SMTP remains optional; local mode sends no mail.


## Company triage — migration 0011

`IssueProgress.priority` defaults to `normal`; optional `due_date` stores a validated ISO calendar date. The company-only `/api/feedback/{id}/triage` route uses the existing workflow version for compare-and-swap updates, preserves status/assignment and report/evidence versions, and shares middleware project/deleted/unsent-report guards. Public workflow serializers omit priority, deadline and waiting indicators. Triage changes create no customer notifications or public planning events.

Company snapshots derive `waiting_since` from the latest submitted report, customer public reply or failed retest versus the latest company public reply or public status/progress update. Private notes and assignment without a public note do not clear it; resolved reports do not wait. Company customer metadata includes an account ID (or guest submission ID) for identity-based filtering; display-name equality never establishes ownership.

The browser applies composable filters only to the server-authorized feedback list. Deadline comparisons use local `YYYY-MM-DD` dates; formatting avoids UTC date shifts. Attention sorting puts unresolved reports first, then overdue reports, priority, waiting customers, due date and recency. Summary counts cover the full authorized list and open the matching full feedback queue. Open report workflow snapshots follow the existing polling refresh without overwriting report text. Separate triage/progress forms protect unsaved edits and expose explicit conflict reloads.


## Personal work and customer guidance — migration 0012

The employee `My work` view derives personal queues from the server-authorized feedback list and the current employee ID. Resolved and differently assigned items are excluded; project visibility remains enforced by the existing middleware. Owners retain the overview. Personal browser draft recovery is an explicit action and reuses the existing account-isolated storage and identity checks.

`NextStep` supplies role-specific guidance from current workflow state, assignment and company-only reply-wait metadata; it performs no writes and does not advance workflow automatically. Public/customer rendering uses only the minimal customer workflow snapshot. The authenticated report list adds a bounded 160-character summary of the customer's original text, never the company's internal report, proposal or notes. Customer portal attention cards cover unfinished drafts, requests for information and fixes awaiting retest. An initial account-data loading state avoids displaying incorrect first-project onboarding. Closed intake links hide new-report actions while retaining existing account-owned report access.

`Project.team_name` is an optional customer-facing display name, defaulting to an empty string for existing rows. The existing project write authorization protects it; omission on older project PUT requests preserves its value. Authorized customer project listings, capability-protected intake configuration and report snapshots expose this display name. The UI uses a neutral project-team fallback rather than invent a company name. The sharing dialog re-reads current settings and refreshes the workspace when closed.

Browser regression identities for the experience checks are seeded only in the disposable test database. They use real hashed sessions while avoiding extra signup/login attempts against the unchanged abuse limits. The independent audit employee session remains attached to the audit identity.
