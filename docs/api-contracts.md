# API Contracts (`api-contracts.md`)

## 1. Internal Backend REST API (FastAPI -> Frontend)

- `GET /health` -> `200 OK` `{"status": "ok"}`
- `GET /api/v1/dictionaries` -> `200 OK` `{domains, groups, traffic_sources, defaults: {domain_id: 1813, group_id: 10332, traffic_source_id: 836, campaign_prefix: "test_bullo_"}}`
- `GET /api/v1/offers?q=...` -> `200 OK` `list[{id, name, group_id, state, payout_value, payout_currency}]` (case-insensitive ID/name filter)
- `GET /api/v1/campaigns` -> `200 OK` `list[CampaignSummaryResponse]` ordered by `created_at DESC, id DESC`
- `POST /api/v1/campaigns`
  - **Request:** `{"name": str (^test_[a-zA-Z0-9_-]+$), "alias": str | None, "geo": list[str] | str = ["AU", "MX"], "initial_offer_id": int, "domain_id": int | None, "group_id": int | None, "traffic_source_id": int | None}`
  - **Response (`201 Created`):** `CampaignDetailResponse` with ordered streams (`position ASC`) and initial staged offer (`share = 100`).
- `GET /api/v1/campaigns/{campaign_id}` -> `200 OK` `CampaignDetailResponse` (streams ordered by `position ASC, id ASC`; offers ordered by `status ASC, id ASC`; each stream includes `can_push: bool` and `validation_error: str | None`).
- `POST /api/v1/campaigns/{campaign_id}/streams/fetch` -> `200 OK` `CampaignDetailResponse` (syncs streams via `FETCH STREAMS FROM KT`; Flow 2 preserves `has_offers = True` via `schema == "landings"` or prior `has_offers`; missing KT offers transition to `status = "removed"` (unpublished local drafts missing in KT are deleted; duplicate KT offers are summed; non-active/`share <= 0` KT offers become `removed`)).
- `POST /api/v1/streams/{stream_id}/offers` -> Request `{"offer_id": int, "offer_name": str}` -> `200 OK` `StreamResponse`
- `POST /api/v1/streams/{stream_id}/offers/{offer_id}/remove` -> `200 OK` `StreamResponse`
- `POST /api/v1/streams/{stream_id}/offers/{offer_id}/bring-back` -> `200 OK` `StreamResponse`
- `POST /api/v1/streams/{stream_id}/offers/{offer_id}/pin` -> Optional request `{"share": int | None}` -> `200 OK` `StreamResponse` (`share is None` toggles `is_pinned`; `1 <= share <= 100` sets `is_pinned = True` and `share`)
- `POST /api/v1/streams/{stream_id}/cancel` -> `200 OK` `StreamResponse`
- `POST /api/v1/streams/{stream_id}/push` -> `200 OK` `StreamResponse`
- **Error Envelope (`ErrorResponse`):** `{"error": {"code": str, "message": str, "details": dict[str, str] | None}}` mapped to `404` (`NotFoundError` / `ResourceNotFoundError`), `409` (`ConflictError` / `ResourceConflictError`), `422` (`DomainValidationError` / `RequestValidationError`), `502` (`ExternalServiceError`), `504` (`ExternalServiceTimeoutError`).

## 2. External Keitaro Admin API Contracts (`/admin_api/v1/`)
> **Status:** `[CONFIRMED-KEITARO]` — Verified against Keitaro Admin API specification and sandbox defaults (`domain_id = 1813`, `group_id = 10332`, `traffic_source_id = 836`).

- **Base URL & Relative Path Rule:** `KeitaroClient` normalizes `base_url` to always end with `/` (e.g. `https://<host>/admin_api/v1/`) and executes all HTTP calls using relative paths **without** a leading `/` so `httpx.AsyncClient` preserves the `/admin_api/v1` path prefix.
- **Auth Header:** `Api-Key: <KEITARO_API_KEY>` (injected from `pydantic.SecretStr`, never logged). `[CONFIRMED-TZ]`

### Dictionary & Search Endpoints
- `GET domains` -> `list[{id, name, state?, is_ssl?, default_campaign_id?}]`
- `GET groups?type=campaigns` -> `list[{id, name, position?, type?}]`
- `GET traffic_sources` -> `list[{id, name, state?}]`
- `GET offers` -> `list[{id, name, group_id?, state?, payout_value?, payout_currency?}]` (filtered client-side by ID or name case-insensitively when `query` is provided)

### Campaign & Stream Endpoints
- `POST campaigns`
  - **Request:**
    ```json
    {
      "name": "test_bullo_campaign1",
      "alias": "test-bullo-campaign1",
      "type": "position",
      "state": "active",
      "cost_type": "CPC",
      "domain_id": 1813,
      "group_id": 10332,
      "traffic_source_id": 836
    }
    ```
  - **Response (`200 OK`):** `{id, name, alias, type, state, domain_id, group_id, traffic_source_id, ...}`
- `POST streams` (Flow 1 — GEO Filter -> Google)
  - **Request:**
    ```json
    {
      "campaign_id": 101,
      "type": "regular",
      "name": "Geo -> Google",
      "position": 1,
      "state": "active",
      "schema": "redirect",
      "action_type": "http",
      "action_payload": "https://google.com/",
      "filters": [
        {
          "name": "country",
          "mode": "accept",
          "payload": ["AU"]
        }
      ]
    }
    ```
- `POST streams` (Flow 2 — Default Offers)
  - **Request:**
    ```json
    {
      "campaign_id": 101,
      "type": "default",
      "name": "Offers",
      "position": 2,
      "state": "active",
      "schema": "landings",
      "action_type": "http",
      "offers": [
        {
          "offer_id": 55,
          "share": 100,
          "state": "active"
        }
      ]
    }
    ```
- `GET campaigns/{id}/streams` -> `list[{id, campaign_id, type, name, position, state, schema, action_type, action_payload?, offers: list[{offer_id, share, state}]}]`
  - Note: Streams with `offers == []` (e.g., Flow 1) are persisted locally with `has_offers = False` without parsing filters/redirects.
- `PUT streams/{id}`
  - **Request:**
    ```json
    {
      "offers": [
        {"offer_id": 55, "share": 50, "state": "active"},
        {"offer_id": 77, "share": 50, "state": "active"}
      ]
    }
    ```
  - **Response (`200 OK`):** Updated stream object `{id, campaign_id, name, position, offers, ...}`.

### Error & Timeout Handling
- Request timeouts (`httpx.TimeoutException`) map to `ExternalServiceTimeoutError` (`504`).
- Transport failures (`httpx.RequestError`) and HTTP `4xx`/`5xx` responses map to `ExternalServiceError` (`502`), parsing both `{"error": "..."}` payloads and Keitaro `406` field-validation dictionary payloads (e.g., `{"name": ["Name has already been taken."]}` or `{"offers": "..."}`).
