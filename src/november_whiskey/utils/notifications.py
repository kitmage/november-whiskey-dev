from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def send_discord_webhook(webhook_url: str, content: str, timeout_seconds: float = 10.0) -> bool:
    import requests

    payload = {"content": content}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "november-whiskey/1.0 (+https://github.com/kitmage/november-whiskey-dev)",
        "Accept": "application/json",
    }
    try:
        response = requests.post(webhook_url, headers=headers, data=json.dumps(payload), timeout=timeout_seconds)
        if response.ok:
            return True
        logger.warning(
            "Discord webhook returned non-success status: %s body=%s",
            response.status_code,
            (response.text or "")[:300],
        )
        return False
    except requests.RequestException as exc:
        logger.warning("Failed to send Discord webhook notification: %s", exc)
        return False
    except Exception as exc:  # defensive to avoid workflow interruption
        logger.warning("Unexpected Discord webhook error: %s", exc)
        return False
