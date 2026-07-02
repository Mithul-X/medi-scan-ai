"""
Custom exception hierarchy.

Every exception here carries an HTTP status code and a machine-readable
`code` string, so the global handler in app/main.py can turn any of these
into a consistent JSON error shape without per-route try/except blocks.
"""

from __future__ import annotations


class MediScanError(Exception):
    """Base class for all application-raised errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedFileTypeError(MediScanError):
    status_code = 415
    code = "unsupported_file_type"


class FileTooLargeError(MediScanError):
    status_code = 413
    code = "file_too_large"


class FileProcessingError(MediScanError):
    status_code = 422
    code = "file_processing_failed"


class AllProvidersExhaustedError(MediScanError):
    """Raised when Gemini and every OpenRouter fallback model have failed."""

    status_code = 503
    code = "llm_providers_exhausted"


class ProviderRateLimitedError(MediScanError):
    """Raised internally between providers — usually caught by the router,
    not surfaced to clients unless every fallback also rate-limits."""

    status_code = 429
    code = "provider_rate_limited"


class ReportParsingError(MediScanError):
    status_code = 502
    code = "report_parsing_failed"


class SessionNotFoundError(MediScanError):
    status_code = 404
    code = "session_not_found"


class InvalidRequestError(MediScanError):
    status_code = 400
    code = "invalid_request"
