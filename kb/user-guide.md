# November Whiskey User Guide (Non-Technical)

This guide is for team members who need to run the workflow without changing code.

## What this tool does

The workflow helps your team:
1. Find engaged contacts in HubSpot.
2. (Optional) Send those contacts to a HubSpot form.
3. Find a shared open meeting time.
4. Create Outlook meetings.

## Before you start

Ask your administrator for:
- A prepared `.env` file with all required account settings.
- Access to the company terminal/server where this project is installed.

> You should **not** edit credentials manually unless instructed.

## Common commands

Run these from the project root folder (the directory that contains `.env` and `app/`).

### 1) Check setup

```bash
november-whiskey config-check
```

If setup is correct, it prints:

```json
{"ok": true}
```

### 2) Preview engaged contacts (safe)

```bash
november-whiskey --output-format text signal find
```

### 3) Preview full workflow (safe dry-run)

```bash
november-whiskey --output-format text workflow private-lenders --dry-run
```

This does **not** create real calendar events.

### 4) Run full workflow live

```bash
november-whiskey --output-format text workflow private-lenders
```

Use this only when you are ready to create real meetings.

## Output formats (simple explanation)

- `text`: easiest to read as a person.
- `json`: best for saving structured results.
- `ndjson`: one JSON record per line (used in pipelines).

> Note: `--output-format` is a global option, so place it right after `november-whiskey` and before the subcommand.

## Safety tips

- Use `--dry-run` first whenever possible.
- Never share `.env` contents in chat or email.
- If credentials may be exposed, notify admin and rotate secrets immediately.

## Troubleshooting

### "ERROR: Missing required environment variable"

Your `.env` is missing values. Ask your administrator to re-provision it.

### "Missing audience config file for 'private-lenders': app/private-lenders/.env"

The segment-specific env file is missing at `app/private-lenders/.env`, or you ran the command from the wrong folder.
Run commands from the project root, or ask your administrator to set `AUDIENCE_ENV_PATH` correctly.

### "No mutual availability found"

No shared free time was found in the configured date window. Try again later or ask admin to adjust scheduling rules.

### "Invalid customer email"

The email was not valid. Correct it and rerun.

## Where to get help

- For day-to-day usage issues: contact the operations owner.
- For system/config changes: contact engineering.
