from datetime import datetime

from november_whiskey.config import SchedulingConfig
from november_whiskey.graph.availability import (
    build_search_window,
    exclude_friday_afternoon,
    exclude_lunch,
    find_mutual_free_ranges,
    score_candidate_starts,
    select_best_start,
    slice_ranges_to_intervals,
)


def _cfg() -> SchedulingConfig:
    return SchedulingConfig(
        users=["a@x.com", "b@x.com"],
        booking_window_start_hours=1,
        booking_window_end_hours=2,
        business_day_start_hour=9,
        business_day_end_hour=17,
        lunch_break_start_hour=11,
        lunch_break_start_minute=30,
        lunch_break_end_hour=13,
        lunch_break_end_minute=0,
        interval_minutes=30,
        friday_afternoon_start_hour=12,
        default_duration_minutes=30,
    )


def test_contiguous_free_blocks():
    start = datetime(2026, 1, 5, 10, 0)
    views = ["001110", "001010"]
    ranges = find_mutual_free_ranges(views, start, 30)
    assert ranges[0] == (datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 11, 0))


def test_lunch_boundary_exclusions():
    slots = [(datetime(2026, 1, 5, 11, 30), datetime(2026, 1, 5, 12, 0)), (datetime(2026, 1, 5, 13, 0), datetime(2026, 1, 5, 13, 30))]
    filtered = exclude_lunch(slots, _cfg())
    assert filtered == [slots[1]]


def test_friday_afternoon_exclusions():
    slots = [(datetime(2026, 1, 9, 11, 30), datetime(2026, 1, 9, 12, 0)), (datetime(2026, 1, 9, 12, 30), datetime(2026, 1, 9, 13, 0))]
    filtered = exclude_friday_afternoon(slots, _cfg())
    assert filtered == [slots[0]]


def test_earliest_tie_breaker():
    starts = [
        (datetime(2026, 1, 6, 10, 0), datetime(2026, 1, 6, 10, 30)),
        (datetime(2026, 1, 6, 10, 30), datetime(2026, 1, 6, 11, 0)),
        (datetime(2026, 1, 6, 11, 0), datetime(2026, 1, 6, 11, 30)),
    ]
    scored = score_candidate_starts(starts, 30)
    best = select_best_start(scored)
    assert best is not None
    assert best.start == "2026-01-06T10:30:00"


def test_dst_window_build():
    now = datetime(2026, 3, 8, 9, 0).astimezone()
    cfg = _cfg()
    start, end = build_search_window(now, cfg, "America/Los_Angeles")
    assert end > start


def test_slice_ranges_to_intervals():
    ranges = [(datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 11, 0))]
    slots = slice_ranges_to_intervals(ranges, 30)
    assert len(slots) == 2
