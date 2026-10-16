# Customer-to-agency checkpoint

Purpose: remove the agency's copy/paste and clarification relay. A customer submits directly, records browser/viewport context with permission, answers genuine hosted follow-up questions, and sends one submission to the agency for review.

- [x] Protect agency endpoints with an access code and signed HttpOnly session.
- [x] Project-scoped intake links, revocation, private per-submission resume links and idempotent draft creation.
- [x] Customer submission, screenshot review, optional hosted follow-up, saved answers and final receipt; saving works when processing is unavailable.
- [x] Embeddable Report a problem button; collect the parent page URL and viewport with clear consent. Standalone forms cannot automatically know the affected page.
- [x] Agency inbox shows submitted customer reports and captured context; manual edits and proposals remain protected.
- [x] Isolation, quota, persistence and browser workflow tests; real hosted check when configured.

Keep one process, SQLite, local storage and hosted inference. No paid infrastructure or messaging integration. The checkpoint runs locally; links are not reachable by remote customers until the app is deployed behind HTTPS. No public deployment is performed here.


Actual live check: an anonymous browser reported “Checkout isn't working” on the demo, received three real hosted questions, saved its answers, received a real revised proposal and sent the submission. The agency inbox then contained the original text, answers, confirmed captured browser/page/viewport and the proposal. Anonymous agency-API access returned 401. This is a non-sensitive test scenario, not proof of broad accuracy or willingness to pay.

The existing report-management, duplicate, voice/video and production-workspace phases remain separate. This checkpoint was reprioritized to validate direct customer collection and reduce the agency's clarification relay.


Role and management update: the root page now asks company/customer; `/workspace` remains authenticated and `/customer` accepts private/project links and lists submissions remembered in that browser. Customers can delete their own submission and company users can delete any report/draft, both through a confirmation dialog. Content and image bytes are erased from the active workspace; minimal quota/idempotency tombstones remain. Alembic `0004` upgrades existing records without removing them. Verification: 110 backend tests, 24 desktop/mobile browser tests and the production build passed.


Customer-account update: `/customer` now offers New customer / Returning customer. Signup creates a persistent customer account; sign-in opens an account-filtered dashboard from any browser. A project invitation connects a project once. Account-owned report and image access requires the owner’s customer session; earlier guest reports can be explicitly saved to an account. Customer sessions do not authorize the company API. Migration `0005` retains existing reports, submissions, links and usage. No email delivery or password reset was added.
