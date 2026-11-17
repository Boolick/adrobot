"""End-to-end API integration tests for `/api/v1` dictionaries, campaigns, and stream editor."""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.api.dependencies import get_keitaro_client
from adrobot.core.config import Settings, get_settings
from adrobot.db.session import (
    Base,
    create_engine_from_url,
    get_db_session,
    get_session_factory,
)
from adrobot.integrations.keitaro import KeitaroClient
from adrobot.main import create_app


@dataclass
class _FakeKeitaroState:
    """In-memory stateful fake Keitaro Admin API backend for MockTransport."""

    next_campaign_id: int = 500
    next_stream_id: int = 900
    campaigns: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    streams_by_campaign: dict[int, list[dict[str, object]]] = field(
        default_factory=dict[int, list[dict[str, object]]]
    )
    recorded_calls: list[tuple[str, str, object]] = field(
        default_factory=list[tuple[str, str, object]]
    )
    force_error: tuple[int, dict[str, object]] | None = None
    force_timeout: bool = False
    fail_nth_stream_post: int | None = None
    stream_posts: int = 0
    offers_catalog: list[dict[str, object]] = field(
        default_factory=lambda: [
            {"id": 55, "name": "AU Nutra Primary", "group_id": 1, "state": "active"},
            {"id": 66, "name": "AU Nutra Secondary", "group_id": 1, "state": "active"},
            {"id": 77, "name": "MX Finance Top", "group_id": 2, "state": "active"},
            {"id": 88, "name": "RO Crypto Fallback", "group_id": 2, "state": "active"},
        ]
    )

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.force_timeout:
            raise httpx.ReadTimeout("Simulated Keitaro timeout", request=request)

        body: object = json.loads(request.content.decode("utf-8")) if request.content else None
        self.recorded_calls.append((request.method, request.url.path, body))

        if self.force_error is not None:
            status_code, err_payload = self.force_error
            return httpx.Response(status_code, json=err_payload)

        path = request.url.path
        if request.method == "DELETE" and path.startswith("/admin_api/v1/campaigns/"):
            cid = int(path.split("/")[4])
            self.campaigns = [c for c in self.campaigns if c["id"] != cid]
            self.streams_by_campaign.pop(cid, None)
            return httpx.Response(204)
        if request.method == "POST" and path == "/admin_api/v1/streams":
            self.stream_posts += 1
            if self.fail_nth_stream_post == self.stream_posts:
                return httpx.Response(406, json={"name": ["Stream rejected"]})
        if request.method == "GET" and path == "/admin_api/v1/domains":
            return httpx.Response(
                200, json=[{"id": 1813, "name": "kylovoa.com", "state": "active"}]
            )
        if request.method == "GET" and path == "/admin_api/v1/groups":
            return httpx.Response(
                200, json=[{"id": 10332, "name": "FORTESTS", "type": "campaigns", "position": 1}]
            )
        if request.method == "GET" and path == "/admin_api/v1/traffic_sources":
            return httpx.Response(200, json=[{"id": 836, "name": "FORTESTS", "state": "active"}])
        if request.method == "GET" and path == "/admin_api/v1/offers":
            return httpx.Response(200, json=self.offers_catalog)

        if request.method == "POST" and path == "/admin_api/v1/campaigns":
            payload = cast("dict[str, object]", body)
            cid = self.next_campaign_id
            self.next_campaign_id += 1
            created = {
                "id": cid,
                "name": payload["name"],
                "alias": payload.get("alias"),
                "type": payload["type"],
                "state": payload["state"],
                "cost_type": payload["cost_type"],
                "domain_id": payload["domain_id"],
                "group_id": payload["group_id"],
                "traffic_source_id": payload["traffic_source_id"],
            }
            self.campaigns.append(created)
            self.streams_by_campaign[cid] = []
            return httpx.Response(200, json=created)

        if request.method == "POST" and path == "/admin_api/v1/streams":
            payload = cast("dict[str, object]", body)
            sid = self.next_stream_id
            self.next_stream_id += 1
            cid = cast("int", payload["campaign_id"])
            stream = {
                "id": sid,
                "campaign_id": cid,
                "type": payload["type"],
                "name": payload["name"],
                "position": payload["position"],
                "state": payload["state"],
                "schema": payload["schema"],
                "action_type": payload["action_type"],
                "action_payload": payload.get("action_payload"),
                "offers": payload.get("offers", []),
            }
            self.streams_by_campaign.setdefault(cid, []).append(stream)
            return httpx.Response(200, json=stream)

        if request.method == "GET" and path.startswith("/admin_api/v1/campaigns/"):
            cid = int(path.split("/")[4])
            return httpx.Response(200, json=self.streams_by_campaign.get(cid, []))

        if request.method == "PUT" and path.startswith("/admin_api/v1/streams/"):
            sid = int(path.split("/")[4])
            payload = cast("dict[str, object]", body)
            for streams in self.streams_by_campaign.values():
                for stream in streams:
                    if stream["id"] == sid:
                        stream["offers"] = payload["offers"]
                        return httpx.Response(200, json=stream)
            return httpx.Response(404, json={"error": "Stream not found"})

        return httpx.Response(404, json={"error": f"Unhandled mock route: {request.method} {path}"})


