from __future__ import annotations

from collections.abc import Callable
from typing import Any

import os

from november_whiskey.config import load_config, resolve_audience_segments
from november_whiskey.exceptions import ConfigError, WorkflowError
from november_whiskey.workflows.private_lenders import run_private_lenders_workflow

def resolve_segments(segments_override: str | None = None) -> list[str]:
    return resolve_audience_segments(segments_override)


def _extract_key_output_fields(output: Any) -> dict[str, Any]:
    if isinstance(output, list):
        return {
            "records_processed": len(output),
            "output_type": "list",
        }
    if isinstance(output, dict):
        return {
            "output_type": "dict",
            "keys": sorted(output.keys()),
        }
    return {
        "output_type": type(output).__name__,
    }


def run_all_segments(
    segments_override: str | None = None,
    continue_on_error: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    segments = resolve_segments(segments_override)
    if not segments:
        raise WorkflowError("No workflow segments selected")

    runners: dict[str, Callable[[Any, bool], Any]] = {
        "private-lenders": run_private_lenders_workflow,
    }

    previous_segment = os.environ.get("AUDIENCE_SEGMENT")
    segment_results: list[dict[str, Any]] = []

    for segment in segments:
        runner = runners.get(segment)
        if not runner:
            outcome = {
                "segment": segment,
                "status": "failed",
                "error": f"Unknown segment: {segment}",
                "key_output_fields": {},
            }
            segment_results.append(outcome)
            if not continue_on_error:
                break
            continue

        try:
            os.environ["AUDIENCE_SEGMENT"] = segment
            config = load_config()
            output = runner(config, dry_run=dry_run)
            outcome = {
                "segment": segment,
                "status": "success",
                "error": None,
                "key_output_fields": _extract_key_output_fields(output),
            }
            segment_results.append(outcome)
        except (ConfigError, WorkflowError) as exc:
            outcome = {
                "segment": segment,
                "status": "failed",
                "error": str(exc),
                "key_output_fields": {},
            }
            segment_results.append(outcome)
            if not continue_on_error:
                break

    if previous_segment is None:
        os.environ.pop("AUDIENCE_SEGMENT", None)
    else:
        os.environ["AUDIENCE_SEGMENT"] = previous_segment

    failed_count = sum(1 for result in segment_results if result["status"] == "failed")
    return {
        "segments": segments,
        "continue_on_error": continue_on_error,
        "dry_run": dry_run,
        "totals": {
            "total_segments": len(segment_results),
            "succeeded": len(segment_results) - failed_count,
            "failed": failed_count,
        },
        "results": segment_results,
    }
