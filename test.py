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
CAMPAIGN_IDS = set()  # e.g. {"123456789", "987654321"}

# Optional: only count events since a given Unix ms timestamp
START_TIMESTAMP_MS = None  # e.g. 1741392000000

# Optional: page size where supported
LIST_PAGE_LIMIT = 250
CONTACT_BATCH_SIZE = 100


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


# ----------------------------
# Step 1: Get list memberships
# Docs: GET /crm/v3/lists/{listId}/memberships
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
# Step 2: Batch read contacts to get email addresses
# Uses CRM batch read for contacts
# ----------------------------
def batch_chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def get_contact_emails(contact_ids):
    """
    Returns:
      {
        "123": "person@example.com",
        ...
      }
    """
    result = {}

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
# Step 3: Pull marketing email events
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
# Step 4: Aggregate opens
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

    print(f"Fetching members of list {LIST_ID}...")
    contact_ids = get_all_list_member_ids(LIST_ID)
    print(f"Found {len(contact_ids)} list members")

    print("Fetching contact emails...")
    contact_email_map = get_contact_emails(contact_ids)
    print(f"Resolved {len(contact_email_map)} contact emails")

    print("Aggregating OPEN events...")
    opens = aggregate_opens(
        contact_email_map=contact_email_map,
        campaign_ids=CAMPAIGN_IDS if CAMPAIGN_IDS else None,
        start_timestamp_ms=START_TIMESTAMP_MS,
    )

    print("\nrecipient_email,emailCampaignId,open_count")
    for (recipient_email, email_campaign_id), count in sorted(opens.items()):
        print(f"{recipient_email},{email_campaign_id},{count}")


if __name__ == "__main__":
    main()

