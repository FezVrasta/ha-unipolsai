"""Client for the Unipol apphub telematics API.

Behaviour here is derived from docs/FINDINGS.md, which was verified against a
live account. The non-obvious parts, all of which will bite if changed:

* The bearer token alone is not enough. Login also sets F5 BIG-IP session
  cookies (MRHSession, JSESSIONID, TS*) that must ride on every request, so
  everything goes through one cookie-persisting session and a 403 means
  "log in again", not "refresh the token".
* Plates are country-prefixed in the path: IT-AB123CD.
* Telematics calls need service_type and company_id headers.
* `update` is a required query parameter on lastPosition.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import aiohttp

from .const import BASE_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class UnipolSaiError(Exception):
    """Base error."""


class UnipolSaiAuthError(UnipolSaiError):
    """Credentials rejected."""


class UnipolSaiApi:
    """Minimal async client for the endpoints the integration needs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        tenant: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant = tenant
        self._token: str | None = None

    # -- plumbing ---------------------------------------------------------

    @staticmethod
    def normalise_plate(plate: str) -> str:
        """AB123CD -> IT-AB123CD. A bare plate 404s."""
        plate = plate.strip().upper().replace(" ", "")
        return plate if "-" in plate else f"IT-{plate}"

    def _headers(self, telematics: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "source": "mobile",
            "accept": "application/json",
            "x-unipol-canale": "APP",
            "x-unipol-requestid": str(uuid.uuid4()),
            "x-ibm-client-id": self._client_id,
            "x-ibm-client-secret": self._client_secret,
            "x-unipol-tenant": self._tenant,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if telematics:
            # Fills the @HeaderMap on every TelematicsAutoService method.
            headers["service_type"] = "Vehicle"
            headers["company_id"] = "unipolsai"
        return headers

    async def login(self) -> None:
        """Form-POST login. Also establishes the F5 cookies on the session."""
        self._token = None
        try:
            async with self._session.post(
                f"{BASE_URL}login",
                data={"username": self._username, "password": self._password},
                headers=self._headers(),
            ) as resp:
                if resp.status in (401, 403):
                    raise UnipolSaiAuthError("username or password rejected")
                resp.raise_for_status()
                body = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UnipolSaiError(f"login failed: {err}") from err

        jwt = (body or {}).get("JWT") or {}
        # The JSON key is "token" even though the Kotlin field is called value.
        token = jwt.get("token")
        if not token:
            raise UnipolSaiAuthError("login returned no token")
        self._token = token

    async def _get(self, path: str, telematics: bool = False, **params: Any) -> dict:
        if self._token is None:
            await self.login()

        async def _do() -> tuple[int, Any]:
            async with self._session.get(
                BASE_URL + path,
                params=params or None,
                headers=self._headers(telematics),
            ) as resp:
                if resp.status in (401, 403):
                    return resp.status, None
                resp.raise_for_status()
                return resp.status, await resp.json(content_type=None)

        try:
            status, body = await _do()
            if status in (401, 403):
                # 403003 "No credential" means the F5 session went, not just
                # the JWT, so a full login is the only thing that fixes it.
                _LOGGER.debug("Re-authenticating after HTTP %s on %s", status, path)
                await self.login()
                status, body = await _do()
                if status in (401, 403):
                    raise UnipolSaiAuthError(f"still {status} after re-login")
        except aiohttp.ClientError as err:
            raise UnipolSaiError(f"{path} failed: {err}") from err

        if isinstance(body, dict):
            result = body.get("operationResult") or {}
            if result.get("type") not in (0, None):
                raise UnipolSaiError(
                    f"{path}: {result.get('code')} {result.get('message')}"
                )
        return body or {}

    # -- endpoints --------------------------------------------------------

    async def telematic_contracts(self) -> list[dict]:
        """Vehicles with a box on them.

        Sections report an empty result as codice 404/404404 with
        "Contratti non trovati" inside an HTTP 200, which is normal.
        """
        body = await self._get("api/priv/contesto-utente/v2/me/contrattiTelematici")
        auto = body.get("auto") or {}
        return auto.get("contrattiAuto") or []

    async def last_position(self, plate: str, update: bool = False) -> dict:
        """Current known position.

        update=true is fire and forget: it returns 200 with the *old* position
        and pendingRequest false, then the flag goes true a few seconds later.
        Never treat this response as the result of a forced refresh.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self.normalise_plate(plate)}/lastPosition",
            telematics=True,
            update="true" if update else "false",
        )
        return body.get("lastPosition") or {}

    async def vehicle_vas(self, plate: str) -> dict[str, dict]:
        """Value-added services, keyed by serviceName."""
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self.normalise_plate(plate)}/vehicleVAS",
            telematics=True,
        )
        return {s["serviceName"]: s for s in body.get("vehicleVAS") or []}

    async def last_notifications(self, plate: str, service: str) -> list[dict]:
        """Recent alert events for one VAS, newest first.

        `service` is a serviceName from vehicle_vas, e.g. engineOn. The
        credits on that service pay for having it switched on; reading the
        notifications it produced is a plain read.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self.normalise_plate(plate)}/lastNotifications",
            telematics=True,
            vehicleVAS=service,
        )
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("lastNotifications(%s) raw: %s", service, body)
        return body.get("serviceNotifications") or []

    async def vehicle_usages(self, plate: str) -> dict:
        """Driving statistics. Free: rangeStatistics needs no credits.

        dateRange is a single letter; g is the whole contract period. Distances
        are metres and times are seconds.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self.normalise_plate(plate)}/vehicleUsages",
            telematics=True,
            dateRange="g",
        )
        usages = body.get("vehicleUsages") or []
        return usages[0] if usages else {}
