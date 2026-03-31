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

# Restrict to one or more marketing email campaign IDs
CAMPAIGN_IDS = {"25347176"}

# Optional: only count events since a given Unix ms timestamp
START_TIMESTAMP_MS = None  # e.g. 1741392000000

# Optional: page size where supported
LIST_PAGE_LIMIT = 250
CONTACT_BATCH_SIZE = 100

# Suppression property
SUPPRESSION_PROPERTY = "do_not_send_pci"

# Owner for notes (from env)
NOTE_OWNER_ID = os.getenv("HUBSPOT_USER_ID")

# Note body for suppressed contacts
SUPPRESSION_NOTE_BODY = (
    'MikeBot noticed this contact has the "Block PCI" Property set to Yes/True, '
    "so the contact has been removed from the PCI Nurture Sequence."
)

# ----------------------------
# Helpers
# ----------------------------
def headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }

def get_json(url, params=None):
    resp = requests.get(url, headers=headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def batch_chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]

# ----------------------------
# Get list memberships
# ----------------------------
def get_all_list_member_ids(list_id):
    """
    Returns list of contact IDs that are list members.
    (No suppression filtering here.)
    """
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
# Actions for suppressed contacts
# ----------------------------
def associate_note_to_contact(note_id, contact_id):
    """
    Associate a note with a contact using v3 associations API.
    PUT /crm/v3/objects/notes/{noteId}/associations/contacts/{contactId}/note_to_contact
    """
    url = f"{BASE_URL}/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact"
    resp = requests.put(url, headers=headers(), timeout=30)
    if resp.status_code >= 400:
        print(f"[DEBUG] Association error body for note {note_id} -> contact {contact_id}: {resp.text}")
        resp.raise_for_status()

def create_suppression_note_for_contact(contact_id):
    """
    Create a note on the contact explaining why they were removed.
    Owner is set from NOTE_OWNER_ID (HUBSPOT_USER_ID env) if available.
    """
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
# Batch read suppression property & filter
# ----------------------------
def filter_suppressed_contacts(contact_ids):
    """
    Takes a list of contact IDs, returns only those where
    SUPPRESSION_PROPERTY != "true" (string, case-insensitive).

    For each suppressed contact:
      - Add a note to the contact (owned by NOTE_OWNER_ID if set).

    Contacts missing the property are treated as NOT suppressed.
    """
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
                continue  # skip suppressed

            allowed_ids.append(str(cid))

        time.sleep(0.05)

    return allowed_ids

# ----------------------------
# Batch read contacts to get email addresses
# ----------------------------
def get_contact_emails(contact_ids):
    """
    Returns:
      {
        "123": "person@example.com",
        ...
      }
    """
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
# Pull marketing email events by campaign
# ----------------------------
def get_email_events_for_campaign(campaign_id, start_timestamp_ms=None):
    """
    Pulls all events for a marketing email campaign.
    Returns raw event rows.
    """
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

# ----------------------------
# Aggregate opens and replies from campaign events
# ----------------------------
def aggregate_opens_and_replies_for_campaign(contact_email_map, campaign_id, start_timestamp_ms=None):
    """
    For a single marketing email campaign:
      - Pulls all events for the campaign
      - Aggregates OPEN and REPLY events for contacts in contact_email_map

    Returns:
      opens[(recipient_email, emailCampaignId)]   -> open_count
      replies[(recipient_email, emailCampaignId)] -> reply_count
    """
    opens = defaultdict(int)
    replies = defaultdict(int)

    allowed_emails = {email.lower() for email in contact_email_map.values()}

    events = get_email_events_for_campaign(
        campaign_id=campaign_id,
        start_timestamp_ms=start_timestamp_ms,
    )

    for event in events:
        recipient_email = (event.get("recipient") or "").lower()
        if recipient_email not in allowed_emails:
            continue

        etype = event.get("type")
        email_campaign_id = str(event.get("emailCampaignId"))

        # DEBUG: mirror what's happening for each event
        print("EVENT", etype, email_campaign_id, recipient_email)

        key = (recipient_email, email_campaign_id)

        if etype == "OPEN":
            opens[key] += 1
        elif etype in ("REPLY", "REPLIED"):
            replies[key] += 1

    return opens, replies

# ----------------------------
# Main
# ----------------------------
def main():
    if HUBSPOT_TOKEN in (None, "", "$HUBSPOT_TOKEN"):
        raise RuntimeError("Set HUBSPOT_TOKEN in your environment before running.")

    if not NOTE_OWNER_ID:
        print("[INFO] HUBSPOT_USER_ID is not set; notes will not have an explicit owner.")

    print(f"Fetching members of list {LIST_ID}...")
    contact_ids = get_all_list_member_ids(LIST_ID)
    print(f"Found {len(contact_ids)} list members before suppression")

    print(f"Filtering out contacts where {SUPPRESSION_PROPERTY} == 'true' and updating them...")
    filtered_ids = filter_suppressed_contacts(contact_ids)
    print(f"{len(filtered_ids)} contacts remain after suppression filter")

    print("Fetching contact emails...")
    contact_email_map = get_contact_emails(filtered_ids)
    print(f"Resolved {len(contact_email_map)} contact emails")

    # Aggregate per campaign
    all_opens = defaultdict(int)
    all_replies = defaultdict(int)

    for campaign_id in CAMPAIGN_IDS:
        print(f"Aggregating OPEN and REPLY events for campaign {campaign_id}...")
        opens, replies = aggregate_opens_and_replies_for_campaign(
            contact_email_map=contact_email_map,
            campaign_id=campaign_id,
            start_timestamp_ms=START_TIMESTAMP_MS,
        )

        for k, v in opens.items():
            all_opens[k] += v
        for k, v in replies.items():
            all_replies[k] += v

        time.sleep(0.1)

    # Print a human-readable summary to the CLI
    print("\n=== Per-contact engagement ===")
    if not (all_opens or all_replies):
        print("No OPEN or REPLY events found for the configured campaigns and list.")
        return

    for (recipient_email, email_campaign_id) in sorted(set(all_opens) | set(all_replies)):
        open_count = all_opens.get((recipient_email, email_campaign_id), 0)
        reply_count = all_replies.get((recipient_email, email_campaign_id), 0)
        print(f"- {recipient_email} (campaign {email_campaign_id}): "
              f"opens={open_count}, replies={reply_count}")

if __name__ == "__main__":
    main()
