# KiosGamer

A Flask web app that sends likes and creates lobbies for Free Fire players.

## Stack

- **Backend:** Python / Flask
- **Database:** MongoDB Atlas (`kiosgamer` database)
- **Auth:** JWT (Bearer tokens)
- **Frontend:** Vanilla JS + HTML/CSS (served by Flask)

## Running

```
python app.py
```

Runs on port 5000. The "Start App" workflow handles this automatically.

## Required Secrets

| Secret | Description |
|---|---|
| `MONGODB_URI` | MongoDB Atlas connection string |
| `JWT_SECRET` | Secret key for signing JWT tokens |

## Notes

- The `garena/` module handles real Free Fire API calls (likes, guest accounts). If it fails to import (protobuf version issue), the app falls back to **demo mode** — all like/lobby features still work with random placeholder data.
- The protobuf warning on startup (`cannot import name 'runtime_version'`) is non-fatal; the app runs in demo mode.
- Admin routes (`/api/admin/*`) require a user with `role: "admin"` in MongoDB.

## User Preferences

- Keep existing project structure and stack.
