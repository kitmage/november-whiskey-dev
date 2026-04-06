from __future__ import annotations

from typing import Any

from november_whiskey.config import AppConfig
from november_whiskey.workflows.multi_segment import run_all_segments


def run_all_segments_workflow(
    config: AppConfig,
    segments_override: str | None = None,
    continue_on_error: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    _ = config
    return run_all_segments(
        segments_override=segments_override,
        continue_on_error=continue_on_error,
        dry_run=dry_run,
    )
