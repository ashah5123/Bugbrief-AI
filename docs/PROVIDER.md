# Hosted API selection

Verified on **15 October 2026** against official Google documentation. These findings describe the public offering, not a guarantee that a particular account has quota.

Selected provider: **Gemini Developer API**, model **`gemini-3.5-flash-lite`**, direct HTTPS integration. No local model, SDK orchestration framework, credit card, billing account, paid fallback or infrastructure purchase is needed by this application.

- [Pricing](https://ai.google.dev/gemini-api/docs/pricing): selected model has free input and output allowances for standard API requests. Text, image, video and audio input are listed; only text is enabled in Phase 1. Embeddings and transcription remain unimplemented.
- [Billing](https://ai.google.dev/gemini-api/docs/billing): new accounts start in the Free Tier. Upgrading requires explicitly linking billing and adding prepaid credit. Create an API key in a **Free Tier project without a billing account**. Do not select “Set up billing”, activate a trial or supply payment details. Chatbot subscriptions are unrelated to this API allowance.
- [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits): RPM, TPM and RPD limits vary by model/project and are shown in AI Studio. Public fixed numbers are not guaranteed. Check your active quota there; a zero quota is a blocker, not a reason to enable billing. Provider daily quotas reset at midnight Pacific; our conservative local cap resets at midnight UTC and may therefore remain paused past a provider reset or require another retry after its own reset.
- [Data terms](https://ai.google.dev/gemini-api/terms): unpaid input and output may be used for product improvement and reviewed by humans. Google directs users not to submit sensitive, confidential or personal information. For this checkpoint, use only non-sensitive demo feedback. Regional exceptions exist; review the terms for your account.
- [Structured output](https://ai.google.dev/gemini-api/docs/structured-output): JSON schema output is supported. Pydantic validates again on the backend; each evidence quote is checked against the submitted source. Structured output does not guarantee factual correctness.
- [API key setup](https://ai.google.dev/gemini-api/docs/api-key) and [available regions](https://ai.google.dev/gemini-api/available-regions): account eligibility and regional availability must be checked by the person creating the key.

The app cannot determine whether an arbitrary API key belongs to a billed project. `FREE_TIER_CONFIRMED=true` is an explicit operator assertion, not a billing API check. Keep billing disabled in the actual provider console. Local request counters are not a provider-side billing guarantee.

Application controls: 8,000-character feedback, maximum 32 KiB JSON bodies, 5,000 output tokens, one in-process job, 45-second HTTP timeout (configurable up to 90 seconds), 20 daily attempts by default (configurable from 1–100), **zero automatic retries**. Failed external attempts count. A 429 pauses AI until the next UTC day, persistently across restarts. Drafts and edits remain available. No tools, grounding, search, cached storage or paid features are requested.

Live verification: **not run; no credentials supplied**. `scripts/live_check.py` is opt-in and calls the running application's normal generation endpoint, enforcing the same caps. A successful HTTP transport test with a test double is not a live integration check.
