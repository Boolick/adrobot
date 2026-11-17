"""Custom domain and infrastructure exception hierarchy."""


class AdrobotError(Exception):
    """Base exception for all Adrobot application errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ADROBOT_ERROR",
        status_code: int = 500,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class ConfigurationError(AdrobotError):
    """Raised when required runtime configuration is missing or invalid."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )


class DomainValidationError(AdrobotError):
    """Raised when a domain invariant or business rule fails validation."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="DOMAIN_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class ResourceNotFoundError(AdrobotError):
    """Raised when a requested local or remote resource does not exist."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="RESOURCE_NOT_FOUND",
            status_code=404,
            details=details,
        )


class ResourceConflictError(AdrobotError):
    """Raised when an operation conflicts with existing resource state."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="RESOURCE_CONFLICT",
            status_code=409,
            details=details,
        )


class ExternalServiceError(AdrobotError):
    """Raised when an upstream integration returns an unexpected failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "EXTERNAL_SERVICE_ERROR",
        status_code: int = 502,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status_code,
            details=details,
        )


class ExternalServiceTimeoutError(ExternalServiceError):
    """Raised when an upstream integration request times out."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="EXTERNAL_SERVICE_TIMEOUT",
            status_code=504,
            details=details,
        )


NotFoundError = ResourceNotFoundError
ConflictError = ResourceConflictError
