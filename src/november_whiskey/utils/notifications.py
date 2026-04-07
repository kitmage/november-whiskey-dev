from __future__ import annotations

import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def send_discord_webhook(webhook_url: str, content: str, timeout_seconds: float = 10.0) -> bool:
    payload = json.dumps({"content": content}).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 204)
            if 200 <= status < 300:
                return True
            logger.warning("Discord webhook returned non-success status: %s", status)
            return False
    except URLError as exc:
        logger.warning("Failed to send Discord webhook notification: %s", exc)
        return False
