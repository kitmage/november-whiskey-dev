from __future__ import annotations

from typing import Any

import logging
import os
import time
import uuid

from november_whiskey.config import load_config, resolve_audience_segments
from november_whiskey.exceptions import ConfigError, WorkflowError
from november_whiskey.utils.redaction import sanitize_error_text
from november_whiskey.workflows.registry import get_workflow_runner

logger = logging.getLogger(__name__)


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
    strict_missing_workflow: bool = False,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    segments = resolve_segments(segments_override)
    if not segments:
        raise WorkflowError("No workflow segments selected")

    previous_segment = os.environ.get("AUDIENCE_SEGMENT")
    segment_results: list[dict[str, Any]] = []

    for segment in segments:
        start_monotonic = time.monotonic()
        logger.info("segment_start segment=%s run_id=%s", segment, run_id)
        try:
            runner = get_workflow_runner(segment, strict=strict_missing_workflow)
            if runner is None:
                duration_ms = int((time.monotonic() - start_monotonic) * 1000)
                outcome = {
                    "segment": segment,
                    "run_id": run_id,
                    "status": "failed",
                    "error": sanitize_error_text(f"No workflow registered for segment '{segment}'"),
                    "key_output_fields": {},
                    "duration_ms": duration_ms,
                }
                segment_results.append(outcome)
                logger.info(
                    "segment_end segment=%s run_id=%s status=failed duration_ms=%d",
                    segment,
                    run_id,
                    duration_ms,
                )
                if not continue_on_error:
                    break
                continue

            os.environ["AUDIENCE_SEGMENT"] = segment
            config = load_config()
            output = runner(config, dry_run=dry_run)
            duration_ms = int((time.monotonic() - start_monotonic) * 1000)
            outcome = {
                "segment": segment,
                "run_id": run_id,
                "status": "success",
                "error": None,
                "key_output_fields": _extract_key_output_fields(output),
                "duration_ms": duration_ms,
            }
            segment_results.append(outcome)
            logger.info(
                "segment_end segment=%s run_id=%s status=success duration_ms=%d",
                segment,
                run_id,
                duration_ms,
            )
        except (ConfigError, WorkflowError) as exc:
            if strict_missing_workflow and isinstance(exc, WorkflowError):
                raise

            duration_ms = int((time.monotonic() - start_monotonic) * 1000)
            outcome = {
                "segment": segment,
                "run_id": run_id,
                "status": "failed",
                "error": sanitize_error_text(str(exc)),
                "key_output_fields": {},
                "duration_ms": duration_ms,
            }
            segment_results.append(outcome)
            logger.info(
                "segment_end segment=%s run_id=%s status=failed duration_ms=%d",
                segment,
                run_id,
                duration_ms,
            )
            if not continue_on_error:
                break

    if previous_segment is None:
        os.environ.pop("AUDIENCE_SEGMENT", None)
    else:
        os.environ["AUDIENCE_SEGMENT"] = previous_segment

    failed_count = sum(1 for result in segment_results if result["status"] == "failed")
    failed_segments = [result["segment"] for result in segment_results if result["status"] == "failed"]
    return {
        "run_id": run_id,
        "segments": segments,
        "continue_on_error": continue_on_error,
        "dry_run": dry_run,
        "strict_missing_workflow": strict_missing_workflow,
        "totals": {
            "total_segments": len(segment_results),
            "succeeded": len(segment_results) - failed_count,
            "failed": failed_count,
        },
        "summary": {
            "total_segments": len(segment_results),
            "succeeded": len(segment_results) - failed_count,
            "failed": failed_count,
            "failed_segments": failed_segments,
        },
        "results": segment_results,
    }
