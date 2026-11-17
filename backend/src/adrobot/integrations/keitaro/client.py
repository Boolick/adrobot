"""Typed async HTTP client for the Keitaro Admin API."""

import logging
from collections.abc import Sequence
from typing import Self, cast
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError

from adrobot.core.exceptions import (
    ConfigurationError,
    DomainValidationError,
    ExternalServiceError,
    ExternalServiceTimeoutError,
)
from adrobot.integrations.keitaro.schemas import (
    KeitaroCampaign,
    KeitaroCampaignGroup,
    KeitaroCreateCampaignRequest,
    KeitaroCreateStreamRequest,
    KeitaroDomain,
    KeitaroOffer,
    KeitaroStream,
    KeitaroStreamOfferItem,
    KeitaroTrafficSource,
    KeitaroUpdateStreamOffersRequest,
)

logger = logging.getLogger(__name__)

_DOMAINS_ADAPTER: TypeAdapter[list[KeitaroDomain]] = TypeAdapter(list[KeitaroDomain])
_GROUPS_ADAPTER: TypeAdapter[list[KeitaroCampaignGroup]] = TypeAdapter(list[KeitaroCampaignGroup])
_SOURCES_ADAPTER: TypeAdapter[list[KeitaroTrafficSource]] = TypeAdapter(list[KeitaroTrafficSource])
_OFFERS_ADAPTER: TypeAdapter[list[KeitaroOffer]] = TypeAdapter(list[KeitaroOffer])
_STREAMS_ADAPTER: TypeAdapter[list[KeitaroStream]] = TypeAdapter(list[KeitaroStream])

_RESERVED_DETAIL_KEYS = frozenset({"upstream_status", "method", "path", "upstream_error"})


def _stringify_validation_value(value: object) -> str:
    """Format a Keitaro validation error value (list, string, or scalar) into text."""
    if isinstance(value, list):
        items = [str(item).strip() for item in cast("list[object]", value) if str(item).strip()]
        return "; ".join(items) if items else "Invalid value"
    if isinstance(value, dict):
        parts: list[str] = []
        for sub_key, sub_val in cast("dict[object, object]", value).items():
            parts.append(f"{sub_key}: {_stringify_validation_value(sub_val)}")
        return "; ".join(parts) if parts else "Invalid value"
    text = str(value).strip()
    return text if text else "Invalid value"


def _extract_field_errors(
    mapping: dict[object, object],
    *,
    details: dict[str, str],
) -> list[str]:
    """Extract field-level validation entries into details and formatted summary strings."""
    summary_parts: list[str] = []
    for raw_key, raw_value in mapping.items():
        field_name = str(raw_key).strip()
        if not field_name:
            continue
        rendered = _stringify_validation_value(raw_value)
        detail_key = f"field.{field_name}" if field_name in _RESERVED_DETAIL_KEYS else field_name
        details[detail_key] = rendered
        summary_parts.append(f"{field_name}: {rendered}")
    return summary_parts


def _parse_keitaro_error(
    response: httpx.Response,
    *,
    method: str,
    path: str,
) -> tuple[str, dict[str, str]]:
    """Parse Keitaro error responses (including {'error': ...} and 406 field dicts)."""
    status_code = response.status_code
    details: dict[str, str] = {
        "upstream_status": str(status_code),
        "method": method,
        "path": path,
    }

    try:
        raw_body: object = response.json()
    except ValueError:
        excerpt = response.text.strip()[:200]
        if excerpt:
            details["response_excerpt"] = excerpt
            return (
                f"Keitaro API error ({status_code}) on {method} {path}: {excerpt}",
                details,
            )
        return f"Keitaro API error ({status_code}) on {method} {path}.", details

    if not isinstance(raw_body, dict):
        rendered = _stringify_validation_value(raw_body)
        details["upstream_error"] = rendered
        return f"Keitaro API error ({status_code}) on {method} {path}: {rendered}", details

    payload = cast("dict[object, object]", raw_body)
    messages: list[str] = []

    if "error" in payload:
        error_text = _stringify_validation_value(payload["error"])
        details["upstream_error"] = error_text
        messages.append(error_text)
    elif isinstance(payload.get("message"), str) and str(payload["message"]).strip():
        message_text = str(payload["message"]).strip()
        details["upstream_error"] = message_text
        messages.append(message_text)

    nested_errors = payload.get("errors")
    if isinstance(nested_errors, dict):
        messages.extend(
            _extract_field_errors(cast("dict[object, object]", nested_errors), details=details)
        )

    non_envelope_fields = {
        k: v
        for k, v in payload.items()
        if str(k) not in {"error", "errors", "message", "code", "status"}
    }
    if non_envelope_fields:
        messages.extend(_extract_field_errors(non_envelope_fields, details=details))

    if messages:
        return (
            f"Keitaro API error ({status_code}) on {method} {path}: {'; '.join(messages)}",
            details,
        )
    return f"Keitaro API error ({status_code}) on {method} {path}.", details


