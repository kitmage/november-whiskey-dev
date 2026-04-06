import os

import pytest

from november_whiskey.config import parse_segment_list
from november_whiskey.exceptions import ConfigError, WorkflowError
from november_whiskey.workflows import multi_segment


def test_parse_segment_list_dedupes_and_strips():
    assert parse_segment_list(" private-lenders, credit_unions ,private-lenders ", source="test") == [
        "private-lenders",
        "credit_unions",
    ]


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [
        ("private-lenders,../bad", "path traversal is not allowed"),
        ("private-lenders,with/slash", "path traversal is not allowed"),
        ("private-lenders,with\\slash", "path traversal is not allowed"),
        ("private-lenders,$oops", "only letters, digits, hyphens, and underscores are allowed"),
        ("private-lenders,-leading-hyphen", "only letters, digits, hyphens, and underscores are allowed"),
    ],
)
def test_parse_segment_list_rejects_malformed_values(raw_value, message):
    with pytest.raises(ConfigError, match=message):
        parse_segment_list(raw_value, source="test")


def test_resolve_segments_cli_precedence(monkeypatch):
    monkeypatch.setenv("AUDIENCE_SEGMENTS", "env-a,env-b")
    assert multi_segment.resolve_segments("cli-a, cli-b") == ["cli-a", "cli-b"]


def test_resolve_segments_env_fallback(monkeypatch):
    monkeypatch.setenv("AUDIENCE_SEGMENTS", "env-a, env-b, env-a")
    assert multi_segment.resolve_segments(None) == ["env-a", "env-b"]


def test_resolve_segments_single_segment_fallback(monkeypatch):
    monkeypatch.delenv("AUDIENCE_SEGMENTS", raising=False)
    monkeypatch.setenv("AUDIENCE_SEGMENT", "single-segment")
    assert multi_segment.resolve_segments(None) == ["single-segment"]


def test_run_all_segments_stops_on_error(monkeypatch):
    called_segments = []

    def fake_load_config():
        segment = os.environ.get("AUDIENCE_SEGMENT")
        called_segments.append(segment)
        if len(called_segments) == 2:
            raise ConfigError("bad config")
        return object()

    def fake_runner(config, dry_run=False):
        _ = config
        _ = dry_run
        return [{"id": 1}]

    monkeypatch.setattr(multi_segment, "load_config", fake_load_config)
    monkeypatch.setattr(multi_segment, "get_workflow_runner", lambda segment, strict=False: fake_runner)
    monkeypatch.setattr(
        multi_segment,
        "resolve_segments",
        lambda segments_override=None: ["private-lenders", "private-lenders", "private-lenders"],
    )

    result = multi_segment.run_all_segments(None, continue_on_error=False)

    assert called_segments == ["private-lenders", "private-lenders"]
    assert result["totals"] == {"total_segments": 2, "succeeded": 1, "failed": 1}
    assert [row["status"] for row in result["results"]] == ["success", "failed"]


def test_run_all_segments_continues_on_error(monkeypatch):
    called_segments = []

    def fake_load_config():
        segment = os.environ.get("AUDIENCE_SEGMENT")
        called_segments.append(segment)
        if len(called_segments) == 1:
            raise ConfigError("first failure")
        return object()

    def fake_runner(config, dry_run=False):
        _ = config
        _ = dry_run
        return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(multi_segment, "load_config", fake_load_config)
    monkeypatch.setattr(multi_segment, "get_workflow_runner", lambda segment, strict=False: fake_runner)
    monkeypatch.setattr(
        multi_segment,
        "resolve_segments",
        lambda segments_override=None: ["private-lenders", "private-lenders"],
    )

    result = multi_segment.run_all_segments(None, continue_on_error=True)

    assert called_segments == ["private-lenders", "private-lenders"]
    assert result["totals"] == {"total_segments": 2, "succeeded": 1, "failed": 1}
    assert result["results"][0]["error"] == "first failure"
    assert result["results"][1]["key_output_fields"]["records_processed"] == 2


def test_run_all_segments_unregistered_segment_non_strict(monkeypatch):
    monkeypatch.setattr(
        multi_segment,
        "resolve_segments",
        lambda segments_override=None: ["unknown-segment"],
    )

    result = multi_segment.run_all_segments(None, continue_on_error=True, strict_missing_workflow=False)

    assert result["totals"] == {"total_segments": 1, "succeeded": 0, "failed": 1}
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["error"] == "No workflow registered for segment 'unknown-segment'"


