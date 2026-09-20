#!/usr/bin/env python3
"""Minimal Unipol apphub client, to answer the open questions in docs/FINDINGS.md.

Reads credentials from the environment so nothing lands in shell history:

    export UNIPOL_USERNAME=...
    export UNIPOL_PASSWORD=...
    export UNIPOL_IBM_CLIENT_ID=...       # from a capture, see docs/CAPTURE.md
    export UNIPOL_IBM_CLIENT_SECRET=...
    export UNIPOL_TENANT=...              # optional

    ./tools/probe.py contracts
    ./tools/probe.py position AB123CD
    ./tools/probe.py position AB123CD --update
    ./tools/probe.py usage AB123CD

Nothing here writes to the API. The only state-changing call the app makes on
these paths is `?update=true`, which costs one unit of the daily quota, so it is
behind an explicit flag.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import requests

BASE = "https://apphub.unipolsai.it/hub/"
APP_VERSION = "6.3.18"
APP_BUILD = "42642"


class Unipol:
    def __init__(self, username: str, password: str, client_id: str | None,
                 client_secret: str | None, tenant: str | None,
                 impersonate_app: bool = False):
        self.username = username
        self.password = password
        self.token: str | None = None
        self.expires_at: float = 0.0
        self.s = requests.Session()

        # Default to an honest UA. The app's own string is available behind a
        # flag in case the gateway turns out to reject anything else.
        if impersonate_app:
            ua = (f"UnipolSaiApp/{APP_VERSION} Version Code {APP_BUILD} "
                  "(Android 14; Pixel 6; Google oriole;)")
        else:
            ua = "ha-unipolsai/0.1 (+https://github.com/fezvrasta/ha-unipolsai)"

        self.s.headers.update({
            "User-Agent": ua,
            "source": "mobile",
            "x-unipol-canale": "APP",
        })
        if client_id:
            self.s.headers["x-ibm-client-id"] = client_id
        if client_secret:
            self.s.headers["x-ibm-client-secret"] = client_secret
        if tenant:
            self.s.headers["x-unipol-tenant"] = tenant

    def _headers(self, telematics: bool = False) -> dict[str, str]:
        h = {"x-unipol-requestid": str(uuid.uuid4()), "accept": "application/json"}
        if telematics:
            # The @HeaderMap parameter on every TelematicsAutoService method.
            # Required; the endpoints misbehave without them.
            h["service_type"] = "Vehicle"
            h["company_id"] = "unipolsai"
        return h

    def login(self) -> None:
        r = self.s.post(
            BASE + "login",
            data={"username": self.username, "password": self.password},
            headers=self._headers(),
            timeout=30,
        )
        r.raise_for_status()
        jwt = r.json()["JWT"]
        self.token = jwt["token"]
        # The app refreshes 120s early; mirror that.
        self.expires_at = time.time() + int(jwt.get("expires_in", 3600)) - 120
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        print(f"logged in, identity={jwt.get('identity')} "
              f"expires_in={jwt.get('expires_in')}", file=sys.stderr)

    def _ensure_token(self) -> None:
        if self.token is None:
            self.login()
        elif time.time() > self.expires_at:
            r = self.s.post(BASE + "login/refresh", headers=self._headers(), timeout=30)
            if r.status_code >= 400:
                self.login()
            else:
                jwt = r.json()["JWT"]
                self.token = jwt["token"]
                self.expires_at = time.time() + int(jwt.get("expires_in", 3600)) - 120
                self.s.headers["Authorization"] = f"Bearer {self.token}"

    def get(self, path: str, **params):
        self._ensure_token()
        tele = "/telematici/" in path
        r = self.s.get(BASE + path, params=params or None,
                       headers=self._headers(tele), timeout=30)
        # 403003 "No credential" means the F5 session went away, not just the
        # JWT. Re-login rebuilds both, since the cookies ride on self.s.
        if r.status_code in (401, 403):
            self.login()
            r = self.s.get(BASE + path, params=params or None,
                           headers=self._headers(tele), timeout=30)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _plate(plate: str) -> str:
        """The API wants the plate country-prefixed: AB123CD -> IT-AB123CD."""
        plate = plate.strip().upper().replace(" ", "")
        return plate if "-" in plate else f"IT-{plate}"

    # --- endpoints -------------------------------------------------------

    def contracts(self):
        return self.get("api/priv/telematici/contratti/v1/contracts/myTelematicContracts")

    def position(self, plate: str, update: bool = False):
        # update is NOT optional: omitting it returns HTTP 400 with no body.
        return self.get(
            f"api/priv/telematici/auto/v1/vehicles/{self._plate(plate)}/lastPosition",
            update="true" if update else "false",
        )

    def usage(self, plate: str, date_range: str = "g"):
        return self.get(
            f"api/priv/telematici/auto/v1/vehicles/{self._plate(plate)}/vehicleUsages",
            dateRange=date_range,
        )

    def crashes(self, plate: str):
        return self.get(f"api/priv/telematici/auto/v1/vehicles/{self._plate(plate)}/crashes")

    def vas(self, plate: str):
        return self.get(f"api/priv/telematici/auto/v1/vehicles/{self._plate(plate)}/vehicleVAS")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command",
                   choices=["contracts", "position", "usage", "crashes", "vas"])
    p.add_argument("plate", nargs="?", help="vehicle plate, uppercase")
    p.add_argument("--update", action="store_true",
                   help="force the box to report a fresh fix (costs one daily quota unit)")
    p.add_argument("--range", default="g", help="dateRange for usage: g (whole contract) or t (needs dates)")
    p.add_argument("--impersonate-app", action="store_true",
                   help="send the app's own User-Agent instead of ours")
    args = p.parse_args()

    user = os.environ.get("UNIPOL_USERNAME")
    pw = os.environ.get("UNIPOL_PASSWORD")
    if not user or not pw:
        print("set UNIPOL_USERNAME and UNIPOL_PASSWORD", file=sys.stderr)
        return 2

    if args.command != "contracts" and not args.plate:
        print(f"{args.command} needs a plate", file=sys.stderr)
        return 2

    c = Unipol(
        user, pw,
        os.environ.get("UNIPOL_IBM_CLIENT_ID"),
        os.environ.get("UNIPOL_IBM_CLIENT_SECRET"),
        os.environ.get("UNIPOL_TENANT"),
        impersonate_app=args.impersonate_app,
    )

    if args.command == "contracts":
        out = c.contracts()
    elif args.command == "position":
        out = c.position(args.plate, update=args.update)
        loc = out.get("lastPosition") or {}
        q = loc.get("dailyFruitions") or {}
        if q:
            print(f"quota: {q.get('current')}/{q.get('max')}", file=sys.stderr)
        if loc.get("pendingRequest"):
            print("pendingRequest=true: the fix is still being fetched, poll again "
                  "WITHOUT --update", file=sys.stderr)
    elif args.command == "usage":
        out = c.usage(args.plate, args.range)
    elif args.command == "crashes":
        out = c.crashes(args.plate)
    else:
        out = c.vas(args.plate)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
