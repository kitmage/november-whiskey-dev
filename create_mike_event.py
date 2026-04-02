#!/usr/bin/env python3
"""
create_mike_event.py

Reads best_start_time JSON from availability.py and creates a calendar event
directly on Mike's Outlook calendar.

Example:
  python3 availability.py | python3 create_mike_event.py \
    --customer-name "Prospect Name" \
    --customer-email "prospect@example.com" \
    --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
DEFAULT_TIMEZONE = "Pacific Standard Time"
DEFAULT_DURATION_MINUTES = 30
DEFAULT_SUBJECT_TEMPLATE = "30min Meeting - {customer_name}"


class GraphError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Outlook calendar event on Mike's calendar.")
    parser.add_argument("--input", help="Path to JSON file from availability.py. If omitted, reads stdin.")
    parser.add_argument("--customer-name", required=True)
    parser.add_argument("--customer-email", required=True)
    parser.add_argument("--customer-phone", default="")
    parser.add_argument("--customer-notes", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--location", default="Microsoft Teams")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--duration-minutes", type=int, default=DEFAULT_DURATION_MINUTES)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def read_input_json(path: Optional[str]) -> Dict[str, Any]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.load(sys.stdin)


def require_best_start(payload: Dict[str, Any]) -> str:
    best = payload.get("best_start_time")
    if not isinstance(best, dict):
        raise RuntimeError('Input JSON must contain object key "best_start_time".')
    start = best.get("start")
    if not isinstance(start, str) or not start:
        raise RuntimeError('"best_start_time.start" is missing or invalid.')
    return start


def get_access_token() -> str:
    tenant_id = load_env("TENANT_ID")
    client_id = load_env("CLIENT_ID")
    client_secret = load_env("CLIENT_SECRET")

    token_url = TOKEN_URL_TMPL.format(tenant_id=tenant_id)
    resp = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if not resp.ok:
        raise GraphError(f"Token request failed: {resp.status_code} {resp.text}")

    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise GraphError(f"No access_token in token response: {data}")
    return token


class GraphClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{GRAPH_ROOT}{path}"
        resp = self.session.post(url, data=json.dumps(body), timeout=30)
        if not resp.ok:
            raise GraphError(f"POST {url} failed: {resp.status_code} {resp.text}")
        return resp.json()


def make_datetime_pair(start_str: str, duration_minutes: int) -> tuple[str, str]:
    start_dt = datetime.fromisoformat(start_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return start_dt.isoformat(), end_dt.isoformat()


def build_event_body(args: argparse.Namespace, start_str: str) -> Dict[str, Any]:
    start_iso, end_iso = make_datetime_pair(start_str, args.duration_minutes)

    subject = args.subject.strip() or DEFAULT_SUBJECT_TEMPLATE.format(
        customer_name=args.customer_name
    )

    lines = [
        f"Customer: {args.customer_name}",
        f"Email: {args.customer_email}",
    ]
    if args.customer_phone:
        lines.append(f"Phone: {args.customer_phone}")
    if args.customer_notes:
        lines.append("")
        lines.append("Notes:")
        lines.append(args.customer_notes)

    return {
        "subject": subject,
        "body": {
            "contentType": "Text",
            "content": "\n".join(lines),
        },
        "start": {
            "dateTime": start_iso,
            "timeZone": args.timezone,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": args.timezone,
        },
        "location": {
            "displayName": args.location,
        },
        "attendees": [
            {
                "emailAddress": {
                    "address": args.customer_email,
                    "name": args.customer_name,
                },
                "type": "required",
            }
        ],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }


def main() -> None:
    args = parse_args()
    mike_email = load_env("MIKE_ID")

    input_payload = read_input_json(args.input)
    best_start = require_best_start(input_payload)

    token = get_access_token()
    client = GraphClient(token)

    event_body = build_event_body(args, best_start)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "target_calendar_user": mike_email,
            "event_payload": event_body,
        }, indent=2))
        return

    result = client.post(f"/users/{mike_email}/events", event_body)

    print(json.dumps({
        "target_calendar_user": mike_email,
        "event_id": result.get("id"),
        "web_link": result.get("webLink"),
        "subject": result.get("subject"),
        "start": result.get("start"),
        "end": result.get("end"),
    }, indent=2))


if __name__ == "__main__":
    main()
