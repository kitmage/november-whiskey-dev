import os
import sys
import json
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
HUBSPOT_APP_ID = int(os.environ.get("HUBSPOT_APP_ID", "2286"))  # 2286 = HubSpot marketing email app

# You can adjust these as needed
LIST_ID = 677  # Not used in this script but kept from your template
CAMPAIGN_ID = "6afccccd-1f8b-4036-ba17-3eea85f23a05"
PROPERTY_NAME = "do_not_send_pci"  # Not used here

BASE_URL = "https://api.hubapi.com"


def require_env():
    missing = []
    if not HUBSPOT_TOKEN:
        missing.append("HUBSPOT_TOKEN")
    if not HUBSPOT_APP_ID:
        missing.append("HUBSPOT_APP_ID")
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def hs_get(path, params=None):
    """Thin wrapper for GET with basic error handling."""
    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, params=params or {})
    if not resp.ok:
        print(
            f"GET {url} failed ({resp.status_code}): {resp.text}",
            file=sys.stderr,
        )
        resp.raise_for_status()
    return resp.json()


def get_marketing_email_ids_for_campaign(campaign_guid):
    """
    Uses Campaigns v3:
      GET /marketing/v3/campaigns/{campaignGuid}/assets/MARKETING_EMAIL

    Returns:
      list[str] of marketing email IDs.
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

        # API shape can be either:
        # 1) { "results": [ { "id": "832", ... }, ... ] }
        # 2) { "assets": { "MARKETING_EMAIL": { "results": [...], "paging": {...} } } }
        results = []

        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
            results = data["results"]
        elif (
            isinstance(data, dict)
            and "assets" in data
            and "MARKETING_EMAIL" in data["assets"]
            and "results" in data["assets"]["MARKETING_EMAIL"]
        ):
            results = data["assets"]["MARKETING_EMAIL"]["results"]

        for asset in results:
            email_id = asset.get("id")
            if email_id is not None:
                email_ids.append(str(email_id))

        # Handle paging for either top-level or nested form
        paging = data.get("paging")
        if not paging and "assets" in data and "MARKETING_EMAIL" in data["assets"]:
            paging = data["assets"]["MARKETING_EMAIL"].get("paging")

        if paging and "next" in paging and "after" in paging["next"]:
            after = paging["next"]["after"]
        else:
            break

    return email_ids


def get_email_campaign_ids_for_email(email_id):
    """
    Uses Marketing Emails v3:
      GET /marketing/v3/emails/{emailId}

    Returns:
      list[int] of legacy emailCampaignIds for that email.
    """
    data = hs_get(f"/marketing/v3/emails/{email_id}")

    email_campaign_ids = set()

    # allEmailCampaignIds is usually an array of strings
    for cid in data.get("allEmailCampaignIds", []):
        try:
            email_campaign_ids.add(int(cid))
        except (TypeError, ValueError):
            continue

    # primaryEmailCampaignId is a single string
    primary = data.get("primaryEmailCampaignId")
    if primary:
        try:
            email_campaign_ids.add(int(primary))
        except (TypeError, ValueError):
            pass

    return sorted(email_campaign_ids)


def get_open_events_for_email_campaign(email_campaign_id, app_id=HUBSPOT_APP_ID):
    """
    Uses Email Events API v1:
      GET /email/public/v1/events?appId={appId}&emailCampaignId={id}&type=OPEN

    Paginates with 'offset' (string cursor) until hasMore == false.

    Returns:
      list[dict] of OPEN events.
    """
    events = []
    offset = None

    while True:
        params = {
            "appId": app_id,
            "emailCampaignId": email_campaign_id,
            "type": "OPEN",
            "limit": 1000,  # max per page
        }
        if offset is not None:
            params["offset"] = offset

        data = hs_get("/email/public/v1/events", params=params)

        batch = data.get("events", [])
        events.extend(batch)

        if not data.get("hasMore"):
            break

        offset = data.get("offset")
        if not offset:
            break

    return events


def main():
    require_env()

    print(
        f"Fetching marketing emails for campaign {CAMPAIGN_ID} "
        f"(appId={HUBSPOT_APP_ID})...",
        file=sys.stderr,
    )

    email_ids = get_marketing_email_ids_for_campaign(CAMPAIGN_ID)

    if not email_ids:
        print("No MARKETING_EMAIL assets found for this campaign.", file=sys.stderr)
        return

    print(f"Found {len(email_ids)} marketing emails.", file=sys.stderr)

    for email_id in email_ids:
        print(f"\n=== Email ID {email_id} ===")
        email_campaign_ids = get_email_campaign_ids_for_email(email_id)

        if not email_campaign_ids:
            print("  No legacy emailCampaignIds found for this email.", file=sys.stderr)
            continue

        for ecid in email_campaign_ids:
            print(
                f"  -- emailCampaignId {ecid} (appId={HUBSPOT_APP_ID}) --",
                file=sys.stderr,
            )
            open_events = get_open_events_for_email_campaign(ecid, HUBSPOT_APP_ID)

            if not open_events:
                print(f"  (no OPEN events for emailCampaignId {ecid})")
                continue

            # Print raw events, one line per event (you can change to pure JSON if you prefer)
            for ev in open_events:
                recipient = ev.get("recipient")
                created = ev.get("created")
                event_type = ev.get("type")
                print(
                    f"emailId={email_id}, appId={HUBSPOT_APP_ID}, "
                    f"emailCampaignId={ecid}, type={event_type}, "
                    f"recipient={recipient}, created={created}, raw={json.dumps(ev)}"
                )


if __name__ == "__main__":
    main()