def _validate_positive_id(value: int, *, field_name: str) -> None:
    """Validate positive integer path identifiers before building Keitaro endpoints."""
    if value <= 0:
        raise DomainValidationError(
            f"{field_name} must be a positive integer.",
            details={field_name: str(value)},
        )


def _validate_with_adapter[T](
    adapter: TypeAdapter[T],
    raw: object,
    *,
    method: str,
    path: str,
) -> T:
    """Validate an HTTP JSON payload with a Pydantic TypeAdapter, mapping schema errors."""
    try:
        return adapter.validate_python(raw)
    except ValidationError as exc:
        logger.warning("Unexpected Keitaro response schema on %s %s", method, path)
        raise ExternalServiceError(
            f"Unexpected response payload from Keitaro on {method} {path}.",
            details={"method": method, "path": path},
        ) from exc


def _validate_model[T: BaseModel](
    model_cls: type[T],
    raw: object,
    *,
    method: str,
    path: str,
) -> T:
    """Validate a single JSON object into a Pydantic BaseModel, mapping schema errors."""
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Unexpected Keitaro response schema on %s %s", method, path)
        raise ExternalServiceError(
            f"Unexpected response payload from Keitaro on {method} {path}.",
            details={"method": method, "path": path},
        ) from exc


class KeitaroClient:
    """Async HTTPX client wrapping the Keitaro Admin API (`/admin_api/v1/`)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        cleaned_url = base_url.strip()
        parsed = urlparse(cleaned_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(
                "KEITARO_API_URL must be a valid HTTP or HTTPS URL.",
                details={"field": "keitaro_api_url"},
            )

        secret_value = api_key.get_secret_value().strip()
        if not secret_value:
            raise ConfigurationError(
                "KEITARO_API_KEY must not be empty.",
                details={"field": "keitaro_api_key"},
            )

        if timeout_seconds <= 0:
            raise ConfigurationError(
                "KEITARO_TIMEOUT_SECONDS must be greater than zero.",
                details={"field": "keitaro_timeout_seconds"},
            )

        # Ensure trailing slash so relative paths preserve any base path such as /admin_api/v1.
        self._base_url = cleaned_url.rstrip("/") + "/"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Api-Key": secret_value,
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    def __repr__(self) -> str:
        return f"KeitaroClient(base_url={self._base_url!r})"

    @property
    def base_url(self) -> str:
        """Return the normalized base URL ending with a trailing slash."""
        return self._base_url

    async def aclose(self) -> None:
        """Close the underlying HTTPX AsyncClient connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: object | None = None,
    ) -> object:
        """Execute a relative Keitaro HTTP request and map transport/HTTP errors."""
        # Strip leading slash so httpx resolves against the full base_url path (/admin_api/v1/).
        relative_path = path.lstrip("/")

        try:
            response = await self._client.request(
                method=method,
                url=relative_path,
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Keitaro API timeout on %s %s", method, relative_path)
            raise ExternalServiceTimeoutError(
                f"Keitaro API request timed out on {method} {relative_path}.",
                details={"method": method, "path": relative_path},
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Keitaro API transport error on %s %s: %s",
                method,
                relative_path,
                type(exc).__name__,
            )
            raise ExternalServiceError(
                f"Keitaro API transport failure on {method} {relative_path}.",
                details={
                    "method": method,
                    "path": relative_path,
                    "error_type": type(exc).__name__,
                },
            ) from exc

        if not response.is_success:
            message, details = _parse_keitaro_error(response, method=method, path=relative_path)
            logger.warning(
                "Keitaro API returned HTTP %s on %s %s",
                response.status_code,
                method,
                relative_path,
            )
            raise ExternalServiceError(message, details=details)

        try:
            return response.json()
        except ValueError as exc:
            logger.warning("Keitaro API returned non-JSON body on %s %s", method, relative_path)
            raise ExternalServiceError(
                f"Keitaro API returned invalid JSON on {method} {relative_path}.",
                details={"method": method, "path": relative_path},
            ) from exc

    async def get_domains(self) -> list[KeitaroDomain]:
        """Fetch all domains configured in Keitaro."""
        raw = await self._request_json("GET", "domains")
        return _validate_with_adapter(_DOMAINS_ADAPTER, raw, method="GET", path="domains")

    async def get_campaign_groups(self) -> list[KeitaroCampaignGroup]:
        """Fetch campaign groups via GET groups?type=campaigns."""
        raw = await self._request_json("GET", "groups", params={"type": "campaigns"})
        return _validate_with_adapter(_GROUPS_ADAPTER, raw, method="GET", path="groups")

    async def get_traffic_sources(self) -> list[KeitaroTrafficSource]:
        """Fetch all traffic sources configured in Keitaro."""
        raw = await self._request_json("GET", "traffic_sources")
        return _validate_with_adapter(_SOURCES_ADAPTER, raw, method="GET", path="traffic_sources")

    async def search_offers(self, query: str | None = None) -> list[KeitaroOffer]:
        """Fetch offers from Keitaro and filter by ID or name case-insensitively."""
        raw = await self._request_json("GET", "offers")
        offers = _validate_with_adapter(_OFFERS_ADAPTER, raw, method="GET", path="offers")
        if query is None:
            return offers
        normalized = query.strip().casefold()
        if not normalized:
            return offers
        return [
            offer
            for offer in offers
            if normalized in str(offer.id) or normalized in offer.name.casefold()
        ]

    async def create_campaign(self, payload: KeitaroCreateCampaignRequest) -> KeitaroCampaign:
        """Create a new campaign in Keitaro via POST campaigns."""
        raw = await self._request_json(
            "POST",
            "campaigns",
            json_body=payload.model_dump(exclude_none=True),
        )
        return _validate_model(KeitaroCampaign, raw, method="POST", path="campaigns")

    async def create_stream(self, payload: KeitaroCreateStreamRequest) -> KeitaroStream:
        """Create a new stream in Keitaro via POST streams."""
        raw = await self._request_json(
            "POST",
            "streams",
            json_body=payload.model_dump(by_alias=True, exclude_none=True),
        )
        return _validate_model(KeitaroStream, raw, method="POST", path="streams")

    async def get_campaign_streams(self, campaign_id: int) -> list[KeitaroStream]:
        """Fetch all streams for a given Keitaro campaign via GET campaigns/{id}/streams."""
        _validate_positive_id(campaign_id, field_name="campaign_id")
        path = f"campaigns/{campaign_id}/streams"
        raw = await self._request_json("GET", path)
        return _validate_with_adapter(_STREAMS_ADAPTER, raw, method="GET", path=path)

    async def update_stream_offers(
        self,
        stream_id: int,
        offers: Sequence[KeitaroStreamOfferItem],
    ) -> KeitaroStream:
        """Update a stream's offer allocations via PUT streams/{id}."""
        _validate_positive_id(stream_id, field_name="stream_id")
        body = KeitaroUpdateStreamOffersRequest(offers=list(offers))
        path = f"streams/{stream_id}"
        raw = await self._request_json("PUT", path, json_body=body.model_dump())
        return _validate_model(KeitaroStream, raw, method="PUT", path=path)
