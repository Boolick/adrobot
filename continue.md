# Continue — Phase 2: Keitaro API Integration

## Last action
Initialized `frontend/` application with Vite 6 + React 19 + TypeScript, FSD architecture, OpenAPI type generation, and strict ESLint boundaries (`npm run lint`, `npm run typecheck`, `npm run build` all pass with code 0). Verified backend quality gate (`ruff check`, `ruff format --check`, `pyright`, `pytest`) passes with code 0. Git repository initialized with `.gitignore` updated to track `.agents/` and `AGENTS.md` while ignoring `docs/TA/` and `docs/temp/`.

## Next action
Implement Phase 2 (`backend/src/adrobot/integrations/keitaro/`): build the typed async `KeitaroClient` using HTTPX to fetch Keitaro dictionaries (`offers`, `domains`, `groups`, `traffic_sources`), validate response schemas with Pydantic v2, and write unit tests with mocked Keitaro API responses in `backend/tests/test_keitaro_client.py`.

## Why
Phase 0, Phase 1 (DB & Core), and Phase 1.5 (Frontend skeleton) are complete and tested. The Campaign Creator (Phase 3) requires a working Keitaro client to fetch dictionaries and create campaigns/streams.

## Open threads
- Git repository is initialized on branch `master` with no commits yet; all files are untracked.
- `docs/checklist.md` updated with completed Phase 0, Phase 1, and Phase 1.5 checkboxes.
- Keitaro credentials (`KEITARO_API_URL` and `KEITARO_API_KEY`) need to be present in `.env` for integration testing against live sandbox (mocked tests do not require live credentials).

## Do not
- Do NOT touch `docs/TA/` or `docs/temp/` (they are ignored in `.gitignore`).
- Do NOT log, print, or expose `.env` or `KEITARO_API_KEY` (enforce `pydantic.SecretStr`).
- Do NOT bypass FSD boundaries or use `any` in `frontend/` (strict ESLint will fail).
- Do NOT import DB models or Keitaro HTTP calls directly into routers (maintain `api -> services -> integrations/db -> core`).
