# Business Rules (`business-rules.md`)

## 1. Campaign Creation Invariants
- **BR-1.1 (Two-Stream Structure & Creation Sequence):** Every campaign created by Adrobot executes `POST campaigns` followed by two `POST streams` calls ordered by position:
  - Campaign (`POST campaigns`): `type = "position"`, `state = "active"`, `cost_type = "CPC"`, bound to `domain_id`, `group_id`, `traffic_source_id`. `[CONFIRMED-KEITARO]`
  - Position 1 (`Flow 1`, `POST streams`): `type = "regular"`, `name = "Geo -> Google"`, `position = 1`, `state = "active"`, `schema = "redirect"`, `action_type = "http"`, `action_payload = "https://google.com/"`, `filters = [{"name": "country", "mode": "accept", "payload": [<ISO-2 codes>]}]`. `[CONFIRMED-KEITARO]`
  - Position 2 (`Flow 2`, `POST streams`): `type = "default"`, `name = "Offers"`, `position = 2`, `state = "active"`, `schema = "landings"`, `action_type = "http"`, `offers = [{"offer_id": <id>, "share": 100, "state": "active"}]`. `[CONFIRMED-KEITARO]`
- **BR-1.2 (Sandbox Naming & Default Metadata Binding):**
  - Sandbox campaign names must begin with `test_<surname>_` (e.g., `test_bullo_campaign1`). `[CONFIRMED-TZ]`
  - Campaign must bind valid `domain_id`, `group_id`, and `traffic_source_id` from Keitaro dictionaries, defaulting in sandbox to `domain_id = 1813` (`kylovoa.com`), `group_id = 10332` (`FORTESTS`), and `traffic_source_id = 836` (`FORTESTS`). `[CONFIRMED-KEITARO]`
- **BR-1.3 (GEO Normalization):** Country codes input (e.g., `"au, mx"`) must be stripped, uppercased, deduplicated, and validated as 2-letter ISO 3166-1 alpha-2 codes (`["AU", "MX"]`). `[DERIVED-LOGIC]`

## 2. Campaign Stream Editing & Staging Invariants
- **BR-2.1 (Non-Empty Active Offer Stream on Push):** Before pushing via `PUSH TO KT`, an offer stream (`has_offers = True`) must contain at least one offer with `status == "active"`. `[DERIVED-LOGIC]`
- **BR-2.2 (Share Sum Invariant):** Traffic shares across all offers with `status == "active"` in a stream must be non-negative integers summing strictly to `100`. Offers with `status == "removed"` always have `share = 0` and `is_pinned = False`. `[CONFIRMED-TZ]`
- **BR-2.3 (PIN & Weight Distribution Algorithm):** `[CONFIRMED-TZ]`
  - Pinned active offers (`is_pinned == True`, `status == "active"`) keep their configured `share`.
  - Remaining share `remaining = 100 - sum(pinned_shares)` (must be `>= 0`) is distributed evenly across all unpinned active offers (`count = len(unpinned_active)`):
    - Each unpinned active offer receives `remaining // count`.
    - Any remainder `remaining % count` is added to the **last** unpinned active offer (e.g., 3 unpinned offers -> `33, 33, 34`).
  - If all active offers are pinned, their shares must already sum strictly to `100`.
  - Every unpinned active offer must receive at least `1%`: if `remaining < len(unpinned_active)` (e.g., pinned `100%` plus a new offer), `ADD`, `PIN`, and `BRING BACK` fail immediately with `422` instead of staging a `0%` active offer (Keitaro rejects active offers with `share <= 0`).
  - `REMOVE` auto-unpin: if after removal every remaining active offer is pinned and their shares do not sum to `100`, those offers are unpinned and rebalanced to `100%`.
- **BR-2.4 (No Duplicate Offers per Stream):** The same `keitaro_offer_id` must not appear twice within the same `stream_id` (enforced via DB unique constraint on `(stream_id, keitaro_offer_id)`). Reactivating a removed offer uses `BRING BACK` on the existing row rather than creating a duplicate. `[DERIVED-LOGIC]`
- **BR-2.5 (Staging Sync — `FETCH STREAMS FROM KT` & Empty-Offer Streams):** `[CONFIRMED-TZ]`
  - Streams fetched from `GET campaigns/{id}/streams` with `offers == []` (e.g., Flow 1) are persisted with `has_offers = False` and rendered as compact stream headers without parsing filters or redirects.
  - Offers previously stored locally in a stream that are missing from Keitaro's response are **not deleted**; they transition to `status = "removed"`, `share = 0`, `is_pinned = False` so the user can restore them with `BRING BACK`.
  - Offers that were never published (`is_published == False`, i.e. local drafts) and are missing from Keitaro are **deleted** instead of being archived as published-`removed` ghost rows.
  - Duplicate `offer_id` entries inside one Keitaro stream are aggregated (shares summed, warning logged). Keitaro offers with `state != "active"` or `share <= 0` are stored as `status = "removed"`, `share = 0` (a later `PUSH` therefore omits them from Keitaro).
  - `FETCH` overwrites local staged edits of the campaign's streams (a warning is logged when dirty streams are overwritten).
- **BR-2.6 (Staging Lifecycle — `REMOVE`, `CANCEL`, and `PUSH TO KT`):** `[CONFIRMED-TZ]`
  - `REMOVE`: Sets local `status = "removed"`, `share = 0`, `is_pinned = False`, and marks the stream `is_dirty = True`. On `PUSH TO KT`, only `status == "active"` offers are sent to `PUT streams/{id}`; removed offers remain archived locally for `BRING BACK`.
  - `CANCEL`: Deletes local `stream_offers` where `is_published == False` (newly added, never pushed) and restores `is_published == True` offers to `published_share` and `published_status`, resetting `is_dirty = False`.
  - `PUSH TO KT`: Sends `status == "active"` offers to `PUT streams/{id}`, updates `is_published = True`, `published_share = share`, `published_status = status` for active offers (and snapshots `published_status = "removed"`, `published_share = 0` for pushed-out removed offers), and resets `is_dirty = False`.
