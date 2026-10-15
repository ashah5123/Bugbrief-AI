# Phase 2 implementation checklist

Existing React / FastAPI / SQLite architecture stays in place. Add an Alembic migration for attachment metadata, clarification history and AI job kind. Store only reviewed screenshot bytes behind the replaceable storage interface. Browser canvas redaction is ordinary image editing, with no local inference.

- [x] Bounded PNG/JPEG uploads, decode/type/pixel validation, metadata stripping, preview and deletion.
- [x] Review and opaque manual redaction before upload; separate consent before external analysis.
- [x] Hosted vision adapter, structured observation validation, shared single-job lock and persistent quotas.
- [x] Explicit screenshot observation references; prevent image-only reproduction steps and expected behaviour claims.
- [x] Stored clarification questions and answers, including source references and correction history.
- [x] Revised report proposals preserving manual edits.
- [x] Backend and browser checks; upgrade/restart persistence; updated setup and manual checklist.
- [x] Live text and screenshot-assisted vision/report CLI checks passed with the user’s configured credentials. One English example was reviewed; broader model accuracy evaluation remains pending. Isolated test fixtures remain separate from live checks.

No voice, duplicate matching, approval/export, authentication or new infrastructure in this phase.
