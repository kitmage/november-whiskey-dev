#!/usr/bin/env python3

import os
import time
import requests
from collections import defaultdict

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN", "$HUBSPOT_TOKEN")
BASE_URL = "https://api.hubapi.com"

# ----------------------------
# Config
# ----------------------------
LIST_ID = 677  # HubSpot segment/list ID

# The marketing email campaign IDs we care about (UI "emailCampaignId")
CAMPAIGN_IDS = {"25347176"}

# Optional: only count events since a given Unix ms timestamp (for opens)
START_TIMESTAMP_MS = None  # e.g. 1741392000000

# Time window for replies on CRM emails (ms since epoch)
# Set these around when the campaign went out
CAMPAIGN_SEND_START_MS = None  # e.g. 1774965000000
CAMPAIGN_SEND_END_MS = None    # e.g. 1775051400000

LIST_PAGE_LIMIT = 250
CONTACT_BATCH_SIZE = 100

SUPPRESSION_PROPERTY = "do_not_send_pci"
NOTE_OWNER_ID = os.getenv("HUBSPOT_USER_ID")

SUPPRESSION_NOTE_BODY = (
    'MikeBot noticed this contact has the "Block PCI" Property set to Yes/True, '
    "so the contact has been removed from the PCI Nurture Sequence."
)

def headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }

def get_json(url, params=None):
    resp = requests.get(url, headers=headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def post_json(url, payload):
    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def batch_chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]

# ----------------------------
# List memberships
# ----------------------------
def get_all_list_member_ids(list_id):
    member_ids = []
    after = None

    while True:
        params = {"limit": LIST_PAGE_LIMIT}
        if after:
            params["after"] = after

        url = f"{BASE_URL}/crm/v3/lists/{list_id}/memberships"
        data = get_json(url, params=params)

        for row in data.get("results", []):
            record_id = row.get("recordId")
            if record_id:
                member_ids.append(str(record_id))

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after:
            break

    return member_ids

# ----------------------------
# Notes for suppressed contacts
# ----------------------------
def associate_note_to_contact(note_id, contact_id):
    url = f"{BASE_URL}/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact"
    resp = requests.put(url, headers=headers(), timeout=30)
    if resp.status_code >= 400:
        print(f"[DEBUG] Association error body for note {note_id} -> contact {contact_id}: {resp.text}")
        resp.raise_for_status()

def create_suppression_note_for_contact(contact_id):
    url = f"{BASE_URL}/crm/v3/objects/notes"

    properties = {
        "hs_note_body": SUPPRESSION_NOTE_BODY,
        "hs_timestamp": int(time.time() * 1000),
    }
    if NOTE_OWNER_ID:
        properties["hubspot_owner_id"] = NOTE_OWNER_ID

    payload = {"properties": properties}
    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    if resp.status_code >= 400:
        print(f"[DEBUG] Note create error body for contact {contact_id}: {resp.text}")
        resp.raise_for_status()

    note = resp.json()
    note_id = note.get("id")

    if note_id:
        associate_note_to_contact(note_id, contact_id)

    return note

