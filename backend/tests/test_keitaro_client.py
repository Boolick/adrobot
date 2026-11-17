"""Unit tests for KeitaroClient and Keitaro Pydantic v2 schemas using httpx.MockTransport."""

import json
import logging
from typing import cast

import httpx
import pytest
from pydantic import SecretStr

from adrobot.core.exceptions import (
    ConfigurationError,
    DomainValidationError,
    ExternalServiceError,
    ExternalServiceTimeoutError,
)
from adrobot.integrations.keitaro import (
    KeitaroClient,
    KeitaroCreateCampaignRequest,
    KeitaroCreateStreamRequest,
    KeitaroStreamFilter,
    KeitaroStreamOfferItem,
)

TEST_BASE_URL = "https://tracker.example.com/admin_api/v1"
TEST_API_KEY = SecretStr("super-secret-keitaro-key-123")


def _make_client(
    handler: httpx.MockTransport,
    *,
    base_url: str = TEST_BASE_URL,
    api_key: SecretStr = TEST_API_KEY,
    timeout_seconds: float = 5.0,
) -> KeitaroClient:
    return KeitaroClient(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        transport=handler,
    )


def test_client_configuration_validation_and_safe_repr() -> None:
    """Verify invalid configuration fails fast and repr never exposes the API key."""
    with pytest.raises(ConfigurationError):
        KeitaroClient(base_url="", api_key=TEST_API_KEY)

    with pytest.raises(ConfigurationError):
        KeitaroClient(base_url="ftp://tracker.example.com/admin_api/v1", api_key=TEST_API_KEY)

    with pytest.raises(ConfigurationError):
        KeitaroClient(base_url=TEST_BASE_URL, api_key=SecretStr("   "))

    with pytest.raises(ConfigurationError):
        KeitaroClient(base_url=TEST_BASE_URL, api_key=TEST_API_KEY, timeout_seconds=0.0)

    client_without_slash = KeitaroClient(base_url=TEST_BASE_URL, api_key=TEST_API_KEY)
    client_with_slash = KeitaroClient(base_url=f"{TEST_BASE_URL}/", api_key=TEST_API_KEY)
    assert client_without_slash.base_url == f"{TEST_BASE_URL}/"
    assert client_with_slash.base_url == f"{TEST_BASE_URL}/"
    assert TEST_API_KEY.get_secret_value() not in repr(client_without_slash)


async def test_dictionaries_preserve_base_path_and_send_api_key_header() -> None:
    """Verify dictionary endpoints preserve /admin_api/v1 and inject Api-Key header."""
    seen_requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.method, str(request.url), request.headers.get("Api-Key")))
        if request.url.path == "/admin_api/v1/domains":
            return httpx.Response(
                200, json=[{"id": 1813, "name": "kylovoa.com", "state": "active"}]
            )
        if (
            request.url.path == "/admin_api/v1/groups"
            and request.url.params.get("type") == "campaigns"
        ):
            return httpx.Response(
                200, json=[{"id": 10332, "name": "FORTESTS", "type": "campaigns", "position": 1}]
            )
        if request.url.path == "/admin_api/v1/traffic_sources":
            return httpx.Response(200, json=[{"id": 836, "name": "FORTESTS", "state": "active"}])
        return httpx.Response(404, json={"error": "Unexpected path"})

    async with _make_client(httpx.MockTransport(handler), base_url=TEST_BASE_URL) as client:
        domains = await client.get_domains()
        groups = await client.get_campaign_groups()
        sources = await client.get_traffic_sources()

    assert len(domains) == 1
    assert domains[0].id == 1813
    assert domains[0].name == "kylovoa.com"

    assert len(groups) == 1
    assert groups[0].id == 10332
    assert groups[0].name == "FORTESTS"

    assert len(sources) == 1
    assert sources[0].id == 836
    assert sources[0].name == "FORTESTS"

    assert seen_requests == [
        ("GET", "https://tracker.example.com/admin_api/v1/domains", "super-secret-keitaro-key-123"),
        (
            "GET",
            "https://tracker.example.com/admin_api/v1/groups?type=campaigns",
            "super-secret-keitaro-key-123",
        ),
        (
            "GET",
            "https://tracker.example.com/admin_api/v1/traffic_sources",
            "super-secret-keitaro-key-123",
        ),
    ]


