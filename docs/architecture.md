# Architecture (`architecture.md`)

## 1. High-Level System Overview
Adrobot is a modular monolith backend (FastAPI) acting as an orchestration and validation layer between a web UI and the external **Keitaro Admin API**, backed by a local relational database (SQLite via `aiosqlite` for portability, easily switchable to PostgreSQL).

## 2. Layered Architecture & Dependency Rules
Enforced statically via `import-linter`:
1. **`api` Layer (`src/adrobot/api/`)**:
   - **Responsibility:** HTTP routing, request/response serialization, Pydantic DTO validation, mapping domain exceptions to HTTP status codes.
   - **Allowed imports:** `services`, `core`.
2. **`services` Layer (`src/adrobot/services/`)**:
   - **Responsibility:** Business logic, stream graph construction, offer share calculation/validation, orchestration between Keitaro API and local DB transactions.
   - **Allowed imports:** `integrations`, `db`, `core`.
3. **`integrations` Layer (`src/adrobot/integrations/`)**:
   - **Responsibility:** HTTP adapter (`httpx.AsyncClient`) for Keitaro Admin API, timeout/retry handling, translating raw Keitaro JSON into typed internal schemas.
   - **Allowed imports:** `core`.
4. **`db` Layer (`src/adrobot/db/`)**:
   - **Responsibility:** SQLAlchemy 2.0 ORM models, async session management, repository methods for local persistence.
   - **Allowed imports:** `core`.
5. **`core` Layer (`src/adrobot/core/`)**:
   - **Responsibility:** Application settings (`pydantic-settings`), custom domain exceptions, structured logging.
   - **Allowed imports:** Standard library & third-party utilities only.

## 3. Consistency & Partial Failure Strategy
- Keitaro is an external HTTP system without distributed 2PC transactions.
- **Create Campaign Flow:** Call Keitaro API first -> if successful, commit campaign metadata to local DB. If local DB commit fails after Keitaro succeeds, log critical compensating alert (or attempt cleanup/idempotency tracking) rather than silently swallowing the state mismatch.
- **Edit Offers Flow:** Validate invariants (e.g., at least 1 offer remains, `sum(shares) == 100`) in `services` *before* issuing `PUT/POST` requests to Keitaro.