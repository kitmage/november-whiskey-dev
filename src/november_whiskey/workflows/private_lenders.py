from __future__ import annotations

import time
from datetime import datetime

from november_whiskey.config import AppConfig
from november_whiskey.exceptions import WorkflowError
from november_whiskey.graph.auth import get_access_token
from november_whiskey.graph.availability import compute_best_start_from_graph
from november_whiskey.graph.events import build_event_payload, create_event
from november_whiskey.hubspot.form_submitter import submit_contact_form
from november_whiskey.hubspot.signal_finder import HubSpotClient, SignalContact, find_signal_contacts
from november_whiskey.utils.validation import validate_email


def run_private_lenders_workflow(config: AppConfig, dry_run: bool = False) -> list[dict]:
    hs_client = HubSpotClient(config.hubspot.token)
    contacts: list[SignalContact] = find_signal_contacts(hs_client, config.hubspot)
    if not contacts:
        return []

    token = get_access_token(config.graph)
    outputs = []
    for i, contact in enumerate(contacts):
        if not validate_email(contact.email):
            raise WorkflowError(f"Invalid contact email: {contact.email}")
        availability = compute_best_start_from_graph(token, config.graph, config.scheduling, now=datetime.utcnow().astimezone())
        if not availability.best_start_time:
            raise WorkflowError("No mutual availability found")

        event_payload = build_event_payload(
            config.event,
            customer_name=contact.fullName,
            customer_email=contact.email,
            start=availability.best_start_time.start,
            timezone=config.graph.graph_timezone,
            duration_minutes=config.scheduling.default_duration_minutes,
        )

        if dry_run:
            event_result = {"dry_run": True, "event_payload": event_payload}
            form_result = submit_contact_form(hs_client, config.hubspot, {"email": contact.email}, dry_run=True)
        else:
            event_result = create_event(token, config.event.target_calendar_user, event_payload)
            form_result = submit_contact_form(hs_client, config.hubspot, {"email": contact.email}, dry_run=False)

        outputs.append({
            "contact": contact,
            "best_start_time": availability.best_start_time,
            "event": event_result,
            "form": form_result,
        })
        if i < len(contacts) - 1 and config.event.inter_event_delay_seconds > 0:
            time.sleep(config.event.inter_event_delay_seconds)
    return outputs
