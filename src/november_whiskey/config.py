from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from .exceptions import ConfigError

DEFAULT_AUDIENCE_SEGMENT = "private-lenders"
AUDIENCE_SEGMENTS_ENV_VAR = "AUDIENCE_SEGMENTS"
_SEGMENT_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class HubSpotConfig:
    token: str
    app_id: int
    list_id: str
    property_name: str
    campaign_id: str
    lookback_window_hours: int
    signal_threshold: int
    portal_id: str
    form_id: str


@dataclass(frozen=True)
class GraphConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    graph_timezone: str
    local_timezone: str


@dataclass(frozen=True)
class SchedulingConfig:
    users: list[str]
    booking_window_start_hours: int
    booking_window_end_hours: int
    business_day_start_hour: int
    business_day_end_hour: int
    lunch_break_start_hour: int
    lunch_break_start_minute: int
    lunch_break_end_hour: int
    lunch_break_end_minute: int
    interval_minutes: int
    friday_afternoon_start_hour: int
    default_duration_minutes: int


@dataclass(frozen=True)
class EventConfig:
    default_subject_template: str
    default_location: str
    inter_event_delay_seconds: float
    enable_teams_meeting: bool
    target_calendar_user: str


@dataclass(frozen=True)
class NotificationsConfig:
    discord_webhook_url: str | None


@dataclass(frozen=True)
class AppConfig:
    hubspot: HubSpotConfig
    graph: GraphConfig
    scheduling: SchedulingConfig
    event: EventConfig
    notifications: NotificationsConfig


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        if default is None:
            raise ConfigError(f"Missing required integer environment variable: {name}")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer value for {name}: {raw}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid numeric value for {name}: {raw}") from exc


def _bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_segment(segment: str, source: str) -> None:
    if not segment:
        raise ConfigError(f"{source} contains an empty segment value. Remove empty entries like consecutive commas.")
    if ".." in segment or "/" in segment or "\\" in segment:
        raise ConfigError(
            f"Invalid segment '{segment}' from {source}: path traversal is not allowed. "
            "Use only simple segment names like 'private-lenders'."
        )
    if not _SEGMENT_ALLOWED_PATTERN.fullmatch(segment):
        raise ConfigError(
            f"Invalid segment '{segment}' from {source}: only letters, digits, hyphens, and underscores are allowed."
        )


def parse_segment_list(raw_segments: str, *, source: str) -> list[str]:
    parsed_segments: list[str] = []
    seen_segments: set[str] = set()

    for item in raw_segments.split(","):
        segment = item.strip()
        if not segment:
            continue
        _validate_segment(segment, source)
        if segment not in seen_segments:
            seen_segments.add(segment)
            parsed_segments.append(segment)
    return parsed_segments


def resolve_audience_segments(segments_override: str | None = None) -> list[str]:
    if segments_override is not None:
        segments = parse_segment_list(segments_override, source="CLI --segments")
        if not segments:
            raise ConfigError(
                "CLI --segments override was provided but no valid segments were found. "
                "Pass a comma-separated list like '--segments private-lenders,credit-unions'."
            )
        return segments

    env_segments_raw = os.getenv(AUDIENCE_SEGMENTS_ENV_VAR)
    if env_segments_raw is not None:
        env_segments = parse_segment_list(env_segments_raw, source=AUDIENCE_SEGMENTS_ENV_VAR)
        if not env_segments:
            raise ConfigError(
                f"{AUDIENCE_SEGMENTS_ENV_VAR} is set but no valid segments were found. "
                "Set it to a comma-separated list like 'private-lenders,credit-unions' or unset it."
            )
        return env_segments

    audience_segment = os.getenv("AUDIENCE_SEGMENT", DEFAULT_AUDIENCE_SEGMENT).strip() or DEFAULT_AUDIENCE_SEGMENT
    _validate_segment(audience_segment, "AUDIENCE_SEGMENT")
    return [audience_segment]


