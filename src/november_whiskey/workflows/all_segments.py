from __future__ import annotations

from november_whiskey.config import AppConfig
from november_whiskey.exceptions import WorkflowError
from november_whiskey.workflows.private_lenders import run_private_lenders_workflow

DEFAULT_SEGMENTS: tuple[str, ...] = ("private-lenders",)


def _resolve_segments(segments_override: str | None) -> list[str]:
    if not segments_override:
        return list(DEFAULT_SEGMENTS)
    return [segment.strip() for segment in segments_override.split(",") if segment.strip()]


def run_all_segments_workflow(
    config: AppConfig,
    segments_override: str | None = None,
    continue_on_error: bool = True,
    dry_run: bool = False,
) -> dict:
    segments = _resolve_segments(segments_override)
    if not segments:
        raise WorkflowError("No workflow segments selected")

    results: list[dict] = []
    errors: list[dict] = []

    for segment in segments:
        try:
            if segment == "private-lenders":
                segment_result = run_private_lenders_workflow(config, dry_run=dry_run)
            else:
                raise WorkflowError(f"Unknown segment: {segment}")
            results.append({"segment": segment, "ok": True, "result": segment_result})
        except WorkflowError as exc:
            errors.append({"segment": segment, "ok": False, "error": str(exc)})
            if not continue_on_error:
                raise

    return {
        "segments": segments,
        "continue_on_error": continue_on_error,
        "dry_run": dry_run,
        "results": results,
        "errors": errors,
    }
