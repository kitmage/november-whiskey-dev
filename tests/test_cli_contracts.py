import json

from november_whiskey import cli
from november_whiskey.cli import build_parser


def test_parser_has_expected_commands():
    parser = build_parser()
    args = parser.parse_args(["signal", "find"])
    assert args.command == "signal"


def test_parser_output_format_choices():
    parser = build_parser()
    args = parser.parse_args(["--output-format", "json", "config-check"])
    assert args.output_format == "json"
    args_mini = parser.parse_args(["--output-format", "mini", "config-check"])
    assert args_mini.output_format == "mini"


def test_parser_workflow_all_segments_arguments():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--output-format",
            "text",
            "workflow",
            "all-segments",
            "--segments",
            "private-lenders,credit-unions",
            "--no-continue-on-error",
            "--dry-run",
        ]
    )
    assert args.command == "workflow"
    assert args.workflow_command == "all-segments"
    assert args.output_format == "text"
    assert args.segments == "private-lenders,credit-unions"
    assert args.continue_on_error is False
    assert args.dry_run is True


def test_workflow_all_segments_exit_code_zero_on_success(monkeypatch, capsys):
    def fake_run_all_segments(**kwargs):
        assert kwargs["segments_override"] == "seg-a,seg-b"
        assert kwargs["continue_on_error"] is True
        assert kwargs["dry_run"] is True
        return {
            "run_id": "run-1",
            "segments": ["seg-a", "seg-b"],
            "continue_on_error": True,
            "dry_run": True,
            "strict_missing_workflow": False,
            "totals": {"total_segments": 2, "succeeded": 2, "failed": 0},
            "summary": {"total_segments": 2, "succeeded": 2, "failed": 0, "failed_segments": []},
            "results": [
                {"segment": "seg-a", "run_id": "run-1", "status": "success", "error": None, "duration_ms": 1, "key_output_fields": {"output_type": "list", "records_processed": 1}},
                {"segment": "seg-b", "run_id": "run-1", "status": "success", "error": None, "duration_ms": 1, "key_output_fields": {"output_type": "dict", "keys": ["ok"]}},
            ],
        }

    monkeypatch.setattr(cli, "run_all_segments", fake_run_all_segments)

    exit_code = cli.main(["workflow", "all-segments", "--segments", "seg-a,seg-b", "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    rendered = json.loads(captured.out)
    assert rendered["totals"] == {"total_segments": 2, "succeeded": 2, "failed": 0}
    assert rendered["summary"]["failed_segments"] == []
    assert rendered["results"][0]["key_output_fields"]["output_type"] == "list"
    assert rendered["results"][1]["key_output_fields"]["output_type"] == "dict"


def test_workflow_all_segments_exit_code_non_zero_when_any_failed(monkeypatch, capsys):
    def fake_run_all_segments(**kwargs):
        _ = kwargs
        return {
            "run_id": "run-1",
            "segments": ["seg-a"],
            "continue_on_error": True,
            "dry_run": True,
            "strict_missing_workflow": False,
            "totals": {"total_segments": 1, "succeeded": 0, "failed": 1},
            "summary": {"total_segments": 1, "succeeded": 0, "failed": 1, "failed_segments": ["seg-a"]},
            "results": [
                {
                    "segment": "seg-a",
                    "run_id": "run-1",
                    "status": "failed",
                    "error": "boom",
                    "duration_ms": 1,
                    "key_output_fields": {},
                }
            ],
        }

    monkeypatch.setattr(cli, "run_all_segments", fake_run_all_segments)
    exit_code = cli.main(["workflow", "all-segments", "--segments", "seg-a", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 1
    rendered = json.loads(captured.out)
    assert rendered["summary"]["failed_segments"] == ["seg-a"]


def test_workflow_all_segments_exit_code_two_on_config_error(monkeypatch, capsys):
    from november_whiskey.exceptions import ConfigError

    def fake_run_all_segments(**kwargs):
        _ = kwargs
        raise ConfigError("invalid segments")

    monkeypatch.setattr(cli, "run_all_segments", fake_run_all_segments)

    exit_code = cli.main(["workflow", "all-segments", "--segments", "bad"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: invalid segments" in captured.err


def test_cli_sanitizes_sensitive_values_from_error_output(monkeypatch, capsys):
    from november_whiskey.exceptions import ConfigError

    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "cli-secret")

    def fake_run_all_segments(**kwargs):
        _ = kwargs
        raise ConfigError("invalid cli-secret")

    monkeypatch.setattr(cli, "run_all_segments", fake_run_all_segments)
    exit_code = cli.main(["workflow", "all-segments", "--segments", "seg-a"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: invalid [REDACTED]" in captured.err


def test_private_lenders_streams_text_output_per_booking(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: type("Cfg", (), {"notifications": type("Notif", (), {"discord_webhook_url": None})()})(),
    )

    def fake_run_private_lenders_workflow(config, dry_run=False, on_booking_processed=None):
        _ = (config, dry_run)
        row = {
            "contact": {"fullName": "John Doe", "email": "john@example.com"},
            "best_start_time": {"start": "2026-04-13T15:30:00"},
            "event": {"id": "evt-1"},
            "form": {"submitted": True},
        }
        assert on_booking_processed is not None
        on_booking_processed(row)
        return [row]

    monkeypatch.setattr(cli, "run_private_lenders_workflow", fake_run_private_lenders_workflow)
    exit_code = cli.main(["--output-format", "text", "workflow", "private-lenders"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "John Doe" in captured.out
    assert captured.out.count("\n") == 1
