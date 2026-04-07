from __future__ import annotations

from typing import Any

from november_whiskey.config import HubSpotConfig
from november_whiskey.exceptions import HubSpotAPIError
from .signal_finder import HubSpotClient


def extract_submission_data(event: dict[str, Any]) -> dict[str, Any]:
    fields = [{"name": "email", "value": event.get("email", "")}]
    for key in ("pci_datetime", "teams_join_url", "emailId", "emailCampaignId"):
        if event.get(key) is not None:
            fields.append({"name": key, "value": str(event[key])})
    return {"fields": fields}


def submit_contact_form(client: HubSpotClient, config: HubSpotConfig, event: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    payload = extract_submission_data(event)
    if dry_run:
        return {"dry_run": True, "payload": payload}
    endpoint = f"https://api.hsforms.com/submissions/v3/integration/submit/{config.portal_id}/{config.form_id}"
    response = client.session.post(endpoint, json=payload, timeout=client.timeout)
    if not response.ok:
        raise HubSpotAPIError(f"HubSpot form submit failed ({response.status_code})")
    return {"submitted": True, "status": response.status_code}
