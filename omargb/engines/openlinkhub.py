"""Corsair hubs driven by the OpenLinkHub service.

The packaged `openlinkhub` binary panics unless it is the system service.
That service listens on 127.0.0.1:27003. `/api/color/all` is the same call the
web UI uses for "apply this colour to every hub device".
"""

import json
import urllib.error
import urllib.request

from omargb.catalog import Target
from omargb.theme import Theme

ENDPOINT = "http://127.0.0.1:27003/api/color/all"


class OpenLinkHub:
    name = "openlinkhub"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str | None:
        if not targets:
            return None
        labels = ", ".join(target.entry.name for target in targets)
        colour = theme.solid
        if dry_run:
            return f"openlinkhub dry-run {labels} {theme.solid_hex()}"
        body = json.dumps(
            {
                "color": {
                    "red": colour[0],
                    "green": colour[1],
                    "blue": colour[2],
                    "brightness": 1,
                }
            }
        ).encode()
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = response.read().decode()
        except (urllib.error.URLError, TimeoutError) as error:
            return f"openlinkhub unavailable ({error})"
        if '"status":1' not in payload and '"status": 1' not in payload:
            return f"openlinkhub rejected the colour ({payload[:160]})"
        return f"openlinkhub {labels} {theme.solid_hex()}"
