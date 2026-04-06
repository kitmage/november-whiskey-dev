from __future__ import annotations

from typing import Any

from november_whiskey.config import HubSpotConfig
from november_whiskey.exceptions import HubSpotAPIError
from .signal_finder import HubSpotClient


def _build_contact_properties(event: dict[str, Any]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for key in ("pci_datetime", "teams_join_url"):
        value = event.get(key)
        if value is not None and str(value).strip():
            properties[key] = str(value)
    return properties


def _sync_contact_properties(client: HubSpotClient, email: str, properties: dict[str, str]) -> None:
    if not properties:
        return
    search_result = client.request(
        "POST",
        "/crm/v3/objects/contacts/search",
        json_body={
            "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
            "properties": ["email"],
            "limit": 1,
        },
    )
    results = search_result.get("results", [])
    if not results:
        raise HubSpotAPIError(f"HubSpot contact lookup failed for email: {email}")
    contact_id = str(results[0]["id"])
    client.request(
        "PATCH",
        f"/crm/v3/objects/contacts/{contact_id}",
        json_body={"properties": properties},
    )


def extract_submission_data(event: dict[str, Any]) -> dict[str, Any]:
    fields = [{"name": "email", "value": event.get("email", "")}]
    for key in ("openCount", "emailId", "emailCampaignId", "pci_datetime", "teams_join_url"):
        if event.get(key) is not None:
            fields.append({"name": key.lower(), "value": str(event[key])})
    return {"fields": fields}


def submit_contact_form(client: HubSpotClient, config: HubSpotConfig, event: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    payload = extract_submission_data(event)
    contact_properties = _build_contact_properties(event)
    if dry_run:
        return {"dry_run": True, "payload": payload, "properties": contact_properties}
    endpoint = f"https://api.hsforms.com/submissions/v3/integration/submit/{config.portal_id}/{config.form_id}"
    response = client.session.post(endpoint, json=payload, timeout=client.timeout)
    if not response.ok:
        raise HubSpotAPIError(f"HubSpot form submit failed ({response.status_code})")
    email = str(event.get("email", "")).strip()
    if email:
        _sync_contact_properties(client, email, contact_properties)
    return {"submitted": True, "status": response.status_code, "properties_updated": bool(contact_properties)}
