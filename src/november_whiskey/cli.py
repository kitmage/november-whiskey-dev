from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from november_whiskey.config import load_config
from november_whiskey.exceptions import AvailabilityError, ConfigError, GraphAPIError, HubSpotAPIError, WorkflowError
from november_whiskey.graph.auth import get_access_token
from november_whiskey.graph.availability import compute_best_start_from_graph
from november_whiskey.graph.events import build_event_payload, create_event
from november_whiskey.hubspot.form_submitter import submit_contact_form
from november_whiskey.hubspot.signal_finder import HubSpotClient, find_signal_contacts
from november_whiskey.logging_config import configure_logging
from november_whiskey.utils.json_io import render_output
from november_whiskey.utils.notifications import send_discord_webhook
from november_whiskey.utils.redaction import sanitize_error_text
from november_whiskey.utils.validation import validate_email
from november_whiskey.workflows.multi_segment import run_all_segments
from november_whiskey.workflows.private_lenders import run_private_lenders_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="november-whiskey")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output-format", choices=["json", "ndjson", "text", "mini"], default="json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("config-check")

    signal = sub.add_parser("signal")
    signal_sub = signal.add_subparsers(dest="signal_command", required=True)
    signal_find = signal_sub.add_parser("find")
    signal_find.add_argument("--campaign-id")
    signal_find.add_argument("--list-id")
    signal_find.add_argument("--lookback-hours", type=int)
    signal_find.add_argument("--signal-threshold", type=int)

    form = sub.add_parser("form")
    form_sub = form.add_subparsers(dest="form_command", required=True)
    form_submit = form_sub.add_parser("submit")
    form_submit.add_argument("--email", required=True)
    form_submit.add_argument("--dry-run", action="store_true")

    avail = sub.add_parser("availability")
    avail_sub = avail.add_subparsers(dest="availability_command", required=True)
    avail_sub.add_parser("best-start")

    event = sub.add_parser("event")
    event_sub = event.add_subparsers(dest="event_command", required=True)
    event_create = event_sub.add_parser("create")
    event_create.add_argument("--customer-name", required=True)
    event_create.add_argument("--customer-email", required=True)
    event_create.add_argument("--start")
    event_create.add_argument("--subject")
    event_create.add_argument("--location")
    event_create.add_argument("--dry-run", action="store_true")

    workflow = sub.add_parser("workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_pl = workflow_sub.add_parser("private-lenders")
    workflow_pl.add_argument("--dry-run", action="store_true")
    workflow_all = workflow_sub.add_parser("all-segments")
    workflow_all.add_argument("--segments")
    workflow_all.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=True)
    workflow_all.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.debug)

    try:
        if args.command == "config-check":
            load_config()
            print(json.dumps({"ok": True}, sort_keys=True))
            return 0

        if args.command == "workflow" and args.workflow_command == "all-segments":
            result = run_all_segments(
                segments_override=args.segments,
                continue_on_error=args.continue_on_error,
                dry_run=args.dry_run,
            )
            print(render_output(result, args.output_format))
            return 0 if result["totals"]["failed"] == 0 else 1

        config = load_config()

        if args.command == "signal" and args.signal_command == "find":
            client = HubSpotClient(config.hubspot.token)
            contacts = find_signal_contacts(
                client,
                config.hubspot,
                campaign_id=args.campaign_id,
                list_id=args.list_id,
                lookback_hours=args.lookback_hours,
                signal_threshold=args.signal_threshold,
            )
            print(render_output(contacts, args.output_format))
            return 0

        if args.command == "form" and args.form_command == "submit":
            if not validate_email(args.email):
                raise WorkflowError("Invalid --email value")
            client = HubSpotClient(config.hubspot.token)
            result = submit_contact_form(client, config.hubspot, {"email": args.email}, dry_run=args.dry_run)
            print(render_output(result, args.output_format))
            return 0

        if args.command == "availability" and args.availability_command == "best-start":
            token = get_access_token(config.graph)
            result = compute_best_start_from_graph(token, config.graph, config.scheduling, now=datetime.utcnow().astimezone())
            print(render_output(result, args.output_format))
            return 0

        if args.command == "event" and args.event_command == "create":
            if not validate_email(args.customer_email):
                raise WorkflowError("Invalid customer email")
            if args.start:
                start = args.start
            else:
                token = get_access_token(config.graph)
                avail = compute_best_start_from_graph(token, config.graph, config.scheduling, now=datetime.utcnow().astimezone())
                if not avail.best_start_time:
                    raise AvailabilityError("No best start available")
                start = avail.best_start_time.start
            payload = build_event_payload(
                config.event,
                customer_name=args.customer_name,
                customer_email=args.customer_email,
                start=start,
                timezone=config.graph.graph_timezone,
                duration_minutes=config.scheduling.default_duration_minutes,
                subject=args.subject,
                location=args.location,
            )
            if args.dry_run:
                print(render_output({"dry_run": True, "event_payload": payload}, args.output_format))
                return 0
            token = get_access_token(config.graph)
            result = create_event(token, config.event.target_calendar_user, payload)
            print(render_output(result, args.output_format))
            return 0

        if args.command == "workflow" and args.workflow_command == "private-lenders":
            stream_formats = {"text", "ndjson", "mini"}

            def _on_booking_processed(record: dict[str, Any]) -> None:
                if args.output_format in stream_formats:
                    print(render_output(record if args.output_format != "ndjson" else [record], args.output_format))
                if config.notifications.discord_webhook_url:
                    discord_message = render_output(record, "mini")
                    send_discord_webhook(config.notifications.discord_webhook_url, discord_message)

            result = run_private_lenders_workflow(
                config,
                dry_run=args.dry_run,
                on_booking_processed=_on_booking_processed,
            )
            if args.output_format not in stream_formats:
                print(render_output(result, args.output_format))
            return 0

        raise WorkflowError("Unknown command")
    except (ConfigError, HubSpotAPIError, GraphAPIError, AvailabilityError, WorkflowError) as exc:
        print(f"ERROR: {sanitize_error_text(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
