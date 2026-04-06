from __future__ import annotations

from datetime import datetime, timedelta

from november_whiskey.config import EventConfig
from november_whiskey.exceptions import GraphAPIError


def build_event_payload(
    event_config: EventConfig,
    *,
    customer_name: str,
    customer_email: str,
    start: str,
    timezone: str,
    duration_minutes: int,
    subject: str | None = None,
    location: str | None = None,
) -> dict:
    start_dt = datetime.fromisoformat(start)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return {
        "subject": (subject or event_config.default_subject_template.format(customer_name=customer_name)).strip(),
        "body": {"contentType": "Text", "content": f"Customer: {customer_name}\nEmail: {customer_email}"},
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
        "location": {"displayName": location or event_config.default_location},
        "attendees": [{"emailAddress": {"address": customer_email, "name": customer_name}, "type": "required"}],
        "isOnlineMeeting": bool(event_config.enable_teams_meeting),
        "onlineMeetingProvider": "teamsForBusiness",
    }


def create_event(access_token: str, target_user: str, payload: dict, timeout: int = 30) -> dict:
    url = f"https://graph.microsoft.com/v1.0/users/{target_user}/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    import requests
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if not response.ok:
        raise GraphAPIError(f"Graph event create failed ({response.status_code})")
    return response.json()
