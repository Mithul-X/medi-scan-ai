# MediScan AI

An intelligent medical report analyzer: upload a lab report, scan, or prescription (PDF, image, or text) and get a structured, plain-language breakdown of the findings, with a follow-up chat for questions about the result.

Built for a backend-heavy capstone brief: the backend is the substantial part of this project (multi-provider LLM routing with automatic fallback, PDF/image processing pipeline, caching, bounded session history), and the frontend is a deliberately minimal, text-first interface that consumes it.

No local model inference anywhere. Every analysis call goes to a free hosted API (Gemini, with an OpenRouter fallback chain). Nothing in this project requires the developer's machine to do anything but run a thin FastAPI process and a thin Next.js process — both of which deploy to free hosting tiers.

## Stack

**Backend** — FastAPI (Python), SQLite (via SQLAlchemy async + aiosqlite), PyMuPDF for PDF text extraction, Pillow for image compression, httpx for outbound API calls. Deploys to Render's free tier.

**Frontend** — Next.js (App Router) + TypeScript, no UI framework dependency — hand-written CSS for full control over the typography system. Deploys to Vercel's free tier.

**LLM providers** —
- **Gemini 2.5 Flash** (primary): vision + text, generous free tier. *Gemini 2.0 Flash and 2.0 Flash-Lite are end-of-life as of June 1, 2026 — this project does not use them.*
- **OpenRouter** (fallback, used only if Gemini errors or rate-limits): tries `openrouter/free` (a smart router that auto-selects a capable free model) first, then named free models (`meta-llama/llama-3.3-70b-instruct:free`, `deepseek/deepseek-r1:free`) as further backstops.

Because free-tier model availability and naming change often, all model names live in one place: `backend/app/core/config.py`. Check there first if something needs updating.

## How the backend decides what to do with an upload

1. **PDF** → PyMuPDF extracts text locally (zero API cost). If the PDF is image-only (scanned, no embedded text), it's rejected with a message suggesting the image-upload path instead.
2. **Image** (PNG/JPEG/WebP) → Pillow downscales/recompresses to under ~900KB before it's sent to a vision-capable model. This keeps token usage and request size down.
3. **Plain text** → used as-is.
4. **Long documents** → chunked (~12k characters per chunk), analyzed per-chunk, then merged into one final analysis via a second LLM call.
5. **Duplicate uploads** (same file, same session, identified by MD5 hash) → served from cache, no LLM call at all. Checked in two places: an in-memory LRU cache (fast, but cleared on cold start) and the database (durable, survives restarts).

## Provider fallback / rate-limit handling

`backend/app/services/llm_router.py` is the center of the backend. On every analysis request:

1. Try Gemini. Retry up to 2 times on 429/5xx with backoff.
2. If Gemini still fails (rate limited, key missing, safety-filtered, server error), fall through to OpenRouter's `openrouter/free` router model.
3. If that also fails, fall through to each named OpenRouter free model in order.
4. Only if every provider in the chain fails does the request return a `503` (`llm_providers_exhausted`).

The response always reports which provider actually answered (`provider_used`: `"gemini"` or `"openrouter:<model>"`), shown in the UI under each result.

### About free-tier limits

Gemini 2.5 Flash free tier (subject to change — verify at [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)): roughly 10-15 requests/minute, ~250k tokens/minute, ~1000-1500 requests/day. For a capstone demo with occasional uploads, this is far more than enough headroom. OpenRouter's free models are typically capped around 20 requests/minute and 200/day per the OpenRouter account — again well above demo-level traffic, and only used as a fallback anyway.

## Session history (last 3 + last 3)

There's no login. A UUID is generated in the browser on first visit (`frontend/lib/session.ts`, stored in `localStorage`) and sent with every request. The backend keys a SQLite `sessions` row off that UUID and keeps:
- the last **3 sessions** total (older sessions and their analyses are pruned)
- the last **3 analyses per session**

Pruning happens in plain Python at write-time (`backend/app/services/history.py`), not via database triggers — easy to read, easy to test.

**Known limitation:** Render's free-tier disk does not persist across redeploys (it does persist across restarts within the same deploy). This is fine for a demo/capstone but worth stating explicitly if asked — it's not a bug, it's a free-tier tradeoff.

## Project structure

```
mediscan-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory, CORS, lifespan, exception handlers
│   │   ├── core/                  # config, logging, exceptions
│   │   ├── db/                    # SQLAlchemy async engine + ORM models
│   │   ├── routes/                # analyze, history, health
│   │   ├── services/               # file_processor, llm_router, report_parser, cache, history
│   │   ├── schemas/                # Pydantic request/response models
│   │   └── prompts/                # versioned prompt templates
│   ├── tests/                      # pytest + pytest-asyncio, 19 tests, all mocked (no real API calls)
│   ├── requirements.txt
│   ├── .env.example
│   └── render.yaml
└── frontend/
    ├── app/
    │   ├── layout.tsx              # font loading (Space Grotesk + JetBrains Mono)
    │   ├── page.tsx                # main upload/results page
    │   └── globals.css             # full design system, no Tailwind
    ├── components/                 # FileUpload, AnalysisResult, HistorySidebar, ChatPanel, StatusBadge
    ├── lib/                        # api client, session management, shared types
    ├── package.json
    ├── tsconfig.json
    └── vercel.json
```

## Running locally

**Backend:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY and OPENROUTER_API_KEY
uvicorn app.main:app --reload
```
Runs on `http://localhost:8000`. Check `http://localhost:8000/api/v1/health`.

Run the test suite (no API keys needed — everything is mocked):
```bash
pytest -v
```

**Frontend:**
```bash
cd frontend
npm install
cp .env.local.example .env.local   # defaults to localhost:8000 backend
npm run dev
```
Runs on `http://localhost:3000`.

## Deploying

**Backend → Render:**
1. Push this repo to GitHub.
2. New Web Service on Render, point it at the repo, it should auto-detect `backend/render.yaml`.
3. Set `GEMINI_API_KEY` and `OPENROUTER_API_KEY` in the Render dashboard (marked `sync: false` in render.yaml — they're secrets, not committed).
4. Update `CORS_ORIGINS` once you know your Vercel URL.

**Frontend → Vercel:**
1. Import the repo, set the root directory to `frontend/`.
2. Set `NEXT_PUBLIC_API_BASE_URL` to your Render backend's `/api/v1` URL.
3. Deploy.

Get API keys:
- Gemini: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free, no card)
- OpenRouter: [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) (free, no card)

## Notable design choices (for the project report)

- **No vector DB / embeddings.** History scope is tiny (3 sessions × 3 analyses), so a relational lookup is simpler and cheaper than standing up retrieval infrastructure for no real benefit.
- **httpx directly, no provider SDKs.** Keeps the exact request/response shape for both Gemini and OpenRouter fully visible and auditable in one file (`llm_router.py`) rather than hidden behind SDK abstractions — useful both for debugging free-tier rate limit errors and for explaining the system in a viva/defense.
- **SQLite over Postgres.** Zero external service, zero monthly cost, more than sufficient for the bounded history scope. Documented tradeoff: ephemeral across Render redeploys.
- **Chunk-then-merge for long documents**, rather than truncating. Keeps the analysis grounded in the whole document instead of just the first ~12k characters.
- **MD5 cache at two layers** (in-memory + DB-backed) directly addresses the "don't blow through free-tier token limits" requirement — repeat uploads cost nothing.
