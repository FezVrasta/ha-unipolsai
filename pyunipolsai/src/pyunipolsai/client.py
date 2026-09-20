"""Async client for the Unipol apphub telematics API."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Self

import aiohttp

from .const import (
    BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    DEFAULT_USER_AGENT,
)
from .exceptions import (
    UnipolSaiAuthError,
    UnipolSaiConnectionError,
    UnipolSaiError,
    UnipolSaiNotFoundError,
)
from .models import (
    Crash,
    Notification,
    Position,
    Service,
    UsageStats,
    Vehicle,
    normalise_plate,
)

_LOGGER = logging.getLogger(__name__)


class UnipolSaiClient:
    """Talks to `apphub.unipolsai.it`.

    Three things about this API are not guessable from the app's code and
    will produce confusing failures if changed:

    * **The bearer token alone is not enough.** Login also sets F5 BIG-IP
      session cookies (`MRHSession`, `JSESSIONID`, `TS*`) that must ride on
      every subsequent request. Everything therefore shares one
      cookie-persisting session, and a 403 means "log in again", not
      "refresh the token". A stored long-lived token is not a workable
      auth model.
    * **Plates are country-prefixed** in the path: `IT-AB123CD`.
    * **Telematics calls need `service_type` and `company_id` headers.**

    Usage::

        async with UnipolSaiClient(username="...", password="...") as client:
            for vehicle in await client.async_get_vehicles():
                print(await client.async_get_position(vehicle))
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        session: aiohttp.ClientSession | None = None,
        client_id: str = DEFAULT_CLIENT_ID,
        client_secret: str = DEFAULT_CLIENT_SECRET,
        tenant: str = DEFAULT_TENANT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """Create a client.

        `session` must have a cookie jar; if you pass one, don't share it with
        unrelated traffic. Omit it and the client owns its own.
        """
        self._username = username
        self._password = password
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant = tenant
        self._user_agent = user_agent
        self._session = session
        self._owns_session = session is None
        self._token: str | None = None

    async def __aenter__(self) -> Self:
        """Enter the context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the session on exit."""
        await self.async_close()

    async def async_close(self) -> None:
        """Close the session, if this client created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    # -- plumbing ---------------------------------------------------------

    @property
    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self, telematics: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
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

    async def async_login(self) -> None:
        """Authenticate. Also establishes the F5 cookies on the session."""
        self._token = None
        try:
            async with self._http.post(
                f"{BASE_URL}login",
                data={"username": self._username, "password": self._password},
                headers=self._headers(),
            ) as resp:
                if resp.status in (401, 403):
                    raise UnipolSaiAuthError("username or password rejected")
                resp.raise_for_status()
                body = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UnipolSaiConnectionError(f"login failed: {err}") from err

        # The JSON key is "token", even though the app's field is called value.
        token = ((body or {}).get("JWT") or {}).get("token")
        if not token:
            raise UnipolSaiAuthError("login returned no token")
        self._token = token

    async def _get(self, path: str, telematics: bool = False, **params: Any) -> dict:
        if self._token is None:
            await self.async_login()

        async def _do() -> tuple[int, Any]:
            async with self._http.get(
                BASE_URL + path,
                params=params or None,
                headers=self._headers(telematics),
            ) as resp:
                if resp.status in (401, 403):
                    return resp.status, None
                if resp.status == 404:
                    raise UnipolSaiNotFoundError(f"{path}: 404")
                resp.raise_for_status()
                return resp.status, await resp.json(content_type=None)

        try:
            status, body = await _do()
            if status in (401, 403):
                # 403003 "No credential" means the F5 session is gone, not
                # just the JWT, so only a full login fixes it.
                _LOGGER.debug("Re-authenticating after HTTP %s on %s", status, path)
                await self.async_login()
                status, body = await _do()
                if status in (401, 403):
                    raise UnipolSaiAuthError(f"still HTTP {status} after re-login")
        except UnipolSaiNotFoundError:
            raise
        except aiohttp.ClientError as err:
            raise UnipolSaiConnectionError(f"{path} failed: {err}") from err

        if isinstance(body, dict):
            result = body.get("operationResult") or {}
            if result.get("type") not in (0, None):
                raise UnipolSaiError(
                    f"{path}: {result.get('code')} {result.get('message')}"
                )
        return body or {}

    @staticmethod
    def _plate(vehicle: Vehicle | str) -> str:
        return (
            vehicle.api_plate
            if isinstance(vehicle, Vehicle)
            else normalise_plate(vehicle)
        )

    # -- endpoints --------------------------------------------------------

    async def async_get_vehicles(self, usable_only: bool = True) -> list[Vehicle]:
        """Vehicles with a telematics box.

        Empty sections come back as `codice` 404/404404 with "Contratti non
        trovati" inside an HTTP 200; that's a normal empty, not an error.
        """
        body = await self._get("api/priv/contesto-utente/v2/me/contrattiTelematici")
        contracts = (body.get("auto") or {}).get("contrattiAuto") or []
        vehicles = [v for c in contracts if (v := Vehicle.from_api(c))]
        return [v for v in vehicles if v.usable] if usable_only else vehicles

    async def async_get_position(
        self, vehicle: Vehicle | str, *, force_refresh: bool = False
    ) -> Position:
        """Last known position.

        `force_refresh` is **fire and forget**: it returns 200 immediately
        with the *old* position and `pending_request` False, then the flag
        goes true a few seconds later and the cycle takes about five minutes
        to resolve. It can resolve without the position changing, which is
        what a car parked with the engine off looks like, and that costs no
        quota. Compare `timestamp` against the pre-request value to tell
        success from give-up.

        Plain reads are free; only a forced refresh touches the daily quota.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/{self._plate(vehicle)}/lastPosition",
            telematics=True,
            # Required. Omitting it is HTTP 400 with an empty body.
            update="true" if force_refresh else "false",
        )
        return Position.from_api(body.get("lastPosition"))

    async def async_get_services(self, vehicle: Vehicle | str) -> dict[str, Service]:
        """Value-added services, keyed by name."""
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/{self._plate(vehicle)}/vehicleVAS",
            telematics=True,
        )
        return {
            s["serviceName"]: Service.from_api(s)
            for s in body.get("vehicleVAS") or []
            if s.get("serviceName")
        }

    async def async_get_notifications(
        self, vehicle: Vehicle | str, service: str
    ) -> list[Notification]:
        """Recent alert events for one service.

        In practice the API returns only the single most recent event despite
        the plural field name, so two events inside one poll interval collapse
        into one. Reading is free; a service's credits pay for having it on.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self._plate(vehicle)}/lastNotifications",
            telematics=True,
            vehicleVAS=service,
        )
        return [
            Notification.from_api(n)
            for n in body.get("serviceNotifications") or []
            if n.get("id")
        ]

    async def async_get_crashes(self, vehicle: Vehicle | str) -> list[Crash]:
        """Impacts the box has detected.

        Returned without the reconstruction: `samples` and `strengths` are
        empty here. Call `async_get_crash` with an id to fill them in.

        A detection is not a confirmed accident. Check `Crash.validated`
        before presenting one as though it were.

        Returns an empty list on a 404. The account this was written against
        answers 404 here rather than returning an empty list, and there is no
        way to tell from outside whether that means "no impacts on record" or
        "this contract has no crash detection". Either way there is nothing to
        report, so it is not treated as an error.
        """
        try:
            body = await self._get(
                f"api/priv/telematici/auto/v1/vehicles/{self._plate(vehicle)}/crashes",
                telematics=True,
            )
        except UnipolSaiNotFoundError:
            _LOGGER.debug("No crash record for this vehicle (404)")
            return []
        # Logged in full because this is the one shape in the library never
        # verified against real data. If these fields turn out wrong, this is
        # the evidence.
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("crashes raw: %s", body)
        return [c for raw in body.get("crashes") or [] if (c := Crash.from_api(raw))]

    async def async_get_crash(
        self, vehicle: Vehicle | str, crash_id: int | str
    ) -> Crash | None:
        """One impact in full, including the reconstructed track.

        `samples` is the per-point trace either side of the impact, each point
        carrying its accelerometer readings, and `Crash.climax` picks out the
        one the box marks as the moment of impact.
        """
        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self._plate(vehicle)}/crashes/{crash_id}",
            telematics=True,
        )
        # This endpoint returns the crash at the top level, not wrapped in a list.
        return Crash.from_api(body)

    async def async_get_usage(
        self,
        vehicle: Vehicle | str,
        *,
        date_range: str = "g",
        start: int | None = None,
        end: int | None = None,
    ) -> UsageStats:
        """Driving statistics. Free: this service needs no credits.

        `date_range` is a single letter, not a word. `g` is the whole contract
        period; `t` is a custom range and requires `start`/`end` as epoch
        **milliseconds** (ISO dates return HTTP 500). Anything else is
        rejected with `400100`.
        """
        params: dict[str, Any] = {"dateRange": date_range}
        if date_range == "t":
            if start is None or end is None:
                raise ValueError("date_range 't' requires start and end")
            params["startDate"] = start
            params["endDate"] = end

        body = await self._get(
            f"api/priv/telematici/auto/v1/vehicles/"
            f"{self._plate(vehicle)}/vehicleUsages",
            telematics=True,
            **params,
        )
        usages = body.get("vehicleUsages") or []
        return UsageStats.from_api(usages[0] if usages else {})
