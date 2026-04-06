from __future__ import annotations

from collections.abc import Callable
from typing import Any

from november_whiskey.exceptions import WorkflowError
from november_whiskey.workflows.private_lenders import run_private_lenders_workflow

WorkflowRunner = Callable[[Any, bool], Any]

WORKFLOW_REGISTRY: dict[str, WorkflowRunner] = {
    "private-lenders": run_private_lenders_workflow,
    # Temporary alias until a dedicated insurers workflow runner exists.
    "insurers": run_private_lenders_workflow,
}


def get_workflow_runner(segment: str, *, strict: bool = False) -> WorkflowRunner | None:
    runner = WORKFLOW_REGISTRY.get(segment)
    if runner is None and strict:
        raise WorkflowError(
            f"No workflow registered for segment '{segment}'. "
            "Register it in november_whiskey.workflows.registry.WORKFLOW_REGISTRY."
        )
    return runner
