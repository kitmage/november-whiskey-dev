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
# Optional: restrict to one or more marketing email campaign IDs
CAMPAIGN_IDS = {"25347176"}  # e.g. {"123456789", "987654321"}

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
# Docs: GET /crm/v3/lists/{listId}/memberships
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
    # 1) Create the note object
    url = f"{BASE_URL}/crm/v3/objects/notes"

    properties = {
        "hs_note_body": SUPPRESSION_NOTE_BODY,
        # hs_timestamp is required in your portal
        "hs_timestamp": int(time.time() * 1000),
    }
    if NOTE_OWNER_ID:
        properties["hubspot_owner_id"] = NOTE_OWNER_ID

    payload = {
        "properties": properties
    }

    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    if resp.status_code >= 400:
        print(f"[DEBUG] Note create error body for contact {contact_id}: {resp.text}")
        resp.raise_for_status()

    note = resp.json()
    note_id = note.get("id")

    if note_id:
        # 2) Associate note to contact
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

        # Build a map from this chunk by ID -> suppression value
        suppression_map = {}
        for row in data.get("results", []):
            cid = str(row.get("id"))
            val = row.get("properties", {}).get(SUPPRESSION_PROPERTY)
            suppression_map[cid] = val

        for cid in chunk:
            val = suppression_map.get(str(cid))
            if str(val).lower() == "true":
                # Suppressed: create a note
                try:
                    print(f"[SUPPRESS] Contact {cid}: creating note (owner={NOTE_OWNER_ID})...")
                    create_suppression_note_for_contact(cid)
                except Exception as e:
                    print(f"[WARN] Failed to create note for contact {cid}: {e}")
                # Do NOT add to allowed list
                continue

            # Not suppressed, keep
            allowed_ids.append(str(cid))

        time.sleep(0.05)

    return allowed_ids

# ----------------------------
# Batch read contacts to get email addresses
# Uses CRM batch read for contacts
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

        # small courtesy pause
        time.sleep(0.05)

    return result

# ----------------------------
# Pull marketing email events
# Docs: GET /email/public/v1/events
# Can query by recipient and/or campaignId
# ----------------------------
def get_email_events_for_recipient(recipient_email, campaign_id=None, start_timestamp_ms=None):
    """
    Pulls events for one recipient.
    Returns raw event rows.
    """
    events = []
    offset = None
    has_more = True

    while has_more:
        params = {
            "recipient": recipient_email,
            "limit": 1000,
        }

        if campaign_id:
            params["campaignId"] = campaign_id

        # The events endpoint supports paging via offset/hasMore in legacy style.
        if offset:
            params["offset"] = offset

        # If you want to reduce volume, use created__gt if your portal/docs support it.
        # Leaving commented because availability can vary by implementation.
        # if start_timestamp_ms:
        #     params["startTimestamp"] = start_timestamp_ms

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
# Aggregate opens
# ----------------------------
def aggregate_opens(contact_email_map, campaign_ids=None, start_timestamp_ms=None):
    """
    Returns dict keyed by (recipient_email, emailCampaignId) -> open_count
    """
    opens = defaultdict(int)

    for _, email in contact_email_map.items():
        if campaign_ids:
            # Query per recipient + per campaign to reduce noise
            for campaign_id in campaign_ids:
                events = get_email_events_for_recipient(
                    recipient_email=email,
                    campaign_id=campaign_id,
                    start_timestamp_ms=start_timestamp_ms,
                )
                for event in events:
                    if event.get("type") == "OPEN":
                        key = (email, str(event.get("emailCampaignId")))
                        opens[key] += 1
        else:
            # Query all campaign events for this recipient
            events = get_email_events_for_recipient(
                recipient_email=email,
                campaign_id=None,
                start_timestamp_ms=start_timestamp_ms,
            )
            for event in events:
                if event.get("type") == "OPEN":
                    campaign_id = event.get("emailCampaignId")
                    if campaign_id is None:
                        continue
                    key = (email, str(campaign_id))
                    opens[key] += 1

        time.sleep(0.05)

    return opens

# ----------------------------
# Aggregate opens and replies
# ----------------------------
def aggregate_opens_and_replies(contact_email_map, campaign_ids=None, start_timestamp_ms=None):
    """
    Returns two dicts:
      opens[(recipient_email, emailCampaignId)]   -> open_count
      replies[(recipient_email, emailCampaignId)] -> reply_count
    """
    opens = defaultdict(int)
    replies = defaultdict(int)

    for _, email in contact_email_map.items():
        if campaign_ids:
            # Query per recipient + per campaign to reduce noise
            for campaign_id in campaign_ids:
                events = get_email_events_for_recipient(
                    recipient_email=email,
                    campaign_id=campaign_id,
                    start_timestamp_ms=start_timestamp_ms,
                )
                for event in events:
                    if event.get("type") == "OPEN":
                        key = (email, str(event.get("emailCampaignId")))
                        opens[key] += 1
                    elif event.get("type") in ("REPLY", "REPLIED"):  # adjust to real type if needed
                        key = (email, str(event.get("emailCampaignId")))
                        replies[key] += 1
        else:
            # Query all campaign events for this recipient
            events = get_email_events_for_recipient(
                recipient_email=email,
                campaign_id=None,
                start_timestamp_ms=start_timestamp_ms,
            )
            for event in events:
                campaign_id = event.get("emailCampaignId")
                if campaign_id is None:
                    continue

                key = (email, str(campaign_id))
                if event.get("type") == "OPEN":
                    opens[key] += 1
                elif event.get("type") in ("REPLY", "REPLIED"):
                    replies[key] += 1

        time.sleep(0.05)

    return opens, replies

# TEMP: debug inside get_email_events_for_recipient, once, for one email
print(events[:5])

# ----------------------------
# Optional: Resolve campaign metadata
# Docs: GET /email/public/v1/campaigns/{campaign_id}
# ----------------------------
def get_campaign_details(campaign_id):
    url = f"{BASE_URL}/email/public/v1/campaigns/{campaign_id}"
    return get_json(url)

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

    print("Aggregating OPEN and REPLY events...")
    opens, replies = aggregate_opens_and_replies(
        contact_email_map=contact_email_map,
        campaign_ids=CAMPAIGN_IDS if CAMPAIGN_IDS else None,
        start_timestamp_ms=START_TIMESTAMP_MS,
    )

    # Union of all (email, campaign) keys that have either opens or replies
    all_keys = set(opens.keys()) | set(replies.keys())

    print("\nrecipient_email,emailCampaignId,open_count,reply_count")
    for recipient_email, email_campaign_id in sorted(all_keys):
        open_count = opens.get((recipient_email, email_campaign_id), 0)
        reply_count = replies.get((recipient_email, email_campaign_id), 0)
        print(f"{recipient_email},{email_campaign_id},{open_count},{reply_count}")

if __name__ == "__main__":
    main()
