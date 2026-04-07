from __future__ import annotations

import json

from november_whiskey.graph.availability import BestStartTime
from november_whiskey.hubspot.signal_finder import SignalContact
from november_whiskey.utils.json_io import render_output, to_obj


def test_to_obj_recursively_serializes_nested_dataclasses_in_mappings_and_lists():
    payload = {
        "contact": SignalContact(contactId="123", email="a@example.com", fullName="A", openCount=2),
        "best_start_time": BestStartTime(
            start="2026-04-06T12:00:00",
            score=1,
            buffer_before_blocks=2,
            buffer_after_blocks=3,
        ),
        "items": [BestStartTime(start="2026-04-06T12:15:00", score=0, buffer_before_blocks=0, buffer_after_blocks=1)],
    }

    obj = to_obj(payload)

    assert obj["contact"]["email"] == "a@example.com"
    assert obj["best_start_time"]["start"] == "2026-04-06T12:00:00"
    assert obj["items"][0]["buffer_after_blocks"] == 1


def test_render_output_json_handles_private_lenders_workflow_shape():
    result = [
        {
            "contact": SignalContact(contactId="123", email="a@example.com", fullName="A", openCount=2),
            "best_start_time": BestStartTime(
                start="2026-04-06T12:00:00",
                score=1,
                buffer_before_blocks=2,
                buffer_after_blocks=3,
            ),
            "event": {"dry_run": True},
            "form": {"dry_run": True},
        }
    ]

    rendered = render_output(result, "json")

    loaded = json.loads(rendered)
    assert loaded[0]["contact"]["contactId"] == "123"
    assert loaded[0]["best_start_time"]["score"] == 1


def test_render_output_mini_handles_private_lenders_record():
    record = {
        "contact": SignalContact(contactId="123", email="a@example.com", fullName="A", openCount=2),
        "best_start_time": BestStartTime(
            start="2026-04-06T12:00:00",
            score=1,
            buffer_before_blocks=2,
            buffer_after_blocks=3,
        ),
    }
    rendered = render_output(record, "mini")
    assert rendered == "🟢 Event booked with A a@example.com 2026-04-06T12:00:00"


def test_render_output_mini_prefers_pci_datetime_when_present():
    record = {
        "contact": {"fullName": "A", "email": "a@example.com"},
        "best_start_time": {"start": "2026-04-06T12:00:00"},
        "pci_datetime": "Monday, 4/6 at 12:00 pm Pacific",
    }
    rendered = render_output(record, "mini")
    assert rendered == "🟢 Event booked with A a@example.com Monday, 4/6 at 12:00 pm Pacific"
