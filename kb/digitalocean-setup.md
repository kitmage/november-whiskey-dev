# DigitalOcean Setup Guide

This guide explains how to run November Whiskey on DigitalOcean.

---

## Deploy on a DigitalOcean Droplet

## 1) Create the Droplet

- Ubuntu 22.04 LTS (or newer)
- Basic plan is fine to start (1 vCPU / 1 GB RAM)
- Add your SSH key during creation

## 2) SSH into the server

```bash
ssh root@YOUR_DROPLET_IP
```

(Optional but recommended): create a non-root user and use that user for deployments.

## 3) Install system dependencies

```bash
apt update
apt install -y git python3 python3-venv python3-pip
```

## 4) Clone project and install Python dependencies

```bash
git clone <your-repo-url> november-whiskey-dev
cd november-whiskey-dev

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## 5) Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill all `replace-me` values with real credentials.

Security notes:
- Never commit `.env`
- Restrict file permissions:

```bash
chmod 600 .env
```

## 6) Validate setup

```bash
source .venv/bin/activate
november-whiskey config-check
```

Expected output:

```json
{"ok": true}
```

## 7) Run a safe dry-run

```bash
november-whiskey workflow private-lenders --dry-run --output-format text
```

## 8) Run live workflow

```bash
november-whiskey workflow private-lenders --output-format text
```

---

## 9) Schedule recurring runs with cron

Edit crontab:

```bash
crontab -e
```

Example (run every day at 9:00 AM UTC):

```cron
0 9 * * * cd /root/november-whiskey-dev && /root/november-whiskey-dev/.venv/bin/november-whiskey workflow private-lenders --output-format text >> /root/november-whiskey-dev/workflow.log 2>&1
```

Adjust paths/usernames to your setup.

---

## Operational checklist

Before enabling live runs:
- [ ] `config-check` passes
- [ ] dry-run output looks correct
- [ ] `.env` is present and protected (`chmod 600`)
- [ ] cron schedule verified
- [ ] log file path exists and is writable

## Troubleshooting

### `ERROR: Missing required environment variable`
Your `.env` file is missing required values.

### `No mutual availability found`
No shared free time exists in current configured search window.

### HubSpot or Graph API failures
Confirm credentials are valid and network egress is allowed from the Droplet.
