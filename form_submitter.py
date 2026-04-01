#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
from typing import Dict, Any, Optional

import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
HUBSPOT_APP_ID = int(os.environ.get("HUBSPOT_APP_ID", "2286"))  # not strictly needed here, but available

FORM_ID = "2710c2e4-faad-4ddc-83af-faa9520d81a4"
BASE_URL = "https://api.hubapi.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit contacts (from signal_finder.py JSON lines) to a HubSpot form."
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Input file with JSON lines; defaults to stdin.",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be submitted without calling the HubSpot API.",
    )
    return parser.parse_args()


def read_lines(path: Optional[str]):
    """Yield lines from stdin or from a file."""
    if path:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                yield line
    else:
        for line in sys.stdin:
            yield line


def is_contact_event_line(line: str) -> bool:
    """Heuristically detect lines that look like contact JSON from signal_finder."""
    line = line.strip()
    if not line.startswith("{") or not line.endswith("}"):
        return False
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False

    # Expect at minimum these keys from your example
    return "email" in obj and "contactId" in obj


def extract_submission_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map the event fields into form field values.

    Adjust 'fields' list if your HubSpot form has more fields you want to populate.
    """
    email = event.get("email")
    # You can also send openCount, emailId, etc. as hidden fields if your form has them.
    open_count = event.get("openCount")
    email_id = event.get("emailId")
    email_campaign_id = event.get("emailCampaignId")

    fields = [
        {"name": "email", "value": email},
    ]

    # Optional hidden fields (only if these exist as form fields)
    if open_count is not None:
        fields.append({"name": "open_count", "value": str(open_count)})
    if email_id is not None:
        fields.append({"name": "email_id", "value": str(email_id)})
    if email_campaign_id is not None:
        fields.append({"name": "email_campaign_id", "value": str(email_campaign_id)})

    submission = {
        "fields": fields,
        # Legal basis & consent / context can be added here if needed
        # "context": {...},
        # "legalConsentOptions": {...},
    }
    return submission


def submit_form(email: str, submission_data: Dict[str, Any], dry_run: bool = False) -> None:
    """
    Submit a single form submission for the given email.
    """

    if dry_run:
        print(f"[DRY RUN] Would submit for {email}: {json.dumps(submission_data)}")
        return

    if not HUBSPOT_TOKEN:
        raise RuntimeError("HUBSPOT_TOKEN is not set in environment")

    url = f"{BASE_URL}/forms/v2/submissions/forms/{FORM_ID}"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=submission_data)

    if resp.status_code >= 200 and resp.status_code < 300:
        print(f"Submitted form for {email} (status={resp.status_code})")
    else:
        # Print some diagnostics but keep going
        print(
            f"Failed to submit form for {email} "
            f"(status={resp.status_code}): {resp.text}",
            file=sys.stderr,
        )


def main():
    args = parse_args()

    if not HUBSPOT_TOKEN and not args.dry_run:
        print("Error: HUBSPOT_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(1)

    print("Reading contact events and submitting to HubSpot form...")

    count_total = 0
    count_submitted = 0

    for raw_line in read_lines(args.input):
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # Skip log lines from signal_finder.py
        if not is_contact_event_line(raw_line):
            continue

        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            print(f"Skipping non-JSON line: {raw_line}", file=sys.stderr)
            continue

        email = event.get("email")
        if not email:
            print(f"Skipping event without email: {event}", file=sys.stderr)
            continue

        count_total += 1

        submission_data = extract_submission_data(event)
        submit_form(email, submission_data, dry_run=args.dry_run)

        count_submitted += 1

        # Optional small delay if you're worried about rate limits
        time.sleep(0.05)

    print(f"Done. Processed {count_total} events, submitted {count_submitted} forms.")


if __name__ == "__main__":
    main()
