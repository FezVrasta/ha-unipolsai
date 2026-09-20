"""Exceptions raised by pyunipolsai."""

from __future__ import annotations


class UnipolSaiError(Exception):
    """Base error, also raised for API-level `operationResult` failures."""


class UnipolSaiConnectionError(UnipolSaiError):
    """The API could not be reached."""


class UnipolSaiAuthError(UnipolSaiError):
    """Credentials were rejected, or the session could not be re-established."""


class UnipolSaiNotFoundError(UnipolSaiError):
    """The endpoint answered 404.

    Worth its own type because this API uses 404 for "nothing here" as well as
    for "no such thing", and the two are not distinguishable from outside.
    """
