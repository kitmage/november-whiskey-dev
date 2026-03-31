import os
import sys
import time
from datetime import datetime, timedelta
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")

LIST_ID = 677  # HubSpot segment/list ID
PROPERTY_NAME = "do_not_send_pci"

# New: Campaign IDs
CAMPAIGN_IDS = {"25347176"}

BASE_URL = "https://api.hubapi.com"

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}


def get_list_contacts(list_id, properties=None):
    """
    Returns a list of contact records (dicts) from a list/segment.
    Uses v3 CRM Lists API + Batch read for properties.
    """
    # 1) Get all contact IDs in the list
    endpoint = f"{BASE_URL}/crm/v3/lists/{list_id}/memberships"
    after = None
    contact_ids = []

    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after

        resp = requests.get(endpoint, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            # Your structure: {"membershipTimestamp": "...", "recordId": "4585..."}
            contact_id = item.get("recordId")
            if not contact_id:
                raise RuntimeError(f"Could not locate contact id in membership item: {item}")
            contact_ids.append(str(contact_id))

        paging = data.get("paging", {})
        next_link = paging.get("next", {})
        after = next_link.get("after")
        if not after:
            break

    if not contact_ids:
        return []

    # 2) Batch read contacts to get properties
    contacts = []
    batch_endpoint = f"{BASE_URL}/crm/v3/objects/contacts/batch/read"
    batch_size = 100

    for i in range(0, len(contact_ids), batch_size):
        batch_ids = contact_ids[i : i + batch_size]
        payload = {
            "properties": properties or [],
            "inputs": [{"id": cid} for cid in batch_ids],
        }
        resp = requests.post(batch_endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        contacts.extend(data.get("results", []))

    return contacts


def get_reply_emails_for_campaigns(campaign_ids, days_back=30):
    """
    For each campaign ID, fetch REPLY events from the past `days_back` days
    and return a set of all unique recipient email addresses that replied.
    Uses legacy Email Events API: /email/public/v1/events
    """
    replied_emails = set()

    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days_back)

    # Email Events API expects ms since epoch (UTC)
    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)

    for campaign_id in campaign_ids:
        offset = 0
        has_more = True

        while has_more:
            params = {
                "campaignId": campaign_id,
                "eventType": "REPLY",
                "startTimestamp": start_ts,
                "endTimestamp": end_ts,
                "limit": 1000,
                "offset": offset,
            }

            resp = requests.get(
                f"{BASE_URL}/email/public/v1/events",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            events = data.get("events", [])
            for ev in events:
                # Typical fields: recipient, email, etc. We'll use `recipient`
                email = ev.get("recipient") or ev.get("email")
                if email:
                    replied_emails.add(email.lower())

            has_more = data.get("hasMore", False)
            offset = data.get("offset", 0)

            # Simple safety to avoid hammering
            time.sleep(0.1)

    return replied_emails


def main():
    # 1) Get all contacts in the list with do_not_send_pci + email
    contacts = get_list_contacts(LIST_ID, properties=[PROPERTY_NAME, "email"])

    PCI_ELIGIBLE = []
    PCI_INELIGIBLE = []

    for contact in contacts:
        props = contact.get("properties", {}) or {}
        do_not_send_pci_val = props.get(PROPERTY_NAME)

        is_ineligible = str(do_not_send_pci_val).lower() == "true"

        if is_ineligible:
            PCI_INELIGIBLE.append(contact)
        else:
            PCI_ELIGIBLE.append(contact)

    # 2) Build set of emails that replied to specified campaigns in past 30 days
    replied_emails = get_reply_emails_for_campaigns(CAMPAIGN_IDS, days_back=30)

    # 3) Second pass: move eligible contacts with replies into ineligible
    NEW_ELIGIBLE = []
    for contact in PCI_ELIGIBLE:
        props = contact.get("properties", {}) or {}
        email = (props.get("email") or "").lower()

        if email and email in replied_emails:
            PCI_INELIGIBLE.append(contact)
        else:
            NEW_ELIGIBLE.append(contact)

    PCI_ELIGIBLE = NEW_ELIGIBLE

    # 4) Print the two lists (id + email)
    print("=== PCI_ELIGIBLE ===")
    for c in PCI_ELIGIBLE:
        cid = c.get("id")
        email = c.get("properties", {}).get("email")
        print(f"id={cid}, email={email}")

    print("\n=== PCI_INELIGIBLE ===")
    for c in PCI_INELIGIBLE:
        cid = c.get("id")
        email = c.get("properties", {}).get("email")
        print(f"id={cid}, email={email}")


if __name__ == "__main__":
    if not HUBSPOT_TOKEN:
        print("HUBSPOT_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    main()