async def test_search_offers_filters_by_id_or_name_case_insensitively() -> None:
    """Verify search_offers handles empty queries, ID matches, and case-insensitive name search."""
    offers_payload = [
        {"id": 101, "name": "AU Nutra Cardio", "group_id": "", "payout_value": ""},
        {"id": 205, "name": "MX Finance Gold", "group_id": 12, "payout_value": "42.50"},
        {"id": 310, "name": "RO Crypto Top", "state": "active"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin_api/v1/offers"
        return httpx.Response(200, json=offers_payload)

    async with _make_client(httpx.MockTransport(handler), base_url=f"{TEST_BASE_URL}/") as client:
        all_offers = await client.search_offers()
        blank_query = await client.search_offers("   ")
        by_name = await client.search_offers("nutra")
        by_id = await client.search_offers("205")
        by_partial_id = await client.search_offers("31")

    assert len(all_offers) == 3
    assert all_offers[0].group_id is None
    assert all_offers[0].payout_value is None
    assert all_offers[1].payout_value == 42.5
    assert len(blank_query) == 3
    assert [o.id for o in by_name] == [101]
    assert [o.id for o in by_id] == [205]
    assert [o.id for o in by_partial_id] == [310]


async def test_create_campaign_and_streams_and_update_offers_roundtrip() -> None:
    """Verify POST campaigns, 2x POST streams, GET streams, and PUT streams/{id}."""
    recorded_bodies: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body: object = json.loads(request.content.decode("utf-8")) if request.content else None
        recorded_bodies.append((request.method, request.url.path, body))

        if request.method == "POST" and request.url.path == "/admin_api/v1/campaigns":
            return httpx.Response(
                200,
                json={
                    "id": 700,
                    "name": "test_bullo_campaign1",
                    "alias": "test-bullo-campaign1",
                    "type": "position",
                    "state": "active",
                    "cost_type": "CPC",
                    "domain_id": 1813,
                    "group_id": 10332,
                    "traffic_source_id": 836,
                },
            )
        if request.method == "POST" and request.url.path == "/admin_api/v1/streams":
            assert isinstance(body, dict)
            payload_dict = cast("dict[str, object]", body)
            if payload_dict.get("position") == 1:
                return httpx.Response(
                    200,
                    json={
                        "id": 901,
                        "campaign_id": 700,
                        "type": "regular",
                        "name": "Geo -> Google",
                        "position": 1,
                        "state": "active",
                        "schema": "redirect",
                        "action_type": "http",
                        "action_payload": "https://google.com/",
                        "offers": None,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": 902,
                    "campaign_id": 700,
                    "type": "default",
                    "name": "Offers",
                    "position": 2,
                    "state": "active",
                    "schema": "landings",
                    "action_type": "http",
                    "offers": [{"offer_id": 55, "share": 100, "state": "active"}],
                },
            )
        if request.method == "GET" and request.url.path == "/admin_api/v1/campaigns/700/streams":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 901,
                        "campaign_id": 700,
                        "name": "Geo -> Google",
                        "position": 1,
                        "schema": "redirect",
                        "offers": [],
                    },
                    {
                        "id": 902,
                        "campaign_id": 700,
                        "name": "Offers",
                        "position": 2,
                        "schema": "landings",
                        "offers": [{"offer_id": 55, "share": 100, "state": "active"}],
                    },
                ],
            )
        if request.method == "PUT" and request.url.path == "/admin_api/v1/streams/902":
            return httpx.Response(
                200,
                json={
                    "id": 902,
                    "campaign_id": 700,
                    "name": "Offers",
                    "position": 2,
                    "schema": "landings",
                    "offers": [
                        {"offer_id": 55, "share": 50, "state": "active"},
                        {"offer_id": 77, "share": 50, "state": "active"},
                    ],
                },
            )
        return httpx.Response(404, json={"error": "Not found"})

    async with _make_client(httpx.MockTransport(handler)) as client:
        campaign = await client.create_campaign(
            KeitaroCreateCampaignRequest(
                name="test_bullo_campaign1",
                alias="test-bullo-campaign1",
                domain_id=1813,
                group_id=10332,
                traffic_source_id=836,
            )
        )
        flow1 = await client.create_stream(
            KeitaroCreateStreamRequest(
                campaign_id=campaign.id,
                type="regular",
                name="Geo -> Google",
                position=1,
                stream_schema="redirect",
                action_type="http",
                action_payload="https://google.com/",
                filters=[KeitaroStreamFilter(name="country", mode="accept", payload=["AU", "MX"])],
            )
        )
        flow2 = await client.create_stream(
            KeitaroCreateStreamRequest(
                campaign_id=campaign.id,
                type="default",
                name="Offers",
                position=2,
                stream_schema="landings",
                action_type="http",
                offers=[KeitaroStreamOfferItem(offer_id=55, share=100, state="active")],
            )
        )
        streams = await client.get_campaign_streams(campaign.id)
        updated = await client.update_stream_offers(
            flow2.id,
            [
                KeitaroStreamOfferItem(offer_id=55, share=50),
                KeitaroStreamOfferItem(offer_id=77, share=50),
            ],
        )

    assert campaign.id == 700
    assert flow1.id == 901
    assert flow1.offers == []
    assert flow2.id == 902
    assert len(flow2.offers) == 1
    assert len(streams) == 2
    assert streams[0].stream_schema == "redirect"
    assert streams[0].offers == []
    assert streams[1].offers[0].offer_id == 55
    assert [(o.offer_id, o.share) for o in updated.offers] == [(55, 50), (77, 50)]

    assert recorded_bodies[0] == (
        "POST",
        "/admin_api/v1/campaigns",
        {
            "name": "test_bullo_campaign1",
            "alias": "test-bullo-campaign1",
            "type": "position",
            "state": "active",
            "cost_type": "CPC",
            "domain_id": 1813,
            "group_id": 10332,
            "traffic_source_id": 836,
        },
    )
    assert recorded_bodies[1] == (
        "POST",
        "/admin_api/v1/streams",
        {
            "campaign_id": 700,
            "type": "regular",
            "name": "Geo -> Google",
            "position": 1,
            "state": "active",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": "https://google.com/",
            "filters": [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}],
        },
    )
    assert recorded_bodies[2] == (
        "POST",
        "/admin_api/v1/streams",
        {
            "campaign_id": 700,
            "type": "default",
            "name": "Offers",
            "position": 2,
            "state": "active",
            "schema": "landings",
            "action_type": "http",
            "offers": [{"offer_id": 55, "share": 100, "state": "active"}],
        },
    )
    assert recorded_bodies[4] == (
        "PUT",
        "/admin_api/v1/streams/902",
        {
            "offers": [
                {"offer_id": 55, "share": 50, "state": "active"},
                {"offer_id": 77, "share": 50, "state": "active"},
            ]
        },
    )


