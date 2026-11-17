# Requirements (`requirements.md`)

> **Requirement Status Tags:**
> - `[CONFIRMED-TZ]` — Explicitly stated in the task description, screenshots, or video walkthrough (`jNloscEWCjA`).
> - `[CONFIRMED-KEITARO]` — Verified against Keitaro Admin API documentation and live sandbox.
> - `[DERIVED-LOGIC]` — Architectural/engineering requirement derived from system behavior.

## 1. Functional Requirements: Campaign Creator ("Создаватор")
- **Input Parameters:**
  - Campaign name (`name`) — in sandbox environments, campaign names must start with `test_<surname>_` (e.g., `test_bullo_campaign1`) `[CONFIRMED-TZ]`
  - Optional URL `alias` `[CONFIRMED-KEITARO]`
  - Country GEO code(s) (`geo`, e.g., `AU`, `MX,AU,RO`) `[CONFIRMED-TZ]`
  - Keitaro Offer ID (`offer_id`, UI supports search/autocomplete over offers via `GET offers` filtered by ID or name case-insensitively) `[CONFIRMED-TZ]`
  - Optional metadata IDs (`domain_id`, `group_id`, `traffic_source_id`) fetched via Keitaro dictionaries, defaulting to sandbox IDs:
    - `domain_id = 1813` (`kylovoa.com`) `[CONFIRMED-KEITARO]`
    - `group_id = 10332` (`FORTESTS`) `[CONFIRMED-KEITARO]`
    - `traffic_source_id = 836` (`FORTESTS`) `[CONFIRMED-KEITARO]`
- **Target Keitaro Campaign & Stream Creation Sequence (`POST campaigns` -> 2x `POST streams`):**
  - **Step 1 (`POST campaigns`):** Create campaign with `{"name", "alias", "type": "position", "state": "active", "cost_type": "CPC", "domain_id", "group_id", "traffic_source_id"}` `[CONFIRMED-KEITARO]`
  - **Step 2 (`POST streams` — Flow 1, GEO Filter -> Google):** Create regular stream (`position: 1`, `type: "regular"`, `name: "Geo -> Google"`, `state: "active"`, `schema: "redirect"`, `action_type: "http"`, `action_payload: "https://google.com/"`, `filters: [{"name": "country", "mode": "accept", "payload": ["AU", ...]}]`) `[CONFIRMED-KEITARO]`
  - **Step 3 (`POST streams` — Flow 2, Default Offers):** Create default offer stream (`position: 2`, `type: "default"`, `name: "Offers"`, `state: "active"`, `schema: "landings"`, `action_type: "http"`, `offers: [{"offer_id": <id>, "share": 100, "state": "active"}]`) `[CONFIRMED-KEITARO]`

## 2. Functional Requirements: Campaign Editor ("Редактор")
- **Staging Layer Persistence:**
  - Local SQLite stores `campaign_streams` and `stream_offers` as a staging layer (`is_dirty` drives the yellow highlight indicator in UI) `[CONFIRMED-TZ]`
  - Streams without offers (`offers == []`, e.g., Flow 1) are stored with `has_offers = False` and rendered as compact stream headers without parsing filters or redirects `[CONFIRMED-TZ]`
- **Core Capabilities & State Transitions:**
  - **`FETCH STREAMS FROM KT`:** Syncs streams from `GET campaigns/{id}/streams`. Offers previously stored locally in a stream that are missing in Keitaro are NOT deleted; they transition to `status = "removed"`, `share = 0`, and remain available for `BRING BACK` `[CONFIRMED-TZ]`
  - **`ADD OFFER` / `BRING BACK`:** Add a new offer (`is_published = False`, `status = "active"`) or reactivate a locally archived (`status = "removed"`) offer, marking the stream `is_dirty = True` and recalculating shares `[CONFIRMED-TZ]`
  - **`REMOVE`:** Sets local `status = "removed"`, `share = 0`, `is_pinned = False`, and marks stream `is_dirty = True`. On `PUSH TO KT`, only `status == "active"` offers are sent to `PUT streams/{id}`; removed offers stay archived locally for `BRING BACK` `[CONFIRMED-TZ]`
  - **`CANCEL`:** Deletes local `stream_offers` where `is_published == False` (newly added, never pushed) and restores `is_published == True` offers to `published_share` and `published_status`, resetting `is_dirty = False` `[CONFIRMED-TZ]`
  - **`PUSH TO KT`:** Validates active offers and sends only `status == "active"` offers to `PUT streams/{id}`, updating `is_published = True`, `published_share`, `published_status`, and resetting `is_dirty = False` `[CONFIRMED-TZ]`
- **PIN & Weight Distribution Rules:**
  - Offer traffic shares are integers summing strictly to `100` `[CONFIRMED-TZ]`
  - Pinned active offers keep their assigned `share`; remaining `100 - sum(pinned_shares)` is divided evenly (`//`) across unpinned active offers, with the remainder (`%`) added to the last unpinned active offer (e.g., `33, 33, 34`) `[CONFIRMED-TZ]`
- **Campaign Selection Scope:**
  - Campaigns tracked in local DB (`campaigns` table) are listed and managed in the editor; their streams and offers are synced from Keitaro into `campaign_streams` and `stream_offers` `[CONFIRMED-TZ]`

## 3. Technical & Non-Functional Requirements
- **Backend Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Alembic migrations, Pydantic v2, HTTPX `[CONFIRMED-TZ]`
- **Frontend Stack:** React 19 + TypeScript + Vite 6 (Feature-Sliced Design) `[CONFIRMED-TZ]`
- **External Integration:** Keitaro Admin API (`/admin_api/v1/`) authenticated via `Api-Key` header (`pydantic.SecretStr`, never logged) `[CONFIRMED-TZ]`
- **Local Persistence Role:** Store tracked campaigns (`campaigns`) and stream/offer staging state (`campaign_streams`, `stream_offers`) in SQLAlchemy-managed SQLite/PostgreSQL DB `[DERIVED-LOGIC]`
- **Deliverable:** GitHub repository with a clear `README.md` covering migrations and local startup `[CONFIRMED-TZ]`
