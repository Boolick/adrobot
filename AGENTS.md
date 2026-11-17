# Adrobot Project Agent Guidelines (`AGENTS.md`)

## Project Context & Personas
- Read and follow `.agents/keitaro-backend-expert.md` for all backend work.
- Apply the project skills in `.agents/skills/`:
  - `backend-architect`
  - `python-fastapi`
  - `async-python-patterns`
  - `api-design-principles`
  - `backend-security-coder`
- Align every change with the specifications in `docs/`:
  - `docs/requirements.md`
  - `docs/architecture.md`
  - `docs/business-rules.md`
  - `docs/api-contracts.md`
  - `docs/checklist.md`

## Architectural Boundaries
Maintain strict one-way dependencies inside `backend/src/adrobot/`:
- `api` -> `services`, `core` (no direct DB queries or Keitaro HTTP calls in routers)
- `services` -> `integrations`, `db`, `core`
- `integrations` -> `core`
- `db` -> `core`
- `core` -> standard library & third-party utilities only

## Security Rules
- Never log, print, commit, or expose `.env` contents or `KEITARO_API_KEY`.
- Always store secrets with `pydantic.SecretStr` and validate external inputs at API boundaries.
- Never silently swallow errors or leave external API writes and local DB commits out of sync without explicit error logging/compensation.

## Iterative Workflow (Mandatory for Every Task)
For every next task, follow this 5-step loop strictly:
1. **Propose Design First:** Read the relevant `docs/` specifications and propose a concise architectural/implementation design (contracts, schemas, DB changes, edge cases, verification plan).
2. **Wait for Approval:** Do not start writing feature code until the user approves the proposed design.
3. **Implement One Small Vertical Slice:** Build one focused, end-to-end testable slice at a time with strict Pydantic v2 types and async SQLAlchemy 2.0 / HTTPX patterns.
4. **Run the Quality Gate:** From `backend/`, run and verify exit code `0` for all four checks:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run pyright`
   - `uv run pytest`
5. **Explain Non-Trivial Constructs:** Clearly explain any non-trivial Python, FastAPI, Pydantic v2, Alembic, or async SQLAlchemy constructs introduced in the slice.
