"""Exceptions raised by pyunipolsai."""

from __future__ import annotations


class UnipolSaiError(Exception):
    """Base error, also raised for API-level `operationResult` failures."""


class UnipolSaiConnectionError(UnipolSaiError):
    """The API could not be reached."""


class UnipolSaiAuthError(UnipolSaiError):
    """Credentials were rejected, or the session could not be re-established."""
