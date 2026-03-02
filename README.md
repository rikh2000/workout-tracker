# Workout Tracker

Personal workout tracking app built with FastAPI. Tracks gym sessions and runs, with scheduling, templates, and stats.

## Run locally

```bash
source .venv/bin/activate      # or: .venv\Scripts\activate on Windows
uvicorn main:app --reload
```

Open http://localhost:8000. No credentials needed locally (auth only activates when AUTH_USERNAME and AUTH_PASSWORD env vars are set).

## Deploy changes to server

**1. On your laptop:**
```bash
git add -A
git commit -m "Your message here"
git push
```

**2. On the server (SSH in first):**
```bash
ssh root@YOUR_SERVER_IP
```

Then:
```bash
su - appuser
cd workout-tracker
git pull
exit
systemctl restart workout-tracker
```

## Server details

- Provider: Hetzner Cloud
- App runs as: `appuser`
- App location: `/home/appuser/workout-tracker/`
- Database: `/home/appuser/workout-tracker/workout_tracker.db`
- Service: `workout-tracker` (managed by systemd)

## Useful server commands

```bash
systemctl status workout-tracker    # check if app is running
systemctl restart workout-tracker   # restart app
journalctl -u workout-tracker -f    # live logs
```

## Auth

Copy `.env.example` to `.env` and fill in credentials. The `.env` file is gitignored and must be created manually on the server.

```bash
cp .env.example .env
nano .env
```
