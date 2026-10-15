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

Run exactly one backend worker. The in-process lock is deliberately simple and replaceable with a durable queue later. SQLite and local attachment interfaces can be replaced by PostgreSQL and object storage. Separate image, transcription and embedding protocols are extension seams only; no upload, duplicate, voice, video, auth or integration endpoints in Phase 1.

Reports use evidence quotations with validated exact substrings. That rejects fabricated quotations, not every semantic hallucination; factual correctness still requires human review. A regeneration stores a new AI proposal; existing manual edits stay untouched until the user explicitly applies that proposal. No customer data or keys go into logs.

- [ ] Execute one live generation with the user’s own free-tier credentials (not supplied).
