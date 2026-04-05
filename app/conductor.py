"""Run create_mike_event.py across configured app subdirectories."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Directories under ./app to run create_mike_event.py from.
TARGET_DIRECTORIES = [
    "private-lenders",
    #"insurers",
]

SCRIPT_NAME = "create_mike_event.py"
DISCORD_WEBHOOK_ENV_VAR = "DISCORD_WEBHOOK"


def send_discord_message(message: str) -> None:
    """Send a message to Discord via webhook if configured."""
    webhook = os.getenv(DISCORD_WEBHOOK_ENV_VAR)
    if not webhook:
        return

    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except urllib.error.URLError as error:
        print(f"[WARN] Failed to send Discord message: {error}", file=sys.stderr)


def run_script(script_path: Path) -> tuple[int, str, str]:
    """Execute a python script and return exit code/stdout/stderr."""
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    app_dir = Path(__file__).resolve().parent
    overall_exit_code = 0

    for directory in TARGET_DIRECTORIES:
        script_path = app_dir / directory / SCRIPT_NAME
        header = f"\n# Running {script_path.relative_to(app_dir)}"
        print(header)

        if not script_path.exists():
            warning = f"[WARN] Script not found: {script_path}"
            print(warning, file=sys.stderr)
            send_discord_message(f"{header}\n{warning}")
            overall_exit_code = 1
            continue

        exit_code, stdout, stderr = run_script(script_path)
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        exit_line = f"=== Exit code: {exit_code} ==="
        print(exit_line)
        send_discord_message(f"{header}\n{stdout}{stderr}{exit_line}\n")

        if exit_code != 0:
            overall_exit_code = exit_code

    return overall_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
