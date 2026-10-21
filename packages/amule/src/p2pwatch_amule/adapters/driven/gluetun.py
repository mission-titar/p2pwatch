"""`forwarded_port`: gluetun's forwarded port, or None on any failure, never an exception."""

import http.client
import json
import urllib.request

from p2pwatch_amule.ports.driven.logger import Logger


def forwarded_port(control_url: str, logger: Logger) -> int | None:
    """`GET <control_url>/v1/portforward` → `{"port": N}`; None unless N is a TCP port."""
    url = control_url.rstrip("/") + "/v1/portforward"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read()
    except (OSError, http.client.HTTPException) as error:
        # URLError, HTTPError and timeouts are OSErrors; a garbled reply is an HTTPException.
        logger.warning("gluetun's control server is unavailable (%s)", error)
        return None
    try:
        port = json.loads(body).get("port")
    except (ValueError, AttributeError):
        port = None
    if not (type(port) is int and 0 < port <= 65535):
        logger.warning("gluetun reports no forwarded port (%r)", body[:100])
        return None
    return port
