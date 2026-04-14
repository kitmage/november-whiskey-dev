# November Whiskey

Production-hardened workflow automation for:
1. finding engaged HubSpot contacts,
2. optionally submitting them to a HubSpot form,
3. computing mutual availability from Microsoft Graph `getSchedule`, and
4. creating Outlook events.

## Architecture Overview

- `src/november_whiskey/config.py`: centralized typed environment config.
- `src/november_whiskey/hubspot/`: HubSpot signal + form modules.
- `src/november_whiskey/graph/`: Graph auth, availability, and event modules.
- `src/november_whiskey/workflows/private_lenders.py`: orchestration workflow.
- `src/november_whiskey/cli.py`: single supported CLI entrypoint.
- `tests/`: availability, parsing, CLI, and config validation tests.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

## Environment Setup

Copy `.env.example` to `.env` (global/shared secrets), then copy the audience-specific
example into hidden files inside each segment directory:

```bash
cp .env.example .env
cp app/private-lenders/.env.example app/private-lenders/.env
cp app/insurers/.env.example app/insurers/.env
```

`load_config()` now loads `.env` first, then overlays `app/<AUDIENCE_SEGMENT>/.env`
(default segment: `private-lenders`). Put segment values (HubSpot list/campaign/form IDs,
and booking profile settings) only in that hidden segment file.

### Segment Resolution + Precedence (`.env` and CLI)

Use these variables in root `.env`:

```dotenv
AUDIENCE_SEGMENT=private-lenders
AUDIENCE_SEGMENTS=private-lenders,insurers
```

- `AUDIENCE_SEGMENT` is the single-segment fallback.
- `AUDIENCE_SEGMENTS` is a comma-separated multi-segment list used by `workflow all-segments`.
- `AUDIENCE_ENV_PATH` is an explicit per-run env file override and takes precedence over the resolved `app/<segment>/.env` path.

Audience selection precedence is:
1. CLI override `--segments ...`
2. `.env` value `AUDIENCE_SEGMENTS`
3. `.env` value `AUDIENCE_SEGMENT`

Resolution order:
1. Load root `.env` (global/shared values).
2. Resolve segment env path from `AUDIENCE_ENV_PATH` or `app/<AUDIENCE_SEGMENT>/.env`.
3. Load segment file and override matching keys from root `.env`.

Then validate configuration:

```bash
november-whiskey config-check
```

## CLI Usage

```bash
python -m november_whiskey signal find --output-format ndjson
python -m november_whiskey form submit --email person@example.com --dry-run
python -m november_whiskey availability best-start
python -m november_whiskey event create --customer-name "X" --customer-email "x@example.com" --dry-run
python -m november_whiskey workflow private-lenders --dry-run
python -m november_whiskey workflow all-segments --dry-run
```

Global options:
- `--debug`
- `--output-format json|ndjson|text|mini`

`mini` output format is intended for booking notifications and prints:
`🟢 Event booked with {full name} {email address} {pci_datetime}`.

If `DISCORD_WEBHOOK_URL` is set, `workflow private-lenders` also posts each successful booking to Discord using that same mini line format.

### Multi-Segment Workflow Examples

Run all configured segments from `.env` (`AUDIENCE_SEGMENTS`, falling back to `AUDIENCE_SEGMENT`):

```bash
python -m november_whiskey workflow all-segments --dry-run
```

Run only selected segments (CLI override takes precedence):

```bash
python -m november_whiskey workflow all-segments --segments private-lenders,insurers --dry-run
```

Expected summary output shape (includes success/failure per segment):

```json
{
  "segments": ["private-lenders", "insurers"],
  "continue_on_error": true,
  "dry_run": true,
  "totals": {
    "total_segments": 2,
    "succeeded": 1,
    "failed": 1
  },
  "results": [
    {
      "segment": "private-lenders",
      "status": "success",
      "error": null
    },
    {
      "segment": "unknown-segment",
      "status": "failed",
      "error": "No workflow registered for segment 'unknown-segment'"
    }
  ]
}
```

## Knowledge Base

- `kb/user-guide.md`: Non-technical operator guide.
- `kb/command-palette.md`: Full command and flag reference for the CLI.
- `kb/digitalocean-setup.md`: Deployment guide for DigitalOcean.

## Output Examples

Signal NDJSON:

```json
{"contactId":"123","email":"x@example.com","fullName":"X","openCount":4}
```

Availability JSON:

```json
{"best_start_time":{"start":"2026-04-08T10:00:00","score":3,"buffer_before_blocks":4,"buffer_after_blocks":3}}
```

Dry-run workflow output contains exact event payloads (no remote writes).

## Migration Notes (Old -> New)

- `app/private-lenders/signal_finder.py` -> `november-whiskey signal find` (preserved behavior)
- `app/private-lenders/form_submitter.py` -> `november-whiskey form submit --email ...` (slight change: explicit email input)
- `app/private-lenders/availability.py` -> `november-whiskey availability best-start` (preserved behavior)
- `app/private-lenders/create_mike_event.py` -> `november-whiskey workflow private-lenders` (preserved behavior, modularized)
- `app/conductor.py` -> `november-whiskey workflow private-lenders` (single workflow entry)
- `november-whiskey workflow private-lenders` remains supported during the transition to `workflow all-segments`.

Compatibility wrappers remain under `app/` and call the new CLI.

## Development

```bash
pytest
ruff check src tests
black --check src tests
```

## Security + Public Repo Safety

- Never commit `.env`.
- Never commit `.venv`.
- Rotate credentials immediately if exposure is suspected.
- Do not log bearer tokens/client secrets.