def load_config() -> AppConfig:
    load_dotenv(os.getenv("GLOBAL_ENV_PATH", ".env"))
    audience_segment = resolve_audience_segments()[0]
    segment_env_path = Path(os.getenv("AUDIENCE_ENV_PATH", f"app/{audience_segment}/.env"))
    if not segment_env_path.exists():
        raise ConfigError(
            f"Missing audience config file for '{audience_segment}': {segment_env_path}. "
            "Create this hidden file and move segment-specific values there."
        )
    load_dotenv(segment_env_path, override=True)
    segment_values = {k: v for k, v in dotenv_values(segment_env_path).items() if v is not None}

    segment_required_keys = (
        "HUBSPOT_LIST_ID",
        "HUBSPOT_CAMPAIGN_ID",
        "HUBSPOT_PORTAL_ID",
        "HUBSPOT_FORM_ID",
        "SCHEDULING_USERS",
        "DEFAULT_SUBJECT_TEMPLATE",
        "DEFAULT_LOCATION",
        "EVENT_INTER_DELAY_SECONDS",
        "ENABLE_TEAMS_MEETING",
    )
    for key in segment_required_keys:
        if not segment_values.get(key, "").strip():
            raise ConfigError(f"Audience config file is missing required value: {key}")
    hubspot = HubSpotConfig(
        token=_require("HUBSPOT_TOKEN"),
        app_id=_int("HUBSPOT_APP_ID", 2286),
        list_id=_require("HUBSPOT_LIST_ID"),
        property_name=os.getenv("HUBSPOT_PROPERTY_NAME", "pci_automation"),
        campaign_id=_require("HUBSPOT_CAMPAIGN_ID"),
        lookback_window_hours=_int("HUBSPOT_LOOKBACK_WINDOW_HOURS", 360),
        signal_threshold=_int("HUBSPOT_SIGNAL_THRESHOLD", 1),
        portal_id=_require("HUBSPOT_PORTAL_ID"),
        form_id=_require("HUBSPOT_FORM_ID"),
    )
    graph = GraphConfig(
        tenant_id=_require("TENANT_ID"),
        client_id=_require("CLIENT_ID"),
        client_secret=_require("CLIENT_SECRET"),
        graph_timezone=os.getenv("GRAPH_TIMEZONE", "Pacific Standard Time"),
        local_timezone=os.getenv("LOCAL_TIMEZONE", "America/Los_Angeles"),
    )
    users = [x.strip() for x in os.getenv("SCHEDULING_USERS", "").split(",") if x.strip()]
    if len(users) < 1:
        raise ConfigError("SCHEDULING_USERS must contain at least one user")
    scheduling = SchedulingConfig(
        users=users,
        booking_window_start_hours=_int("BOOKING_WINDOW_START_HOURS", 144),
        booking_window_end_hours=_int("BOOKING_WINDOW_END_HOURS", 240),
        business_day_start_hour=_int("BUSINESS_DAY_START_HOUR", 10),
        business_day_end_hour=_int("BUSINESS_DAY_END_HOUR", 16),
        lunch_break_start_hour=_int("LUNCH_BREAK_START_HOUR", 11),
        lunch_break_start_minute=_int("LUNCH_BREAK_START_MINUTE", 30),
        lunch_break_end_hour=_int("LUNCH_BREAK_END_HOUR", 13),
        lunch_break_end_minute=_int("LUNCH_BREAK_END_MINUTE", 0),
        interval_minutes=_int("INTERVAL_MINUTES", 30),
        friday_afternoon_start_hour=_int("FRIDAY_AFTERNOON_START_HOUR", 12),
        default_duration_minutes=_int("DEFAULT_DURATION_MINUTES", 30),
    )
    event = EventConfig(
        default_subject_template=os.getenv("DEFAULT_SUBJECT_TEMPLATE", "30min Meeting - {customer_name}"),
        default_location=os.getenv("DEFAULT_LOCATION", "Microsoft Teams"),
        inter_event_delay_seconds=_float("EVENT_INTER_DELAY_SECONDS", 1.0),
        enable_teams_meeting=_bool("ENABLE_TEAMS_MEETING", True),
        target_calendar_user=_require("MIKE_ID"),
    )
    notifications = NotificationsConfig(
        discord_webhook_url=(os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK") or "").strip() or None,
    )
    if scheduling.booking_window_end_hours <= scheduling.booking_window_start_hours:
        raise ConfigError("BOOKING_WINDOW_END_HOURS must be greater than BOOKING_WINDOW_START_HOURS")
    return AppConfig(hubspot=hubspot, graph=graph, scheduling=scheduling, event=event, notifications=notifications)
