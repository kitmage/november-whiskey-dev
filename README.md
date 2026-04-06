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

Copy `.env.example` to `.env` and replace placeholders:

```bash
cp .env.example .env
```

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
```

Global options:
- `--debug`
- `--output-format json|ndjson|text`

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