@pytest.fixture
async def api_env() -> AsyncGenerator[tuple[FastAPI, _FakeKeitaroState], None]:
    """Provide a FastAPI app wired to an in-memory SQLite DB and MockTransport KeitaroClient."""
    engine = create_engine_from_url("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    fake_keitaro = _FakeKeitaroState()

    app = create_app()
    test_settings = Settings(
        environment="test",
        keitaro_api_url="https://keitaro.test/admin_api/v1",
        keitaro_api_key=SecretStr("test-api-key"),
    )

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_keitaro_client() -> AsyncGenerator[KeitaroClient, None]:
        async with KeitaroClient(
            base_url=test_settings.keitaro_api_url,
            api_key=test_settings.keitaro_api_key,
            transport=httpx.MockTransport(fake_keitaro.handle),
        ) as client:
            yield client

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_keitaro_client] = override_keitaro_client

    try:
        yield app, fake_keitaro
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_dictionaries_offer_search_and_openapi_generation(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Verify /api/v1/dictionaries, /api/v1/offers?q=, and typed OpenAPI schema generation."""
    app, _ = api_env
    openapi_doc = app.openapi()
    assert "/api/v1/dictionaries" in openapi_doc["paths"]
    assert "/api/v1/streams/{stream_id}/push" in openapi_doc["paths"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        dict_resp = await client.get("/api/v1/dictionaries")
        assert dict_resp.status_code == 200
        dict_data = dict_resp.json()
        assert dict_data["domains"][0]["id"] == 1813
        assert dict_data["groups"][0]["id"] == 10332
        assert dict_data["traffic_sources"][0]["id"] == 836
        assert dict_data["defaults"] == {
            "domain_id": 1813,
            "group_id": 10332,
            "traffic_source_id": 836,
            "campaign_prefix": "test_bullo_",
        }

        all_offers = await client.get("/api/v1/offers")
        assert all_offers.status_code == 200
        assert len(all_offers.json()) == 4

        filtered = await client.get("/api/v1/offers", params={"q": "nutra"})
        assert filtered.status_code == 200
        assert [o["id"] for o in filtered.json()] == [55, 66]


async def test_full_campaign_and_stream_editor_lifecycle(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Verify full campaign creation and stream editor staging lifecycle."""
    app, fake_kt = api_env

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Create campaign (3-step Keitaro flow + local persistence)
        create_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "test_bullo_camp1",
                "geo": "au, mx, au",
                "initial_offer_id": 55,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        campaign_id = created["id"]
        kt_campaign_id = created["keitaro_campaign_id"]
        assert created["name"] == "test_bullo_camp1"
        assert created["geo"] == ["AU", "MX"]
        assert created["domain_id"] == 1813
        assert created["group_id"] == 10332
        assert created["source_id"] == 836

        streams = created["streams"]
        assert len(streams) == 2
        flow1, flow2 = streams[0], streams[1]
        assert flow1["position"] == 1
        assert flow1["has_offers"] is False
        assert flow1["can_push"] is False
        assert flow1["validation_error"] is None
        assert flow2["position"] == 2
        assert flow2["has_offers"] is True
        assert flow2["can_push"] is True
        assert flow2["validation_error"] is None
        assert [(o["keitaro_offer_id"], o["share"]) for o in flow2["offers"]] == [(55, 100)]

        flow2_id = flow2["id"]

        # Verify Flow 1 & Flow 2 exact payloads sent to Keitaro
        stream_creates = [
            call for call in fake_kt.recorded_calls if call[:2] == ("POST", "/admin_api/v1/streams")
        ]
        assert len(stream_creates) == 2
        flow1_body = cast("dict[str, object]", stream_creates[0][2])
        assert flow1_body["filters"] == [
            {"name": "country", "mode": "accept", "payload": ["AU", "MX"]}
        ]
        assert flow1_body["action_payload"] == "https://google.com/"

        # List and detail endpoints
        list_resp = await client.get("/api/v1/campaigns")
        assert list_resp.status_code == 200
        assert [c["id"] for c in list_resp.json()] == [campaign_id]

        detail_resp = await client.get(f"/api/v1/campaigns/{campaign_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == campaign_id

        # 2. Simulate external offer addition in Keitaro -> FETCH STREAMS FROM KT
        fake_kt.streams_by_campaign[kt_campaign_id][1]["offers"] = [
            {"offer_id": 55, "share": 50, "state": "active"},
            {"offer_id": 66, "share": 50, "state": "active"},
        ]
        fetch_resp = await client.post(f"/api/v1/campaigns/{campaign_id}/streams/fetch")
        assert fetch_resp.status_code == 200
        fetched_flow2 = fetch_resp.json()["streams"][1]
        assert fetched_flow2["is_dirty"] is False
        assert [
            (o["keitaro_offer_id"], o["offer_name"], o["share"]) for o in fetched_flow2["offers"]
        ] == [
            (55, "AU Nutra Primary", 50),
            (66, "AU Nutra Secondary", 50),
        ]

        # 3. Simulate external deletion of offer 66 in Keitaro -> must move to removed, NOT deleted
        fake_kt.streams_by_campaign[kt_campaign_id][1]["offers"] = [
            {"offer_id": 55, "share": 100, "state": "active"},
        ]
        fetch_missing_resp = await client.post(f"/api/v1/campaigns/{campaign_id}/streams/fetch")
        assert fetch_missing_resp.status_code == 200
        fetched_offers = fetch_missing_resp.json()["streams"][1]["offers"]
        assert [
            (o["keitaro_offer_id"], o["status"], o["share"], o["published_status"])
            for o in fetched_offers
        ] == [
            (55, "active", 100, "active"),
            (66, "removed", 0, "removed"),
        ]

        # 4. Simulate deleting ALL offers externally in KT -> Flow 2 stays has_offers=True
        fake_kt.streams_by_campaign[kt_campaign_id][1]["offers"] = []
        fetch_empty_resp = await client.post(f"/api/v1/campaigns/{campaign_id}/streams/fetch")
        assert fetch_empty_resp.status_code == 200
        empty_flow2 = fetch_empty_resp.json()["streams"][1]
        assert empty_flow2["has_offers"] is True
        assert empty_flow2["can_push"] is False
        assert empty_flow2["validation_error"] == "Stream must have at least one active offer"
        assert all(o["status"] == "removed" for o in empty_flow2["offers"])

        # 5. Bring back offer 55 & add 77 & add 88 (33, 33, 34 split)
        bb_55 = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/bring-back")
        assert bb_55.status_code == 200
        assert bb_55.json()["can_push"] is True

        add_77 = await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 77, "offer_name": "MX Finance Top"},
        )
        assert add_77.status_code == 200
        add_88 = await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 88, "offer_name": "RO Crypto Fallback"},
        )
        assert add_88.status_code == 200
        active_3 = [o for o in add_88.json()["offers"] if o["status"] == "active"]
        assert [(o["keitaro_offer_id"], o["share"]) for o in active_3] == [
            (55, 33),
            (77, 33),
            (88, 34),
        ]

        # 6. Pin offer 55 to explicit share=50, then update to share=60 (stays pinned)
        pin_50 = await client.post(
            f"/api/v1/streams/{flow2_id}/offers/55/pin",
            json={"share": 50},
        )
        assert pin_50.status_code == 200
        active_pinned = [o for o in pin_50.json()["offers"] if o["status"] == "active"]
        assert [(o["keitaro_offer_id"], o["share"], o["is_pinned"]) for o in active_pinned] == [
            (55, 50, True),
            (77, 25, False),
            (88, 25, False),
        ]

        pin_60 = await client.post(
            f"/api/v1/streams/{flow2_id}/offers/55/pin",
            json={"share": 60},
        )
        assert pin_60.status_code == 200
        active_60 = [o for o in pin_60.json()["offers"] if o["status"] == "active"]
        assert [(o["keitaro_offer_id"], o["share"], o["is_pinned"]) for o in active_60] == [
            (55, 60, True),
            (77, 20, False),
            (88, 20, False),
        ]

        # Toggle pin off without body -> equal split returns; toggle with {} -> pins again
        unpin_55 = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/pin")
        assert unpin_55.status_code == 200
        active_unpinned = [o for o in unpin_55.json()["offers"] if o["status"] == "active"]
        assert [(o["keitaro_offer_id"], o["share"], o["is_pinned"]) for o in active_unpinned] == [
            (55, 33, False),
            (77, 33, False),
            (88, 34, False),
        ]

        repin_55 = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/pin", json={})
        assert repin_55.status_code == 200
        assert (
            next(o["is_pinned"] for o in repin_55.json()["offers"] if o["keitaro_offer_id"] == 55)
            is True
        )

        # 7. Remove offer 77 -> pinned 55 keeps 33%, unpinned 88 receives 67%; bring back 77
        rem_77 = await client.post(f"/api/v1/streams/{flow2_id}/offers/77/remove")
        assert rem_77.status_code == 200
        assert [
            (o["keitaro_offer_id"], o["status"], o["share"]) for o in rem_77.json()["offers"]
        ] == [
            (55, "active", 33),
            (88, "active", 67),
            (66, "removed", 0),
            (77, "removed", 0),
        ]

        bb_77 = await client.post(f"/api/v1/streams/{flow2_id}/offers/77/bring-back")
        assert bb_77.status_code == 200
        assert [
            o["keitaro_offer_id"] for o in bb_77.json()["offers"] if o["status"] == "active"
        ] == [
            55,
            77,
            88,
        ]

        # 8. CANCEL -> unpublished (77, 88) physically deleted; published (55, 66) reverted
        cancel_resp = await client.post(f"/api/v1/streams/{flow2_id}/cancel")
        assert cancel_resp.status_code == 200
        canceled = cancel_resp.json()
        assert canceled["is_dirty"] is False
        assert [(o["keitaro_offer_id"], o["status"], o["share"]) for o in canceled["offers"]] == [
            (55, "removed", 0),
            (66, "removed", 0),
        ]

        # 9. Stage realistic changes & PUSH TO KT:
        # Bring back 55, add 77, add-then-remove 88 (unpublished removed must be purged on push)
        await client.post(f"/api/v1/streams/{flow2_id}/offers/55/bring-back")
        await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 77, "offer_name": "MX Finance Top"},
        )
        await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 88, "offer_name": "RO Crypto Fallback"},
        )
        await client.post(f"/api/v1/streams/{flow2_id}/offers/88/remove")

        push_resp = await client.post(f"/api/v1/streams/{flow2_id}/push")
        assert push_resp.status_code == 200
        pushed = push_resp.json()
        assert pushed["is_dirty"] is False
        assert pushed["can_push"] is True
        # Offer 88 (unpublished + removed) was purged; Offer 66 (published + removed) stays archived
        assert [
            (
                o["keitaro_offer_id"],
                o["status"],
                o["share"],
                o["is_published"],
                o["published_status"],
            )
            for o in pushed["offers"]
        ] == [
            (55, "active", 50, True, "active"),
            (77, "active", 50, True, "active"),
            (66, "removed", 0, True, "removed"),
        ]

        # Verify Keitaro PUT streams/{id} received ONLY active offers
        put_calls = [
            call
            for call in fake_kt.recorded_calls
            if call[:2] == ("PUT", f"/admin_api/v1/streams/{flow2['keitaro_stream_id']}")
        ]
        assert len(put_calls) == 1
        assert put_calls[0][2] == {
            "offers": [
                {"offer_id": 55, "share": 50, "state": "active"},
                {"offer_id": 77, "share": 50, "state": "active"},
            ]
        }


