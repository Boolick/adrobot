"""Shared Pydantic v2 API response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health check response payload."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class ErrorBody(BaseModel):
    """Structured error payload returned by global exception handlers."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    details: dict[str, str] | None = None


class ErrorResponse(BaseModel):
    """Top-level JSON error envelope."""

    model_config = ConfigDict(frozen=True)

    error: ErrorBody
