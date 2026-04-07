from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from november_whiskey.config import AppConfig
from november_whiskey.exceptions import WorkflowError
from november_whiskey.graph.auth import get_access_token
from november_whiskey.graph.availability import compute_best_start_from_graph
from november_whiskey.graph.events import build_event_payload, create_event
from november_whiskey.hubspot.form_submitter import submit_contact_form
from november_whiskey.hubspot.signal_finder import HubSpotClient, SignalContact, find_signal_contacts
from november_whiskey.utils.time import format_pacific_human
from november_whiskey.utils.validation import validate_email


def _extract_teams_join_url(event_result: dict) -> str | None:
    online_meeting = event_result.get("onlineMeeting")
    if isinstance(online_meeting, dict):
        join_url = online_meeting.get("joinUrl")
        if join_url:
            return str(join_url)
    online_meeting_url = event_result.get("onlineMeetingUrl")
    if online_meeting_url:
        return str(online_meeting_url)
    return None


def run_private_lenders_workflow(
    config: AppConfig,
    dry_run: bool = False,
    on_booking_processed: Callable[[dict], None] | None = None,
) -> list[dict]:
    hs_client = HubSpotClient(config.hubspot.token)
    contacts: list[SignalContact] = find_signal_contacts(hs_client, config.hubspot)
    if not contacts:
        return []

    token = get_access_token(config.graph)
    outputs = []
    for i, contact in enumerate(contacts):
        if not validate_email(contact.email):
            output_record = {"contact": contact, "error": f"Invalid contact email: {contact.email}", "error_code": "invalid_email"}
            outputs.append(output_record)
            if on_booking_processed is not None:
                on_booking_processed(output_record)
            continue
        availability = compute_best_start_from_graph(token, config.graph, config.scheduling, now=datetime.utcnow().astimezone())
        if not availability.best_start_time:
            output_record = {"contact": contact, "error": "No mutual availability found", "error_code": "no_availability"}
            outputs.append(output_record)
            if on_booking_processed is not None:
                on_booking_processed(output_record)
            continue

        event_payload = build_event_payload(
            config.event,
            customer_name=contact.fullName,
            customer_email=contact.email,
            start=availability.best_start_time.start,
            timezone=config.graph.graph_timezone,
            duration_minutes=config.scheduling.default_duration_minutes,
        )

        try:
            if dry_run:
                event_result = {"dry_run": True, "event_payload": event_payload}
            else:
                event_result = create_event(token, config.event.target_calendar_user, event_payload)

            form_event = {
                "email": contact.email,
                "openCount": contact.openCount,
                "pci_datetime": format_pacific_human(availability.best_start_time.start),
            }
            teams_join_url = _extract_teams_join_url(event_result)
            if teams_join_url:
                form_event["teams_join_url"] = teams_join_url

            form_result = submit_contact_form(hs_client, config.hubspot, form_event, dry_run=dry_run)

            output_record = {
                "contact": contact,
                "best_start_time": availability.best_start_time,
                "pci_datetime": form_event["pci_datetime"],
                "event": event_result,
                "form": form_result,
            }
        except Exception as exc:
            output_record = {"contact": contact, "error": str(exc), "error_code": "booking_error"}
        outputs.append(output_record)
        if on_booking_processed is not None:
            on_booking_processed(output_record)
        if i < len(contacts) - 1 and config.event.inter_event_delay_seconds > 0:
            time.sleep(config.event.inter_event_delay_seconds)
    return outputs
