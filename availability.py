import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import msal
import requests
from dotenv import load_dotenv

load_dotenv()

# =========================
# Required environment vars
# =========================
TENANT_ID = os.environ["TENANT_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
ROB_ID = os.environ["ROB_ID"]
TOM_ID = os.environ["TOM_ID"]
MIKE_ID = os.environ["MIKE_ID"]
# Add more env vars as needed, e.g.:
# JANE_ID = os.environ["JANE_ID"]
# SUE_ID = os.environ["SUE_ID"]

# =========================
# Microsoft Graph settings
# =========================
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_TIMEZONE = "Central Standard Time"  # Windows timezone name for Graph

# =========================
# Local/business settings
# =========================
LOCAL_TZ = ZoneInfo("America/Chicago")

# Define any number of users here
USERS = [
    TOM_ID,
    ROB_ID,
    MIKE_ID,
    # JANE_ID,
    # SUE_ID,
]

BOOKING_WINDOW_START_HOURS = 36
BOOKING_WINDOW_END_HOURS = 120

BUSINESS_DAY_START_HOUR = 9   # 9 AM
BUSINESS_DAY_END_HOUR = 16    # 4 PM

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


def ceil_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    """
    Round a datetime up to the next interval boundary.
    Examples for 30-minute intervals:
      10:00:00 -> 10:00:00
      10:01:00 -> 10:30:00
      10:30:00 -> 10:30:00
      10:31:00 -> 11:00:00
    """
    dt = dt.replace(second=0, microsecond=0)

    minutes_past_interval = dt.minute % interval_minutes
    if minutes_past_interval == 0:
        return dt

    minutes_to_add = interval_minutes - minutes_past_interval
    return dt + timedelta(minutes=minutes_to_add)


def build_search_window() -> tuple[datetime, datetime]:
    now_local = datetime.now(LOCAL_TZ)

    raw_start_dt = now_local + timedelta(hours=BOOKING_WINDOW_START_HOURS)
    raw_end_dt = now_local + timedelta(hours=BOOKING_WINDOW_END_HOURS)

    start_dt = ceil_to_interval(raw_start_dt, INTERVAL_MINUTES)
    end_dt = ceil_to_interval(raw_end_dt, INTERVAL_MINUTES)

    if end_dt <= start_dt:
        raise ValueError("BOOKING_WINDOW_END_HOURS must be greater than BOOKING_WINDOW_START_HOURS")

    # Send naive datetimes to Graph, paired with GRAPH_TIMEZONE in the payload
    return start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None)


def call_get_schedule(
    access_token: str,
    anchor_user: str,
    schedules: list[str],
    start_dt: datetime,
    end_dt: datetime,
    interval_minutes: int,
) -> dict:
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


def mutual_free_slots(
    schedule_response: dict,
    start_dt: datetime,
    interval_minutes: int,
) -> list[tuple[datetime, datetime]]:
    values = schedule_response.get("value", [])
    if len(values) < 1:
        raise ValueError("Expected at least one schedule result.")

    availability_strings = []
    for entry in values:
        availability_view = entry.get("availabilityView")
        if availability_view is None:
            raise ValueError(f"Missing availabilityView for {entry.get('scheduleId')}")
        availability_strings.append(availability_view)

    slot_count = min(len(s) for s in availability_strings)

    free_ranges: list[tuple[datetime, datetime]] = []
    current_start: datetime | None = None

    for i in range(slot_count):
        slot_chars = [s[i] for s in availability_strings]
        everyone_free = all(char == "0" for char in slot_chars)

        slot_start = start_dt + timedelta(minutes=i * interval_minutes)

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


def merge_adjacent_slots(
    slots: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    if not slots:
        return []

    sorted_slots = sorted(slots, key=lambda x: x[0])
    merged = [sorted_slots[0]]

    for start, end in sorted_slots[1:]:
        last_start, last_end = merged[-1]
        if start == last_end:
            merged[-1] = (last_start, end)
        else:
            merged.append((start, end))

    return merged


def filter_to_business_hours(
    free_slots: list[tuple[datetime, datetime]],
    start_hour: int,
    end_hour: int,
    interval_minutes: int,
) -> list[tuple[datetime, datetime]]:
    filtered: list[tuple[datetime, datetime]] = []

    for range_start, range_end in free_slots:
        current = range_start

        while current < range_end:
            next_slot = min(current + timedelta(minutes=interval_minutes), range_end)

            is_weekday = current.weekday() < 5
            is_in_business_hours = start_hour <= current.hour < end_hour

            if is_weekday and is_in_business_hours:
                filtered.append((current, next_slot))

            current = next_slot

    return merge_adjacent_slots(filtered)


def to_json_output(
    search_start: datetime,
    search_end: datetime,
    graph_response: dict,
    free_slots: list[tuple[datetime, datetime]],
    users: list[str],
) -> dict:
    raw_availability = []
    for entry in graph_response.get("value", []):
        raw_availability.append(
            {
                "schedule_id": entry.get("scheduleId"),
                "availability_view": entry.get("availabilityView"),
            }
        )

    mutual_slots = [
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        for start, end in free_slots
    ]

    return {
        "query": {
            "users": users,
            "booking_window_start_hours": BOOKING_WINDOW_START_HOURS,
            "booking_window_end_hours": BOOKING_WINDOW_END_HOURS,
            "business_day_start_hour": BUSINESS_DAY_START_HOUR,
            "business_day_end_hour": BUSINESS_DAY_END_HOUR,
            "interval_minutes": INTERVAL_MINUTES,
            "search_window_start": search_start.isoformat(),
            "search_window_end": search_end.isoformat(),
            "local_timezone": str(LOCAL_TZ),
            "graph_timezone": GRAPH_TIMEZONE,
        },
        "raw_availability": raw_availability,
        "mutual_free_slots": mutual_slots,
    }


def main():
    if not USERS:
        raise ValueError("USERS must contain at least one user.")
    if len(USERS) < 2:
        raise ValueError("USERS must contain at least two users for comparison.")

    search_start, search_end = build_search_window()
    token = get_access_token()

    # Graph requires the endpoint to be called from some user context;
    # using the first user as anchor is fine.
    anchor_user = USERS[0]

    graph_response = call_get_schedule(
        access_token=token,
        anchor_user=anchor_user,
        schedules=USERS,
        start_dt=search_start,
        end_dt=search_end,
        interval_minutes=INTERVAL_MINUTES,
    )

    free_slots = mutual_free_slots(
        schedule_response=graph_response,
        start_dt=search_start,
        interval_minutes=INTERVAL_MINUTES,
    )

    free_slots = filter_to_business_hours(
        free_slots=free_slots,
        start_hour=BUSINESS_DAY_START_HOUR,
        end_hour=BUSINESS_DAY_END_HOUR,
        interval_minutes=INTERVAL_MINUTES,
    )

    output = to_json_output(
        search_start=search_start,
        search_end=search_end,
        graph_response=graph_response,
        free_slots=free_slots,
        users=USERS,
    )

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