async def test_http_401_and_404_error_responses_never_leak_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify 401 and 404 JSON {'error': ...} responses map cleanly without leaking Api-Key."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin_api/v1/domains":
            return httpx.Response(401, json={"error": "Unauthorized"})
        return httpx.Response(404, json={"error": "Campaign not found"})

    caplog.set_level(logging.WARNING)
    async with _make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ExternalServiceError) as err_401:
            await client.get_domains()
        assert err_401.value.status_code == 502
        assert err_401.value.details is not None
        assert err_401.value.details["upstream_status"] == "401"
        assert err_401.value.details["upstream_error"] == "Unauthorized"
        assert "Unauthorized" in err_401.value.message

        with pytest.raises(ExternalServiceError) as err_404:
            await client.get_campaign_streams(999)
        assert err_404.value.status_code == 502
        assert err_404.value.details is not None
        assert err_404.value.details["upstream_status"] == "404"
        assert "Campaign not found" in err_404.value.message

    assert TEST_API_KEY.get_secret_value() not in caplog.text
    assert TEST_API_KEY.get_secret_value() not in err_401.value.message


async def test_http_406_field_validation_dict_responses() -> None:
    """Verify Keitaro 406 field-validation dicts (list and string values) map to details."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin_api/v1/campaigns":
            return httpx.Response(
                406,
                json={
                    "name": ["Name has already been taken."],
                    "domain_id": ["Domain is invalid."],
                },
            )
        return httpx.Response(
            406,
            json={"offers": "Sum of shares must be 100"},
        )

    async with _make_client(httpx.MockTransport(handler)) as client:
        with pytest.raises(ExternalServiceError) as campaign_err:
            await client.create_campaign(
                KeitaroCreateCampaignRequest(
                    name="test_bullo_dup",
                    domain_id=1813,
                    group_id=10332,
                    traffic_source_id=836,
                )
            )
        assert campaign_err.value.details is not None
        assert campaign_err.value.details["upstream_status"] == "406"
        assert campaign_err.value.details["name"] == "Name has already been taken."
        assert campaign_err.value.details["domain_id"] == "Domain is invalid."
        assert "Name has already been taken." in campaign_err.value.message

        with pytest.raises(ExternalServiceError) as stream_err:
            await client.update_stream_offers(902, [KeitaroStreamOfferItem(offer_id=55, share=50)])
        assert stream_err.value.details is not None
        assert stream_err.value.details["upstream_status"] == "406"
        assert stream_err.value.details["offers"] == "Sum of shares must be 100"


async def test_timeouts_transport_errors_and_invalid_responses() -> None:
    """Verify timeouts, transport failures, malformed payloads, and invalid IDs map cleanly."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    def connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def bad_json_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    def bad_schema_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "object"})

    def html_502_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    def nested_406_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            406,
            json={
                "error": "Validation failed",
                "errors": {"path": ["Reserved detail key collision"]},
            },
        )

    async with _make_client(httpx.MockTransport(timeout_handler)) as client:
        with pytest.raises(ExternalServiceTimeoutError) as timeout_err:
            await client.get_domains()
        assert timeout_err.value.status_code == 504
        assert timeout_err.value.code == "EXTERNAL_SERVICE_TIMEOUT"

        with pytest.raises(DomainValidationError):
            await client.get_campaign_streams(0)
        with pytest.raises(DomainValidationError):
            await client.update_stream_offers(0, [])

    async with _make_client(httpx.MockTransport(connect_error_handler)) as client:
        with pytest.raises(ExternalServiceError) as conn_err:
            await client.get_domains()
        assert conn_err.value.status_code == 502

    async with _make_client(httpx.MockTransport(bad_json_handler)) as client:
        with pytest.raises(ExternalServiceError):
            await client.get_domains()

    async with _make_client(httpx.MockTransport(bad_schema_handler)) as client:
        with pytest.raises(ExternalServiceError):
            await client.get_domains()

    async with _make_client(httpx.MockTransport(html_502_handler)) as client:
        with pytest.raises(ExternalServiceError) as html_err:
            await client.get_domains()
        assert html_err.value.details is not None
        assert html_err.value.details["upstream_status"] == "502"
        assert html_err.value.details["response_excerpt"] == "Bad Gateway"

    async with _make_client(httpx.MockTransport(nested_406_handler)) as client:
        with pytest.raises(ExternalServiceError) as nested_err:
            await client.get_domains()
        assert nested_err.value.details is not None
        assert nested_err.value.details["path"] == "domains"
        assert nested_err.value.details["field.path"] == "Reserved detail key collision"
        assert nested_err.value.details["upstream_error"] == "Validation failed"
