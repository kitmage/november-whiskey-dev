import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import msal
import requests
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.environ["TENANT_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Use a Windows timezone name in the Graph payload/header.
# Graph examples and docs use Windows timezone names like "Central Standard Time".
GRAPH_TIMEZONE = "Central Standard Time"

# Your two users
USER_1 = "salesmarketing@nwmriskmonitoring.com"
USER_2 = "tom@nwmriskmanagement.com"

# Query window
START_LOCAL = datetime(2026, 4, 2, 9, 0, 0)
END_LOCAL = datetime(2026, 4, 2, 17, 0, 0)

# Slot size in minutes
INTERVAL_MINUTES = 30


def get_access_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

    result = app.acquire_token_for_client(scopes=SCOPES)

    if "access_token" not in result:
        raise RuntimeError(f"Could not acquire token: {result}")

    return result["access_token"]


def call_get_schedule(access_token: str, anchor_user: str, schedules: list[str],
                      start_dt: datetime, end_dt: datetime, interval_minutes: int) -> dict:
    """
    anchor_user is just the user in the URL path:
      /users/{anchor_user}/calendar/getSchedule

    The actual queried mailboxes are in the schedules array.
    """
    url = f"{GRAPH_BASE}/users/{anchor_user}/calendar/getSchedule"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Prefer": f'outlook.timezone="{GRAPH_TIMEZONE}"',
    }

    payload = {
        "schedules": schedules,
        "startTime": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": GRAPH_TIMEZONE,
        },
        "endTime": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": GRAPH_TIMEZONE,
        },
        "availabilityViewInterval": interval_minutes,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"Graph call failed: {response.status_code}\n{response.text}"
        )

    return response.json()


def mutual_free_slots(schedule_response: dict, start_dt: datetime, interval_minutes: int) -> list[tuple[datetime, datetime]]:
    """
    Use availabilityView from each schedule entry.
    0 = free / working elsewhere
    1 = tentative
    2 = busy
    3 = out of office

    Conservative AND-logic:
      only slots where every user has '0' are considered mutually free.
    """
    values = schedule_response.get("value", [])
    if len(values) < 2:
        raise ValueError("Expected at least two schedule results.")

    availability_strings = []
    for entry in values:
        av = entry.get("availabilityView")
        if not av:
            raise ValueError(f"Missing availabilityView for {entry.get('scheduleId')}")
        availability_strings.append(av)

    # Defensive: make sure lengths line up
    slot_count = min(len(s) for s in availability_strings)

    free_ranges = []
    current_start = None

    for i in range(slot_count):
        chars = [s[i] for s in availability_strings]
        everyone_free = all(c == "0" for c in chars)

        slot_start = start_dt + timedelta(minutes=i * interval_minutes)
        slot_end = slot_start + timedelta(minutes=interval_minutes)

        if everyone_free:
            if current_start is None:
                current_start = slot_start
        else:
            if current_start is not None:
                free_ranges.append((current_start, slot_start))
                current_start = None

    if current_start is not None:
        final_end = start_dt + timedelta(minutes=slot_count * interval_minutes)
        free_ranges.append((current_start, final_end))

    return free_ranges


def main():
    token = get_access_token()

    response = call_get_schedule(
        access_token=token,
        anchor_user=USER_1,
        schedules=[USER_1, USER_2],
        start_dt=START_LOCAL,
        end_dt=END_LOCAL,
        interval_minutes=INTERVAL_MINUTES,
    )

    print("Raw availabilityView values:")
    for entry in response.get("value", []):
        print(f"- {entry.get('scheduleId')}: {entry.get('availabilityView')}")

    print("\nMutual free slots:")
    free_slots = mutual_free_slots(response, START_LOCAL, INTERVAL_MINUTES)

    if not free_slots:
        print("No mutually free slots found.")
        return

    for start_slot, end_slot in free_slots:
        print(f"- {start_slot.isoformat()} to {end_slot.isoformat()}")


if __name__ == "__main__":
    main()