# ----------------------------
# Suppression filter
# ----------------------------
def filter_suppressed_contacts(contact_ids):
    if not contact_ids:
        return []

    url = f"{BASE_URL}/crm/v3/objects/contacts/batch/read"
    allowed_ids = []

    for chunk in batch_chunks(contact_ids, CONTACT_BATCH_SIZE):
        payload = {
            "properties": [SUPPRESSION_PROPERTY],
            "inputs": [{"id": cid} for cid in chunk],
        }

        resp = requests.post(url, headers=headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        suppression_map = {}
        for row in data.get("results", []):
            cid = str(row.get("id"))
            val = row.get("properties", {}).get(SUPPRESSION_PROPERTY)
            suppression_map[cid] = val

        for cid in chunk:
            val = suppression_map.get(str(cid))
            if str(val).lower() == "true":
                try:
                    print(f"[SUPPRESS] Contact {cid}: creating note (owner={NOTE_OWNER_ID})...")
                    create_suppression_note_for_contact(cid)
                except Exception as e:
                    print(f"[WARN] Failed to create note for contact {cid}: {e}")
                continue

            allowed_ids.append(str(cid))

        time.sleep(0.05)

    return allowed_ids

# ----------------------------
# Contact emails
# ----------------------------
def get_contact_emails(contact_ids):
    result = {}
    if not contact_ids:
        return result

    url = f"{BASE_URL}/crm/v3/objects/contacts/batch/read"

    for chunk in batch_chunks(contact_ids, CONTACT_BATCH_SIZE):
        payload = {
            "properties": ["email"],
            "inputs": [{"id": cid} for cid in chunk]
        }

        resp = requests.post(url, headers=headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for row in data.get("results", []):
            cid = str(row.get("id"))
            email = row.get("properties", {}).get("email")
            if email:
                result[cid] = email.lower().strip()

        time.sleep(0.05)

    return result

# ----------------------------
# Marketing email events (for opens, etc.)
# ----------------------------
def get_email_events_for_campaign(campaign_id, start_timestamp_ms=None):
    events = []
    offset = None
    has_more = True

    while has_more:
        params = {
            "campaignId": campaign_id,
            "limit": 1000,
        }
        if offset:
            params["offset"] = offset

        url = f"{BASE_URL}/email/public/v1/events"
        data = get_json(url, params=params)

        events.extend(data.get("events", []))
        has_more = data.get("hasMore", False)
        offset = data.get("offset")

        if not has_more:
            break

    if start_timestamp_ms is not None:
        events = [
            e for e in events
            if e.get("created") is not None and int(e["created"]) >= int(start_timestamp_ms)
        ]

    return events

def aggregate_opens_for_campaign(contact_email_map, campaign_id, start_timestamp_ms=None):
    opens = defaultdict(int)
    allowed_emails = {email.lower() for email in contact_email_map.values()}

    events = get_email_events_for_campaign(campaign_id, start_timestamp_ms)
    for e in events:
        recipient = (e.get("recipient") or "").lower()
        if recipient not in allowed_emails:
            continue

        etype = e.get("type")
        email_campaign_id = str(e.get("emailCampaignId"))
        key = (recipient, email_campaign_id)

        if etype == "OPEN":
            opens[key] += 1

    return opens

# ----------------------------
# CRM email engagements for replies
# ----------------------------
def search_crm_emails_for_contact(contact_id, start_ms=None, end_ms=None):
    """
    Uses /crm/v3/objects/emails/search to pull email engagements for a contact.
    Filters by hs_timestamp window if provided.
    """
    url = f"{BASE_URL}/crm/v3/objects/emails/search"

    filters = [
        {
            "propertyName": "hs_object_id",
            "operator": "HAS_PROPERTY",
            "value": ""
        }
    ]
    # time window filter on hs_timestamp
    if start_ms is not None or end_ms is not None:
        ts_filter = {"propertyName": "hs_timestamp"}
        if start_ms is not None and end_ms is not None:
            ts_filter["operator"] = "BETWEEN"
            ts_filter["value"] = start_ms
            ts_filter["highValue"] = end_ms
        elif start_ms is not None:
            ts_filter["operator"] = "GTE"
            ts_filter["value"] = start_ms
        else:
            ts_filter["operator"] = "LTE"
            ts_filter["value"] = end_ms
        filters.append(ts_filter)

    payload = {
        "filterGroups": [
            {
                "filters": filters
            }
        ],
        "properties": [
            "hs_email_direction",
            "hs_email_status",
            "hs_email_subject",
            "hs_timestamp",
            "hs_email_to_email",
            "hs_email_from_email"
        ],
        "limit": 100,  # adjust if needed, can loop with after
        "associations": ["contacts"],
    }

    # Simple paging loop
    results = []
    after = None
    while True:
        if after is not None:
            payload["after"] = after

        data = post_json(url, payload)
        results.extend(data.get("results", []))

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after:
            break

    # Filter down to emails associated with this contact_id
    out = []
    for row in results:
        assoc = row.get("associations", {}).get("contacts", {})
        assoc_ids = {str(i) for i in assoc.get("results", [])} if isinstance(assoc.get("results", []), list) else set()
        if str(contact_id) in assoc_ids:
            out.append(row)
    return out

def contact_has_reply_email(contact_id):
    """
    Approximate: does this contact have an INBOUND (received) email
    in the configured time window? If yes, treat as "replied".
    """
    if CAMPAIGN_SEND_START_MS is None and CAMPAIGN_SEND_END_MS is None:
        # No time window set; you may want to require one in production
        start_ms = None
        end_ms = None
    else:
        start_ms = CAMPAIGN_SEND_START_MS
        end_ms = CAMPAIGN_SEND_END_MS

    emails = search_crm_emails_for_contact(contact_id, start_ms, end_ms)

    for row in emails:
        props = row.get("properties", {})
        direction = props.get("hs_email_direction")  # INBOUND / OUTBOUND
        status = props.get("hs_email_status")       # e.g. SENT, RECEIVED, REPLIED, etc.
        # Simple heuristic: inbound or received email => treat as reply
        if direction == "INBOUND" or status in ("REPLIED", "REPLY_RECEIVED", "RECEIVED"):
            return True

    return False

# ----------------------------
# Main
# ----------------------------
def main():
    if HUBSPOT_TOKEN in (None, "", "$HUBSPOT_TOKEN"):
        raise RuntimeError("Set HUBSPOT_TOKEN in your environment before running.")

    print(f"Fetching members of list {LIST_ID}...")
    contact_ids = get_all_list_member_ids(LIST_ID)
    print(f"Found {len(contact_ids)} list members before suppression")

    print(f"Filtering out contacts where {SUPPRESSION_PROPERTY} == 'true' and updating them...")
    filtered_ids = filter_suppressed_contacts(contact_ids)
    print(f"{len(filtered_ids)} contacts remain after suppression filter")

    print("Fetching contact emails...")
    contact_email_map = get_contact_emails(filtered_ids)
    print(f"Resolved {len(contact_email_map)} contact emails")

    # Opens via marketing events
    all_opens = defaultdict(int)
    for campaign_id in CAMPAIGN_IDS:
        print(f"Aggregating OPEN events for campaign {campaign_id}...")
        opens = aggregate_opens_for_campaign(
            contact_email_map=contact_email_map,
            campaign_id=campaign_id,
            start_timestamp_ms=START_TIMESTAMP_MS,
        )
        for k, v in opens.items():
            all_opens[k] += v
        time.sleep(0.1)

    # Replies via CRM email engagements
    print("\nChecking CRM email engagements for replies (approximate)...")
    replied_contacts = set()
    for cid, email in contact_email_map.items():
        try:
            if contact_has_reply_email(cid):
                replied_contacts.add(email.lower())
                print(f"[REPLIED] {email}")
        except Exception as e:
            print(f"[WARN] Failed to check replies for contact {cid} ({email}): {e}")
        time.sleep(0.05)

    # Print summary to CLI
    print("\n=== Per-contact engagement (approximate) ===")
    if not all_opens and not replied_contacts:
        print("No opens or replies found for the configured campaigns and list.")
        return

    # all_opens is keyed by (recipient_email, campaign_id_str)
    keys = set(all_opens.keys())
    for (recipient_email, email_campaign_id) in sorted(keys):
        open_count = all_opens.get((recipient_email, email_campaign_id), 0)
        reply_flag = "YES" if recipient_email in replied_contacts else "NO"
        print(f"- {recipient_email} (campaign {email_campaign_id}): "
              f"opens={open_count}, replied={reply_flag}")

if __name__ == "__main__":
    main()