def test_run_all_segments_unregistered_segment_strict(monkeypatch):
    monkeypatch.setattr(
        multi_segment,
        "resolve_segments",
        lambda segments_override=None: ["unknown-segment"],
    )

    with pytest.raises(WorkflowError, match="No workflow registered for segment 'unknown-segment'"):
        multi_segment.run_all_segments(None, continue_on_error=False, strict_missing_workflow=True)


def test_run_all_segments_two_segments_both_succeed(monkeypatch):
    called_segments = []

    def fake_load_config():
        segment = os.environ.get("AUDIENCE_SEGMENT")
        called_segments.append(segment)
        return {"segment": segment}

    def fake_runner(config, dry_run=False):
        _ = dry_run
        return {"segment": config["segment"], "ok": True}

    monkeypatch.setattr(multi_segment, "load_config", fake_load_config)
    monkeypatch.setattr(multi_segment, "get_workflow_runner", lambda segment, strict=False: fake_runner)
    monkeypatch.setattr(multi_segment, "resolve_segments", lambda segments_override=None: ["seg-a", "seg-b"])

    result = multi_segment.run_all_segments(None, continue_on_error=True)

    assert called_segments == ["seg-a", "seg-b"]
    assert result["totals"] == {"total_segments": 2, "succeeded": 2, "failed": 0}
    assert result["results"] == [
        {
            "segment": "seg-a",
            "status": "success",
            "error": None,
            "key_output_fields": {"output_type": "dict", "keys": ["ok", "segment"]},
        },
        {
            "segment": "seg-b",
            "status": "success",
            "error": None,
            "key_output_fields": {"output_type": "dict", "keys": ["ok", "segment"]},
        },
    ]


def test_run_all_segments_first_fails_then_second_succeeds_with_continue_on_error(monkeypatch):
    called_segments = []

    def fake_load_config():
        segment = os.environ.get("AUDIENCE_SEGMENT")
        called_segments.append(segment)
        if segment == "seg-a":
            raise ConfigError("seg-a failed")
        return {"segment": segment}

    def fake_runner(config, dry_run=False):
        _ = dry_run
        return [{"segment": config["segment"]}]

    monkeypatch.setattr(multi_segment, "load_config", fake_load_config)
    monkeypatch.setattr(multi_segment, "get_workflow_runner", lambda segment, strict=False: fake_runner)
    monkeypatch.setattr(multi_segment, "resolve_segments", lambda segments_override=None: ["seg-a", "seg-b"])

    result = multi_segment.run_all_segments(None, continue_on_error=True)

    assert called_segments == ["seg-a", "seg-b"]
    assert result["totals"] == {"total_segments": 2, "succeeded": 1, "failed": 1}
    assert result["results"][0] == {
        "segment": "seg-a",
        "status": "failed",
        "error": "seg-a failed",
        "key_output_fields": {},
    }
    assert result["results"][1] == {
        "segment": "seg-b",
        "status": "success",
        "error": None,
        "key_output_fields": {"records_processed": 1, "output_type": "list"},
    }


def test_run_all_segments_first_fails_and_aborts_with_continue_on_error_disabled(monkeypatch):
    called_segments = []

    def fake_load_config():
        segment = os.environ.get("AUDIENCE_SEGMENT")
        called_segments.append(segment)
        raise ConfigError(f"{segment} failed")

    def fake_runner(config, dry_run=False):
        _ = config
        _ = dry_run
        return []

    monkeypatch.setattr(multi_segment, "load_config", fake_load_config)
    monkeypatch.setattr(multi_segment, "get_workflow_runner", lambda segment, strict=False: fake_runner)
    monkeypatch.setattr(multi_segment, "resolve_segments", lambda segments_override=None: ["seg-a", "seg-b"])

    result = multi_segment.run_all_segments(None, continue_on_error=False)

    assert called_segments == ["seg-a"]
    assert result["totals"] == {"total_segments": 1, "succeeded": 0, "failed": 1}
    assert result["results"] == [
        {
            "segment": "seg-a",
            "status": "failed",
            "error": "seg-a failed",
            "key_output_fields": {},
        }
    ]
