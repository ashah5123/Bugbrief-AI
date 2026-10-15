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

Run exactly one backend worker. The in-process lock is deliberately simple and replaceable with a durable queue later. SQLite and local attachment interfaces can be replaced by PostgreSQL and object storage. Phase 2 implements the image analysis and local attachment storage protocols. Transcription and embedding protocols remain extension seams. No duplicate, voice, video, authentication or integration endpoints are enabled.

Reports use evidence quotations with validated exact substrings. That rejects fabricated quotations, not every semantic hallucination; factual correctness still requires human review. A regeneration stores a new AI proposal; existing manual edits stay untouched until the user explicitly applies that proposal. No customer data or keys go into logs.

- [x] Execute a real hosted report request and screenshot-assisted vision/report requests with the user’s configured free-tier credentials.


Phase 2 adds an evidence router for reviewed screenshots and append-only clarification answers. Upload validation bounds compressed bytes and decoded pixels and strips metadata before storage. The frontend flattens opaque redaction rectangles into exported pixels before uploading. A separate consented hosted vision request records visible observations and limitations. Report generation receives those observation texts plus original feedback and user answers; image bytes are not resent. Screenshot-derived citations cannot establish reproduction steps or expected behaviour.

`jobs.py` owns the single lock, persistent quota reservations and provider failure handling for both text and vision. Mutations execute without intervening awaits on the single backend event loop after the lock check, preventing report or evidence writes during remote processing. GETs remain available. Screenshot analysis is immutable; evidence changes invalidate proposals, mark reports for review and retain existing manual report content. Clarification corrections append rather than overwrite history.

Before any evidence mutation in an open report, the frontend saves the current manual report edits. Stable references use clarification IDs or attachment ID plus observation index internally; the UI displays readable answer and screenshot numbers. Removed screenshot references are explicitly labelled for review.
