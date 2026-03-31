import os
import sys
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
LIST_ID = 677  # HubSpot segment/list ID (not used in this script, but kept from your template)
CAMPAIGN_ID = "6afccccd-1f8b-4036-ba17-3eea85f23a05"
PROPERTY_NAME = "do_not_send_pci"  # not used in this script yet

BASE_URL = "https://api.hubapi.com"

if not HUBSPOT_TOKEN:
    print("HUBSPOT_TOKEN environment variable is not set.", file=sys.stderr)
    sys.exit(1)


def hs_get(path, params=None):
    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, params=params or {})
    if not resp.ok:
        print(
            f"GET {url} failed: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        resp.raise_for_status()
    return resp.json()


def get_marketing_email_ids_for_campaign(campaign_guid):
    """
    Uses Campaigns v3: GET /marketing/v3/campaigns/{campaignGuid}/assets/MARKETING_EMAIL
    Returns list of email IDs as strings.
    """
    email_ids = []
    after = None

    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after

        data = hs_get(
            f"/marketing/v3/campaigns/{campaign_guid}/assets/MARKETING_EMAIL",
            params=params,
        )

        # Newer API variant: response is directly the asset list
        # Older doc variant: assets.{ASSET_TYPE}.results[]
        results = []

        # Try simple top-level results
        if "results" in data and isinstance(data["results"], list):
            results = data["results"]
        # Try nested assets.MARKETING_EMAIL.results
        elif (
            "assets" in data
            and "MARKETING_EMAIL" in data["assets"]
            and "results" in data["assets"]["MARKETING_EMAIL"]
        ):
            results = data["assets"]["MARKETING_EMAIL"]["results"]

        for asset in results:
            # asset shape: { "id": "832", "name": "My email", ... }
            email_id = str(asset.get("id"))
            if email_id:
                email_ids.append(email_id)

        # handle paging
        paging = data.get("paging") or data.get("assets", {}).get("MARKETING_EMAIL", {}).get("paging")
        if paging and "next" in paging and "after" in paging["next"]:
            after = paging["next"]["after"]
        else:
            break

    return email_ids


def get_email_campaign_ids_for_email(email_id):
    """
    Uses Marketing Emails v3: GET /marketing/v3/emails/{emailId}
    Returns list of legacy emailCampaignIds (ints) from:
      - allEmailCampaignIds
      - primaryEmailCampaignId
    """
    data = hs_get(f"/marketing/v3/emails/{email_id}")

    email_campaign_ids = set()

    # allEmailCampaignIds is an array of strings
    for cid in data.get("allEmailCampaignIds", []):
        try:
            email_campaign_ids.add(int(cid))
        except (TypeError, ValueError):
            pass

    # primaryEmailCampaignId is a single string
    primary = data.get("primaryEmailCampaignId")
    if primary:
        try:
            email_campaign_ids.add(int(primary))
        except (TypeError, ValueError):
            pass

    return sorted(email_campaign_ids)

def get_email_campaign_context_for_email(email_id):
    """
    Uses Marketing Emails v3: GET /marketing/v3/emails/{emailId}
    Returns:
      {
        "appId": int or None,
        "emailCampaignIds": [int, ...]
      }
    """
    data = hs_get(f"/marketing/v3/emails/{email_id}")

    email_campaign_ids = set()

    # allEmailCampaignIds is an array of strings
    for cid in data.get("allEmailCampaignIds", []):
        try:
            email_campaign_ids.add(int(cid))
        except (TypeError, ValueError):
            pass

    # primaryEmailCampaignId is a single string
    primary = data.get("primaryEmailCampaignId")
    if primary:
        try:
            email_campaign_ids.add(int(primary))
        except (TypeError, ValueError):
            pass

    # appId: best-effort extraction
    app_id = None

    # In many accounts, appId appears under stats metadata or event metadata.
    # Try a few likely locations defensively:
    stats = data.get("stats") or {}
    if isinstance(stats, dict):
        # sometimes appId is flattened
        if "appId" in stats:
            try:
                app_id = int(stats["appId"])
            except (TypeError, ValueError):
                pass

        # sometimes nested inside qualifierStats or similar structures
        if app_id is None:
            for section in ("qualifierStats", "counters"):
                sec = stats.get(section)
                if isinstance(sec, dict) and "appId" in sec:
                    try:
                        app_id = int(sec["appId"])
                        break
                    except (TypeError, ValueError):
                        pass

    # As a fallback, check top-level if HubSpot starts surfacing it there
    if app_id is None and "appId" in data:
        try:
            app_id = int(data["appId"])
        except (TypeError, ValueError):
            pass

    return {
        "appId": app_id,
        "emailCampaignIds": sorted(email_campaign_ids),
    }
    

def get_open_events_for_email_campaign(app_id, email_campaign_id):
    """
    Uses Email Events API v1:
      GET /email/public/v1/events?appId={appId}&emailCampaignId={id}&type=OPEN
    Paginates using 'offset' (string cursor) until hasMore is false.
    Returns list of event dicts.
    """
    events = []
    offset = None

    while True:
        params = {
            "appId": app_id,
            "emailCampaignId": email_campaign_id,
            "type": "OPEN",
            "limit": 1000,
        }
        if offset is not None:
            params["offset"] = offset

        data = hs_get("/email/public/v1/events", params=params)

        batch = data.get("events", [])
        events.extend(batch)

        has_more = data.get("hasMore", False)
        if not has_more:
            break

        offset = data.get("offset")
        if not offset:
            break

    return events


def main():
    print(f"Fetching marketing emails for campaign {CAMPAIGN_ID}...", file=sys.stderr)
    email_ids = get_marketing_email_ids_for_campaign(CAMPAIGN_ID)

    if not email_ids:
        print("No MARKETING_EMAIL assets found for this campaign.", file=sys.stderr)
        return

    print(f"Found {len(email_ids)} marketing emails.", file=sys.stderr)

    for email_id in email_ids:
        print(f"\n=== Email ID {email_id} ===")
        ctx = get_email_campaign_context_for_email(email_id)
        app_id = ctx["appId"]
        email_campaign_ids = ctx["emailCampaignIds"]

        if app_id is None:
            print("  No appId found for this email; cannot query raw events.", file=sys.stderr)
            continue

        if not email_campaign_ids:
            print("  No legacy emailCampaignIds found for this email.", file=sys.stderr)
            continue

        for ecid in email_campaign_ids:
            print(f"  -- appId {app_id}, emailCampaignId {ecid} --", file=sys.stderr)
            open_events = get_open_events_for_email_campaign(app_id, ecid)

            if not open_events:
                print(f"  (no OPEN events for emailCampaignId {ecid})")
                continue

            for ev in open_events:
                recipient = ev.get("recipient")
                created = ev.get("created")
                event_type = ev.get("type")
                print(
                    f"emailId={email_id}, appId={app_id}, emailCampaignId={ecid}, "
                    f"type={event_type}, recipient={recipient}, created={created}, raw={ev}"
                )

import json

data = hs_get(f"/marketing/v3/emails/{email_id}")
print(json.dumps(data, indent=2))
sys.exit(0)


if __name__ == "__main__":
    main()
