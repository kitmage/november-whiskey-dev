from __future__ import annotations

from types import SimpleNamespace

from november_whiskey.graph.availability import AvailabilityResult, BestStartTime
from november_whiskey.hubspot.signal_finder import SignalContact
from november_whiskey.workflows import private_lenders


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        hubspot=SimpleNamespace(token="hs-token"),
        graph=SimpleNamespace(graph_timezone="Pacific Standard Time"),
        scheduling=SimpleNamespace(default_duration_minutes=30),
        event=SimpleNamespace(target_calendar_user="calendar-user", inter_event_delay_seconds=0),
    )


def test_private_lenders_form_submission_includes_pci_datetime_and_teams_url(monkeypatch):
    cfg = _config()
    captured_form_event: dict = {}

    monkeypatch.setattr(private_lenders, "HubSpotClient", lambda token: SimpleNamespace(token=token))
    monkeypatch.setattr(
        private_lenders,
        "find_signal_contacts",
        lambda client, hubspot_cfg: [SignalContact(contactId="1", email="john@example.com", fullName="John Doe", openCount=16)],
    )
    monkeypatch.setattr(private_lenders, "get_access_token", lambda graph_cfg: "graph-token")
    monkeypatch.setattr(
        private_lenders,
        "compute_best_start_from_graph",
        lambda token, graph_cfg, scheduling_cfg, now: AvailabilityResult(
            best_start_time=BestStartTime(start="2026-04-14T13:00:00", score=0, buffer_before_blocks=0, buffer_after_blocks=1)
        ),
    )
    monkeypatch.setattr(private_lenders, "build_event_payload", lambda *args, **kwargs: {"subject": "x"})
    monkeypatch.setattr(
        private_lenders,
        "create_event",
        lambda token, target_user, payload: {"onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/test"}},
    )

    def _submit_contact_form(client, hubspot_cfg, event, dry_run=False):
        _ = (client, hubspot_cfg, dry_run)
        captured_form_event.update(event)
        return {"submitted": True, "status": 200}

    monkeypatch.setattr(private_lenders, "submit_contact_form", _submit_contact_form)

    private_lenders.run_private_lenders_workflow(cfg, dry_run=False)

    assert captured_form_event["email"] == "john@example.com"
    assert captured_form_event["openCount"] == 16
    assert captured_form_event["pci_datetime"] == "Tuesday, 4/14 at 1:00 pm Pacific"
    assert captured_form_event["teams_join_url"] == "https://teams.microsoft.com/l/meetup-join/test"


def test_private_lenders_no_availability_returns_error_record(monkeypatch):
    cfg = _config()
    monkeypatch.setattr(private_lenders, "HubSpotClient", lambda token: SimpleNamespace(token=token))
    monkeypatch.setattr(
        private_lenders,
        "find_signal_contacts",
        lambda client, hubspot_cfg: [SignalContact(contactId="1", email="john@example.com", fullName="John Doe", openCount=16)],
    )
    monkeypatch.setattr(private_lenders, "get_access_token", lambda graph_cfg: "graph-token")
    monkeypatch.setattr(
        private_lenders,
        "compute_best_start_from_graph",
        lambda token, graph_cfg, scheduling_cfg, now: AvailabilityResult(best_start_time=None),
    )

    records = private_lenders.run_private_lenders_workflow(cfg, dry_run=False)
    assert records[0]["error_code"] == "no_availability"
