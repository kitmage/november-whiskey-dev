# Command Palette

This article documents every supported `november-whiskey` CLI command and flag combination used by this application.

## CLI shape and ordering rules

Use the CLI in this order:

```bash
november-whiskey [GLOBAL_FLAGS] <COMMAND> <SUBCOMMAND> [COMMAND_FLAGS]
```

Global flags must be placed before the command/subcommand.

## Global flags

- `--debug`
  - Enables debug logging.
- `--output-format json|ndjson|text|mini`
  - Controls output rendering.
  - Default: `json`

Examples:

```bash
november-whiskey --debug config-check
november-whiskey --output-format text workflow private-lenders --dry-run
```

---

## Command: `config-check`

Valid invocations:

```bash
november-whiskey config-check
november-whiskey --debug config-check
november-whiskey --output-format json config-check
november-whiskey --debug --output-format json config-check
```

Purpose:
- Validates required environment/config values.
- Returns `{"ok": true}` on success.

---

## Command group: `signal`

### Subcommand: `signal find`

Flags:
- `--campaign-id <id>`
- `--list-id <id>`
- `--lookback-hours <int>`
- `--signal-threshold <int>`

Valid usage pattern:

```bash
november-whiskey [GLOBAL_FLAGS] signal find \
  [--campaign-id <id>] \
  [--list-id <id>] \
  [--lookback-hours <int>] \
  [--signal-threshold <int>]
```

All four flags are optional and may be combined in any order.

Common combinations:

```bash
november-whiskey signal find
november-whiskey signal find --campaign-id 123
november-whiskey signal find --list-id 456
november-whiskey signal find --lookback-hours 24 --signal-threshold 3
november-whiskey --output-format ndjson signal find --campaign-id 123 --list-id 456
```

---

## Command group: `form`

### Subcommand: `form submit`

Required flag:
- `--email <email>`

Optional flag:
- `--dry-run`

Valid usage pattern:

```bash
november-whiskey [GLOBAL_FLAGS] form submit --email <email> [--dry-run]
```

Combinations:

```bash
november-whiskey form submit --email person@example.com
november-whiskey form submit --email person@example.com --dry-run
november-whiskey --output-format text form submit --email person@example.com --dry-run
```

---

## Command group: `availability`

### Subcommand: `availability best-start`

No command-specific flags.

Valid invocations:

```bash
november-whiskey availability best-start
november-whiskey --debug availability best-start
november-whiskey --output-format text availability best-start
november-whiskey --debug --output-format mini availability best-start
```

---

## Command group: `event`

### Subcommand: `event create`

Required flags:
- `--customer-name <name>`
- `--customer-email <email>`

Optional flags:
- `--start <timestamp>`
- `--subject <text>`
- `--location <text>`
- `--dry-run`

Valid usage pattern:

```bash
november-whiskey [GLOBAL_FLAGS] event create \
  --customer-name <name> \
  --customer-email <email> \
  [--start <timestamp>] \
  [--subject <text>] \
  [--location <text>] \
  [--dry-run]
```

Combination examples:

```bash
november-whiskey event create --customer-name "Jane Doe" --customer-email "jane@example.com"
november-whiskey event create --customer-name "Jane Doe" --customer-email "jane@example.com" --start "2026-04-20T14:00:00"
november-whiskey event create --customer-name "Jane Doe" --customer-email "jane@example.com" --subject "Intro Call" --location "Teams"
november-whiskey event create --customer-name "Jane Doe" --customer-email "jane@example.com" --dry-run
november-whiskey --output-format text event create --customer-name "Jane Doe" --customer-email "jane@example.com" --dry-run
```

Notes:
- If `--start` is omitted, the app computes a best start time automatically.
- Invalid email values fail validation.

---

## Command group: `workflow`

### Subcommand: `workflow private-lenders`

Optional flags:
- `--dry-run`

Valid usage pattern:

```bash
november-whiskey [GLOBAL_FLAGS] workflow private-lenders [--dry-run]
```

Combinations:

```bash
november-whiskey workflow private-lenders
november-whiskey workflow private-lenders --dry-run
november-whiskey --output-format text workflow private-lenders
november-whiskey --output-format mini workflow private-lenders --dry-run
```

Output behavior notes:
- `text`, `ndjson`, and `mini` stream records as bookings are processed.
- `mini` prints compact notification lines.
- If configured, Discord notifications are sent per booking and for certain workflow outcomes.

### Subcommand: `workflow all-segments`

Optional flags:
- `--segments <csv>`
- `--continue-on-error`
- `--no-continue-on-error`
- `--dry-run`

Default behavior:
- `continue_on_error` defaults to `true`.

Valid usage pattern:

```bash
november-whiskey [GLOBAL_FLAGS] workflow all-segments \
  [--segments <csv>] \
  [--continue-on-error | --no-continue-on-error] \
  [--dry-run]
```

Combinations:

```bash
november-whiskey workflow all-segments
november-whiskey workflow all-segments --dry-run
november-whiskey workflow all-segments --segments private-lenders,insurers
november-whiskey workflow all-segments --segments private-lenders,insurers --no-continue-on-error
november-whiskey --output-format text workflow all-segments --segments private-lenders,insurers --dry-run
```

Exit code behavior:
- Returns `0` when all targeted segments succeed.
- Returns `1` when one or more targeted segments fail.

---

## Command matrix (quick reference)

| Command | Required flags | Optional flags |
|---|---|---|
| `config-check` | none | global flags only |
| `signal find` | none | `--campaign-id`, `--list-id`, `--lookback-hours`, `--signal-threshold` |
| `form submit` | `--email` | `--dry-run` |
| `availability best-start` | none | none |
| `event create` | `--customer-name`, `--customer-email` | `--start`, `--subject`, `--location`, `--dry-run` |
| `workflow private-lenders` | none | `--dry-run` |
| `workflow all-segments` | none | `--segments`, `--continue-on-error`, `--no-continue-on-error`, `--dry-run` |

---

## Common mistakes

- Putting global flags after the command (for example, `november-whiskey signal find --output-format text`).
  - Preferred: `november-whiskey --output-format text signal find`
- Omitting required flags:
  - `form submit` requires `--email`
  - `event create` requires `--customer-name` and `--customer-email`
- Using both `--continue-on-error` and `--no-continue-on-error` in the same command.

## See also

- `README.md` (CLI usage and architecture overview)
- `kb/user-guide.md` (non-technical runbook)
