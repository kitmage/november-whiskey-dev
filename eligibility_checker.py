import os
import sys
import requests
from datetime import datetime, timedelta, timezone

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")

LIST_ID = 677  # HubSpot segment/list ID
PROPERTY_NAME = "do_not_send_pci"

# Campaigns to consider for replies
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


# ---------------------------------------------------------
# Library hook: map contacts to "has replies" based on campaigns
# ---------------------------------------------------------

def get_reply_flags_for_contacts(contact_emails, campaign_ids, days_back=30):
    """
    Library stub: For each email in contact_emails, return a boolean flag
    indicating whether that contact has > 0 replies to any of the given
    campaign_ids in the last `days_back` days.

    Return format:
        { "email1@example.com": True, "email2@example.com": False, ... }

    IMPLEMENTATION NEEDED:
      - You can fill this in using:
          * a data export from HubSpot
          * a separate integration you trust
          * or, once HubSpot support provides a working events/analytics endpoint
            for replies in your portal, call it here.

    For now, this stub returns an empty dict (no one has replies).
    """
    # Example of how you might implement once you have a working endpoint:
    #
    # end_dt = datetime.now(timezone.utc)
    # start_dt = end_dt - timedelta(days=days_back)
    # start_ts = int(start_dt.timestamp() * 1000)
    # end_ts = int(end_dt.timestamp() * 1000)
    #
    # ... call your endpoint, fill reply_flags ...
    #
    reply_flags = {email.lower(): False for email in contact_emails if email}
    return reply_flags


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

    # 2) Build email list for eligible contacts
    eligible_emails = []
    for c in PCI_ELIGIBLE:
        email = (c.get("properties", {}) or {}).get("email")
        if email:
            eligible_emails.append(email.lower())

    # 3) Get reply flags per email for the given campaigns
    reply_flags = get_reply_flags_for_contacts(
        contact_emails=eligible_emails,
        campaign_ids=CAMPAIGN_IDS,
        days_back=30,
    )

    # 4) Second pass: move eligible contacts with replies into ineligible
    NEW_ELIGIBLE = []
    for contact in PCI_ELIGIBLE:
        props = contact.get("properties", {}) or {}
        email = (props.get("email") or "").lower()

        has_replied = reply_flags.get(email, False)

        if has_replied:
            PCI_INELIGIBLE.append(contact)
        else:
            NEW_ELIGIBLE.append(contact)

    PCI_ELIGIBLE = NEW_ELIGIBLE

    # 5) Print the two lists (id + email)
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
