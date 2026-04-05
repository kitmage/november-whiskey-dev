"""Run create_mike_event.py across configured app subdirectories."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Directories under ./app to run create_mike_event.py from.
TARGET_DIRECTORIES = [
    "private-lenders",
    #"insurers",
]

SCRIPT_NAME = "create_mike_event.py"


def run_script(script_path: Path) -> int:
    """Execute a python script and stream output to the terminal."""
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    return result.returncode


def main() -> int:
    app_dir = Path(__file__).resolve().parent
    overall_exit_code = 0

    for directory in TARGET_DIRECTORIES:
        script_path = app_dir / directory / SCRIPT_NAME
        print(f"\n# Running {script_path.relative_to(app_dir)}")

        if not script_path.exists():
            print(f"[WARN] Script not found: {script_path}", file=sys.stderr)
            overall_exit_code = 1
            continue

        exit_code = run_script(script_path)
        #print(f"=== Exit code: {exit_code} ===")

        if exit_code != 0:
            overall_exit_code = exit_code

    return overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
