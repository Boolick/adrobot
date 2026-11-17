# Engineering Checklist (`checklist.md`)

## Phase 0: Repository & Quality Gate Setup

- [x] Root structure (`backend/`, `frontend/`, `docs/`, `AGENTS.md`).
- [x] Latest compatible FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, HTTPX installed.
- [x] Quality gate configured and passing (`ruff check .`, `ruff format --check .`, `pyright`, `pytest`).

## Phase 1: Core Infrastructure & DB Layer (`[MUST-HAVE]`)

- [x] Typed configuration via `pydantic-settings` (`.env` support).
- [x] SQLAlchemy async engine/session + initial Alembic migration (`campaigns` tracking table).
- [x] Custom domain exception hierarchy + FastAPI global exception handlers.
- [x] Campaign repository & SQLite persistence layer tested.

## Phase 1.5: Frontend Baseline & FSD Architecture Setup

- [x] Vite 6 + React 19 + TypeScript + Feature-Sliced Design (FSD) architecture initialized.
- [x] Strict ESLint boundaries configured (forbidding `any`, enforcing FSD layer import boundaries).
- [x] Typed OpenAPI contract sync (`schema.d.ts`) + API client with `/health` check.
- [x] Frontend quality gates passing (`npm run lint`, `npm run typecheck`, `npm run build`).

## Phase 2: Staging DB Schema & Keitaro API Integration (`[MUST-HAVE]`)

- [x] Project documentation (`requirements.md`, `business-rules.md`, `api-contracts.md`, `checklist.md`) updated with confirmed Keitaro API & staging editor specs.
- [x] Local staging ORM models (`CampaignStream`, `StreamOffer`) + repositories (explicit `select()` / `selectinload()`, zero lazy loads) + Alembic migration (`add_streams_and_offers_tables`) verified with upgrade/downgrade roundtrip.
- [x] Typed async `KeitaroClient` & Pydantic v2 schemas (`domains`, `groups`, `traffic_sources`, `offers`, `create_campaign`, `create_stream`, `get_campaign_streams`, `update_stream_offers`) with trailing-slash `base_url` normalization and domain error mapping (`{"error": "..."}`, `406` field dicts, timeouts).
- [x] Unit & repository tests passing (`MockTransport` for `KeitaroClient`, async SQLite tests for stream/offer repositories).

## Phase 3: Feature 1 — Campaign Creator (`[MUST-HAVE]`)

- [x] GEO code parser & validator (ISO-2 codes) and sandbox naming (`^test_[a-zA-Z0-9_-]+$`) / default IDs (`domain_id = 1813`, `group_id = 10332`, `traffic_source_id = 836`, `campaign_prefix = "test_bullo_"`).
- [x] Service orchestration: `POST campaigns` -> 2x `POST streams` (Flow 1: `Geo -> Google`, Flow 2: `Offers`) in Keitaro + persist campaign and initial streams/offers in SQLAlchemy.
- [x] FastAPI router endpoints (`GET /api/v1/dictionaries`, `GET /api/v1/offers`, `GET /api/v1/campaigns`, `GET /api/v1/campaigns/{campaign_id}`, `POST /api/v1/campaigns`) + integration tests with mocked `KeitaroClient` & partial-failure handling.

## Phase 4: Feature 2 — Campaign Stream Editor (`[MUST-HAVE]`)

- [x] Pure weight distribution calculator (`PIN` preservation + even split `//` across unpinned active offers + remainder `%` on last unpinned active offer, sum strictly `100`, `validate_stream_for_push`).
- [x] Staging service logic: `FETCH STREAMS FROM KT` (`has_offers = False` compact streams, resilient `schema == "landings"` / existing flag, missing offers archived as `status = "removed"`), `ADD OFFER`, `REMOVE`, `BRING BACK`, `PIN` (toggle or explicit share), `CANCEL` (delete `is_published == False`, restore `published_share` / `published_status`), `PUSH TO KT` (only `status == "active"` sent to `PUT streams/{id}`).
- [x] FastAPI endpoints (`POST /api/v1/campaigns/{campaign_id}/streams/fetch`, `POST /api/v1/streams/{stream_id}/offers`, `.../remove`, `.../bring-back`, `.../pin`, `.../cancel`, `.../push`) + unit and API integration tests.
- [x] Reliability hardening: `remaining >= len(unpinned)` weight guard + `REMOVE` auto-unpin, per-stream/per-campaign-name locks, snapshot-based `PUSH`, shielded create/push persistence with Keitaro `DELETE campaigns/{id}` compensation, `FETCH` hygiene (draft deletion, duplicate aggregation, inactive offers), campaign-scoped stream upsert, shared lifespan `KeitaroClient`, SQLite `busy_timeout`.

## Phase 5: Frontend & Final Polish (`[MUST-HAVE]`)

- [x] Minimal clean UI in `frontend/` (Create Campaign form with offer autocomplete + Stream Staging Editor with `is_dirty` highlight, `PIN`, `REMOVE`, `BRING BACK`, `CANCEL`, `PUSH TO KT`).
- [x] Production Docker packaging (`backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`, `.env.example`).
- [x] `README.md` with setup, Alembic migration commands, and quality gate instructions.
- [x] Final end-to-end verification against live Keitaro sandbox.