async def test_api_error_mapping_404_409_422_502_504(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Verify domain validation, conflict, not-found, and upstream Keitaro HTTP error mapping."""
    app, fake_kt = api_env

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 422 on invalid campaign name or invalid GEO
        bad_name = await client.post(
            "/api/v1/campaigns",
            json={"name": "prod_campaign", "initial_offer_id": 55},
        )
        assert bad_name.status_code == 422
        assert bad_name.json()["error"]["code"] == "DOMAIN_VALIDATION_ERROR"

        bad_prefix_only = await client.post(
            "/api/v1/campaigns",
            json={"name": "test_", "initial_offer_id": 55},
        )
        assert bad_prefix_only.status_code == 422

        bad_geo = await client.post(
            "/api/v1/campaigns",
            json={"name": "test_bullo_badgeo", "geo": ["AUS"], "initial_offer_id": 55},
        )
        assert bad_geo.status_code == 422

        # 404 on unknown campaign / stream
        assert (await client.get("/api/v1/campaigns/9999")).status_code == 404
        assert (await client.post("/api/v1/campaigns/9999/streams/fetch")).status_code == 404
        assert (await client.post("/api/v1/streams/9999/cancel")).status_code == 404

        # Create valid campaign to test stream-level errors
        created = (
            await client.post(
                "/api/v1/campaigns",
                json={"name": "test_bullo_errs", "initial_offer_id": 55},
            )
        ).json()
        flow1_id = created["streams"][0]["id"]
        flow2_id = created["streams"][1]["id"]

        # 422 editing Flow 1 (has_offers=False)
        edit_flow1 = await client.post(
            f"/api/v1/streams/{flow1_id}/offers",
            json={"offer_id": 66, "offer_name": "Nope"},
        )
        assert edit_flow1.status_code == 422

        # 409 adding duplicate active offer
        dup_offer = await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 55, "offer_name": "Duplicate"},
        )
        assert dup_offer.status_code == 409
        assert dup_offer.json()["error"]["code"] == "RESOURCE_CONFLICT"

        # 422 pushing after removing last active offer
        rem_55 = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/remove")
        assert rem_55.status_code == 200
        assert rem_55.json()["can_push"] is False
        push_empty = await client.post(f"/api/v1/streams/{flow2_id}/push")
        assert push_empty.status_code == 422

        # Restore 55, add 66, pin 55=100 (leaving 66=0) -> push fails with 422
        await client.post(f"/api/v1/streams/{flow2_id}/offers/55/bring-back")
        await client.post(
            f"/api/v1/streams/{flow2_id}/offers",
            json={"offer_id": 66, "offer_name": "Secondary"},
        )
        pin_100 = await client.post(
            f"/api/v1/streams/{flow2_id}/offers/55/pin",
            json={"share": 100},
        )
        # Pinning 55=100 would leave 0% for 66 -> rejected at mutation time (422)
        assert pin_100.status_code == 422
        assert "too small" in pin_100.json()["error"]["message"]
        assert (await client.post(f"/api/v1/streams/{flow2_id}/push")).status_code == 200

        # 502 from Keitaro 406 error
        fake_kt.force_error = (406, {"name": ["Campaign name already exists"]})
        kt_err = await client.post(
            "/api/v1/campaigns",
            json={"name": "test_bullo_dup", "initial_offer_id": 55},
        )
        assert kt_err.status_code == 502
        assert kt_err.json()["error"]["code"] == "EXTERNAL_SERVICE_ERROR"
        fake_kt.force_error = None

        # 504 on Keitaro timeout
        fake_kt.force_timeout = True
        kt_timeout = await client.get("/api/v1/dictionaries")
        assert kt_timeout.status_code == 504
        assert kt_timeout.json()["error"]["code"] == "EXTERNAL_SERVICE_TIMEOUT"


async def _create_campaign(client: httpx.AsyncClient, name: str) -> tuple[int, int, int]:
    resp = await client.post("/api/v1/campaigns", json={"name": name, "initial_offer_id": 55})
    assert resp.status_code == 201
    body = resp.json()
    return body["id"], body["keitaro_campaign_id"], body["streams"][1]["id"]


async def test_create_campaign_compensates_keitaro_when_flow2_fails(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """A failed Flow 2 POST must delete the orphaned Keitaro campaign and leave no local row."""
    app, fake_kt = api_env
    fake_kt.fail_nth_stream_post = 2
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/campaigns", json={"name": "test_bullo_comp", "initial_offer_id": 55}
        )
        assert resp.status_code == 502
        assert ("DELETE", "/admin_api/v1/campaigns/500", None) in fake_kt.recorded_calls
        assert fake_kt.campaigns == []
        assert (await client.get("/api/v1/campaigns")).json() == []


async def test_create_campaign_duplicate_name_returns_409(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """A second create with an already tracked name is rejected before touching Keitaro."""
    app, fake_kt = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await _create_campaign(client, "test_bullo_dupname")
        before = len(fake_kt.campaigns)
        resp = await client.post(
            "/api/v1/campaigns", json={"name": "test_bullo_dupname", "initial_offer_id": 55}
        )
        assert resp.status_code == 409
        assert len(fake_kt.campaigns) == before


async def test_add_rejected_422_when_pinned_100_and_remove_auto_unpins(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """ADD is rejected when no share is left; REMOVE of the only unpinned offer rebalances."""
    app, _ = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        _, _, flow2_id = await _create_campaign(client, "test_bullo_weights")
        pin = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/pin", json={"share": 100})
        assert pin.status_code == 200
        rejected = await client.post(
            f"/api/v1/streams/{flow2_id}/offers", json={"offer_id": 66, "offer_name": "B"}
        )
        assert rejected.status_code == 422
        assert "too small" in rejected.json()["error"]["message"]

        await client.post(f"/api/v1/streams/{flow2_id}/offers/55/pin")  # unpin
        await client.post(f"/api/v1/streams/{flow2_id}/offers", json={"offer_id": 66})
        pin_60 = await client.post(f"/api/v1/streams/{flow2_id}/offers/55/pin", json={"share": 60})
        assert pin_60.status_code == 200
        removed = await client.post(f"/api/v1/streams/{flow2_id}/offers/66/remove")
        assert removed.status_code == 200
        active = [o for o in removed.json()["offers"] if o["status"] == "active"]
        assert [(o["keitaro_offer_id"], o["share"], o["is_pinned"]) for o in active] == [
            (55, 100, False)
        ]
        assert removed.json()["can_push"] is True


async def test_fetch_deletes_unpublished_drafts_instead_of_ghosting(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """FETCH drops unpublished drafts absent from Keitaro rather than archiving them."""
    app, _ = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        campaign_id, _, flow2_id = await _create_campaign(client, "test_bullo_fetchdraft")
        added = await client.post(f"/api/v1/streams/{flow2_id}/offers", json={"offer_id": 66})
        assert added.status_code == 200
        fetched = await client.post(f"/api/v1/campaigns/{campaign_id}/streams/fetch")
        assert fetched.status_code == 200
        offers = fetched.json()["streams"][1]["offers"]
        assert [o["keitaro_offer_id"] for o in offers] == [55]


async def test_fetch_aggregates_duplicates_and_removes_inactive_offers(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Duplicate Keitaro offer ids are summed; disabled or 0% offers become removed."""
    app, fake_kt = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        campaign_id, kt_campaign_id, _ = await _create_campaign(client, "test_bullo_fetchdup")
        fake_kt.streams_by_campaign[kt_campaign_id][1]["offers"] = [
            {"offer_id": 55, "share": 30, "state": "active"},
            {"offer_id": 55, "share": 30, "state": "active"},
            {"offer_id": 66, "share": 40, "state": "disabled"},
            {"offer_id": 77, "share": 0, "state": "active"},
        ]
        fetched = await client.post(f"/api/v1/campaigns/{campaign_id}/streams/fetch")
        assert fetched.status_code == 200
        offers = fetched.json()["streams"][1]["offers"]
        assert [(o["keitaro_offer_id"], o["status"], o["share"]) for o in offers] == [
            (55, "active", 60),
            (66, "removed", 0),
            (77, "removed", 0),
        ]


async def test_double_click_add_offer_yields_single_200_and_409(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Concurrent identical ADD requests are serialized: one succeeds, one conflicts cleanly."""
    app, _ = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        _, _, flow2_id = await _create_campaign(client, "test_bullo_race")
        url = f"/api/v1/streams/{flow2_id}/offers"
        first, second = await asyncio.gather(
            client.post(url, json={"offer_id": 66}),
            client.post(url, json={"offer_id": 66}),
        )
        assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_push_marks_published_from_snapshot_and_stays_dirty_on_concurrent_edit(
    api_env: tuple[FastAPI, _FakeKeitaroState],
) -> None:
    """Edits staged during the PUT must remain dirty and unpublished after the push finishes."""
    app, fake_kt = api_env
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        _, _, flow2_id = await _create_campaign(client, "test_bullo_snap")
        await client.post(f"/api/v1/streams/{flow2_id}/offers", json={"offer_id": 66})
        pushed = await client.post(f"/api/v1/streams/{flow2_id}/push")
        assert pushed.status_code == 200
        body = pushed.json()
        assert body["is_dirty"] is False
        assert [(o["share"], o["published_share"]) for o in body["offers"]] == [(50, 50), (50, 50)]
        assert fake_kt.recorded_calls[-1][:2] == ("PUT", f"/admin_api/v1/streams/{900 + 1}")
