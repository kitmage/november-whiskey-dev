from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from november_whiskey.config import GraphConfig, SchedulingConfig
from november_whiskey.exceptions import AvailabilityError, GraphAPIError
from november_whiskey.utils.time import ceil_to_interval


@dataclass(frozen=True)
class BestStartTime:
    start: str
    score: int
    buffer_before_blocks: int
    buffer_after_blocks: int
    free_user_count: int = 0


@dataclass(frozen=True)
class AvailabilityResult:
    best_start_time: BestStartTime | None


def build_search_window(now: datetime, config: SchedulingConfig, local_timezone: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(local_timezone)
    now_local = now.astimezone(tz)
    start = ceil_to_interval(now_local + timedelta(hours=config.booking_window_start_hours), config.interval_minutes)
    end = ceil_to_interval(now_local + timedelta(hours=config.booking_window_end_hours), config.interval_minutes)
    if end <= start:
        raise AvailabilityError("Invalid scheduling booking window")
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def parse_schedule_views(response: dict) -> list[str]:
    views = [item.get("availabilityView") for item in response.get("value", []) if item.get("availabilityView") is not None]
    if not views:
        raise AvailabilityError("Graph response did not contain availabilityView values")
    return views


def find_mutual_free_ranges(
    schedule_views: list[str],
    start_dt: datetime,
    interval_minutes: int,
    min_free_users: int = 2,
) -> list[tuple[datetime, datetime]]:
    slot_count = min(len(s) for s in schedule_views)
    ranges = []
    current_start = None
    for i in range(slot_count):
        slot_start = start_dt + timedelta(minutes=i * interval_minutes)
        free_user_count = sum(1 for view in schedule_views if view[i] == "0")
        enough_users_free = free_user_count >= min_free_users
        if enough_users_free and current_start is None:
            current_start = slot_start
        if not enough_users_free and current_start is not None:
            ranges.append((current_start, slot_start))
            current_start = None
    if current_start is not None:
        ranges.append((current_start, start_dt + timedelta(minutes=slot_count * interval_minutes)))
    return ranges


def slice_ranges_to_intervals(ranges: list[tuple[datetime, datetime]], interval_minutes: int) -> list[tuple[datetime, datetime]]:
    slots = []
    step = timedelta(minutes=interval_minutes)
    for start, end in ranges:
        current = start
        while current < end:
            next_slot = min(current + step, end)
            slots.append((current, next_slot))
            current = next_slot
    return slots


def filter_business_hours(slots: list[tuple[datetime, datetime]], config: SchedulingConfig) -> list[tuple[datetime, datetime]]:
    return [s for s in slots if s[0].weekday() < 5 and config.business_day_start_hour <= s[0].hour < config.business_day_end_hour]


def exclude_lunch(slots: list[tuple[datetime, datetime]], config: SchedulingConfig) -> list[tuple[datetime, datetime]]:
    out = []
    for start, end in slots:
        lunch_start = start.replace(hour=config.lunch_break_start_hour, minute=config.lunch_break_start_minute, second=0, microsecond=0)
        lunch_end = start.replace(hour=config.lunch_break_end_hour, minute=config.lunch_break_end_minute, second=0, microsecond=0)
        if not (start < lunch_end and end > lunch_start):
            out.append((start, end))
    return out


def exclude_friday_afternoon(slots: list[tuple[datetime, datetime]], config: SchedulingConfig) -> list[tuple[datetime, datetime]]:
    return [s for s in slots if not (s[0].weekday() == 4 and s[0].hour >= config.friday_afternoon_start_hour)]


def count_free_users_by_slot(schedule_views: list[str], start_dt: datetime, interval_minutes: int) -> dict[datetime, int]:
    slot_count = min(len(s) for s in schedule_views)
    return {
        start_dt + timedelta(minutes=i * interval_minutes): sum(1 for view in schedule_views if view[i] == "0")
        for i in range(slot_count)
    }


def score_candidate_starts(
    slots: list[tuple[datetime, datetime]],
    interval_minutes: int,
    slot_free_counts: dict[datetime, int] | None = None,
) -> list[dict]:
    starts = [s[0] for s in slots]
    scored = []
    interval = timedelta(minutes=interval_minutes)
    for i, dt in enumerate(starts):
        before = 0
        j = i - 1
        while j >= 0 and starts[j + 1] - starts[j] == interval:
            before += 1
            j -= 1
        after = 0
        j = i + 1
        while j < len(starts) and starts[j] - starts[j - 1] == interval:
            after += 1
            j += 1
        free_user_count = slot_free_counts.get(dt, 0) if slot_free_counts else 0
        scored.append(
            {
                "start": dt,
                "score": free_user_count * 1000 + min(before, after),
                "buffer_before_blocks": before,
                "buffer_after_blocks": after,
                "free_user_count": free_user_count,
            }
        )
    return scored


def select_best_start(scored: list[dict]) -> BestStartTime | None:
    if not scored:
        return None
    best_score = max(item["score"] for item in scored)
    best = min([item for item in scored if item["score"] == best_score], key=lambda item: item["start"])
    return BestStartTime(
        start=best["start"].isoformat(),
        score=best["score"],
        buffer_before_blocks=best["buffer_before_blocks"],
        buffer_after_blocks=best["buffer_after_blocks"],
        free_user_count=best.get("free_user_count", 0),
    )


def get_schedule(access_token: str, graph: GraphConfig, scheduling: SchedulingConfig, start_dt: datetime, end_dt: datetime, timeout: int = 30) -> dict:
    import requests

    url = f"https://graph.microsoft.com/v1.0/users/{scheduling.users[0]}/calendar/getSchedule"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Prefer": f'outlook.timezone="{graph.graph_timezone}"',
    }
    payload = {
        "schedules": scheduling.users,
        "startTime": {"dateTime": start_dt.strftime('%Y-%m-%dT%H:%M:%S'), "timeZone": graph.graph_timezone},
        "endTime": {"dateTime": end_dt.strftime('%Y-%m-%dT%H:%M:%S'), "timeZone": graph.graph_timezone},
        "availabilityViewInterval": scheduling.interval_minutes,
    }
    for attempt in range(4):
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
            continue
        if not response.ok:
            raise GraphAPIError(f"Graph getSchedule failed ({response.status_code})")
        return response.json()
    raise GraphAPIError("Graph getSchedule failed after retries")


def compute_best_start_from_graph(access_token: str, graph: GraphConfig, scheduling: SchedulingConfig, now: datetime) -> AvailabilityResult:
    start, end = build_search_window(now, scheduling, graph.local_timezone)
    response = get_schedule(access_token, graph, scheduling, start, end)
    views = parse_schedule_views(response)
    minimum_free_users = min(2, len(scheduling.users))
    free_ranges = find_mutual_free_ranges(views, start, scheduling.interval_minutes, min_free_users=minimum_free_users)
    slots = slice_ranges_to_intervals(free_ranges, scheduling.interval_minutes)
    slots = filter_business_hours(slots, scheduling)
    slots = exclude_lunch(slots, scheduling)
    slots = exclude_friday_afternoon(slots, scheduling)
    free_counts = count_free_users_by_slot(views, start, scheduling.interval_minutes)
    return AvailabilityResult(best_start_time=select_best_start(score_candidate_starts(slots, scheduling.interval_minutes, free_counts)))
