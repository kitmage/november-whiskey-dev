from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time

from november_whiskey.config import HubSpotConfig
from november_whiskey.exceptions import HubSpotAPIError
from november_whiskey.utils.validation import normalize_email

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.hubapi.com"


@dataclass(frozen=True)
class SignalContact:
    contactId: str
    email: str
    fullName: str
    openCount: int


class HubSpotClient:
    def __init__(self, token: str, timeout: int = 30) -> None:
        self.timeout = timeout
        import requests
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def request(self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        for attempt in range(4):
            response = self.session.request(method, url, params=params, json=json_body, timeout=self.timeout)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                sleep_for = 0.3 * (2 ** attempt)
                time.sleep(sleep_for)
                continue
            if not response.ok:
                if method.upper() == "PATCH" and path.startswith("/crm/v3/objects/contacts/") and response.status_code == 403:
                    LOGGER.debug(
                        "Ignoring HubSpot 403 for contact PATCH %s; continuing without contact property update.",
                        path,
                    )
                    return {"ignored": True, "status": response.status_code}
                raise HubSpotAPIError(f"HubSpot {method} {path} failed ({response.status_code})")
            return response.json()
        raise HubSpotAPIError(f"HubSpot {method} {path} failed after retries")


def find_signal_contacts(
    client: HubSpotClient,
    config: HubSpotConfig,
    *,
    campaign_id: str | None = None,
    list_id: str | None = None,
    lookback_hours: int | None = None,
    signal_threshold: int | None = None,
) -> list[SignalContact]:
    campaign_id = campaign_id or config.campaign_id
    list_id = list_id or config.list_id
    lookback_hours = lookback_hours if lookback_hours is not None else config.lookback_window_hours
    signal_threshold = signal_threshold if signal_threshold is not None else config.signal_threshold

    lookback_ts = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp() * 1000)

    email_ids: list[str] = []
    after = None
    while True:
        params = {"limit": 100, **({"after": after} if after else {})}
        data = client.request("GET", f"/marketing/v3/campaigns/{campaign_id}/assets/MARKETING_EMAIL", params=params)
        results = data.get("results", [])
        for asset in results:
            if asset.get("id"):
                email_ids.append(str(asset["id"]))
        after = (data.get("paging", {}).get("next", {}) or {}).get("after")
        if not after:
            break

    opens_by_recipient: dict[str, dict[str, int]] = {}
    open_sources: dict[str, list[dict[str, str | int]]] = {}
    for email_id in email_ids:
        meta = client.request("GET", f"/marketing/v3/emails/{email_id}")
        campaign_ids = set(meta.get("allEmailCampaignIds", []))
        if meta.get("primaryEmailCampaignId"):
            campaign_ids.add(meta.get("primaryEmailCampaignId"))
        for ecid in campaign_ids:
            offset = None
            while True:
                params = {
                    "appId": config.app_id,
                    "emailCampaignId": ecid,
                    "eventType": "OPEN",
                    "excludeFilteredEvents": "true",
                    "limit": 1000,
                    **({"offset": offset} if offset else {}),
                }
                events = client.request("GET", "/email/public/v1/events", params=params)
                for ev in events.get("events", []):
                    created = ev.get("created")
                    recipient = normalize_email(ev.get("recipient") or "")
                    if isinstance(created, (int, float)) and created >= lookback_ts and recipient:
                        campaign_id_key = str(ecid)
                        opens_by_recipient.setdefault(recipient, {})
                        opens_by_recipient[recipient][campaign_id_key] = opens_by_recipient[recipient].get(campaign_id_key, 0) + 1
                        open_sources.setdefault(recipient, []).append(
                            {
                                "emailId": str(email_id),
                                "emailCampaignId": campaign_id_key,
                                "created": int(created),
                            }
                        )
                if not events.get("hasMore"):
                    break
                offset = events.get("offset")
                if not offset:
                    break

    contact_ids: list[str] = []
    after = None
    while True:
        members = client.request("GET", f"/crm/v3/lists/{list_id}/memberships", params={"limit": 100, **({"after": after} if after else {})})
        results = members.get("results", [])
        contact_ids.extend(str(item["recordId"]) for item in results if item.get("recordId"))
        after = (members.get("paging", {}).get("next", {}) or {}).get("after")
        if not after:
            break

    contacts = []
    for i in range(0, len(contact_ids), 100):
        payload = {
            "properties": [config.property_name, "email", "firstname", "lastname"],
            "inputs": [{"id": cid} for cid in contact_ids[i : i + 100]],
        }
        batch = client.request("POST", "/crm/v3/objects/contacts/batch/read", json_body=payload)
        contacts.extend(batch.get("results", []))

    eligible_by_email: dict[str, tuple[str, str]] = {}
    for c in contacts:
        props = c.get("properties", {}) or {}
        pci_val = str(props.get(config.property_name, "")).lower()
        if pci_val in {"pci_completed"}:
            continue
        email = normalize_email(props.get("email") or "")
        if not email:
            continue
        full_name = (f"{(props.get('firstname') or '').strip()} {(props.get('lastname') or '').strip()}").strip() or email
        eligible_by_email[email] = (str(c.get("id")), full_name)

    out: list[SignalContact] = []
    not_in_list_count = 0
    below_threshold_count = 0
    for email, campaign_counts in sorted(opens_by_recipient.items()):
        if email not in eligible_by_email:
            not_in_list_count += 1
            continue
        trigger_campaign_id, count = max(campaign_counts.items(), key=lambda item: item[1])
        if count < signal_threshold:
            below_threshold_count += 1
            continue
        contact_id, full_name = eligible_by_email[email]
        LOGGER.debug(
            "Signal match recipientEmail=%s campaignOpenCounts=%s triggerEmailCampaignId=%s openCount=%d sources=%s",
            email,
            campaign_counts,
            trigger_campaign_id,
            count,
            open_sources.get(email, []),
        )
        out.append(SignalContact(contactId=contact_id, email=email, fullName=full_name, openCount=count))
    LOGGER.debug(
        "Signal finder summary campaignId=%s listId=%s lookbackHours=%d threshold=%d campaignEmails=%d recipientsWithOpens=%d eligibleContacts=%d belowThreshold=%d notInList=%d signalContacts=%d",
        campaign_id,
        list_id,
        lookback_hours,
        signal_threshold,
        len(email_ids),
        len(opens_by_recipient),
        len(eligible_by_email),
        below_threshold_count,
        not_in_list_count,
        len(out),
    )
    return out
