---
name: Guest bot like limitation
description: Why API-generated Level 0 bot accounts cannot send likes that count in Garena FF
---

## Rule
API-generated guest accounts start at Level 0 (no game history) and Garena silently rejects their likes — LikeProfile returns HTTP 200 with **empty body** but likes_added=0.

**Why:** Garena server-side validates sender game activity. Level 0 = no real gameplay = likes ignored silently.

**How to apply:** Only accounts that have actually played the game (Level 2+, accessed via real APK) can send countable likes. Bot accounts from the `/guest:register` API cannot.

## What DOES work
- Account generation flow (guest:register → token:grant → MajorRegister → MajorLogin → ChooseRegion → GetLoginData) → activated=True
- game_uid (field 3 of MajorRegister response) ≠ OAuth uid (field uid). Both must be tracked.
- GetLoginData activation step is required to make the profile visible in game — without it HTTP 500 from GetLoginData; with it HTTP 200.
- GetPlayerPersonalShow response is AES-encrypted — must decrypt before ParseFromString.

## Working flow (verified OB54)
1. POST `/guest:register` (100067.connect.garena.com) → OAuth uid + password
2. POST `/guest/token:grant` → access_token + open_id
3. POST `loginbp.ggpolarbear.com/MajorRegister` (AES-enc pkt, fields 1–16) → **game_uid (field 3)**
4. POST `loginbp.ggpolarbear.com/MajorLogin` (ext fields 73,75,83,85,87,88,90,97-100) → JWT
5. POST `loginbp.ggpolarbear.com/ChooseRegion` (AES-enc, Bearer JWT) → lock region
6. POST `loginbp.ggpolarbear.com/MajorLogin` again → final JWT with lock_region set
7. POST `{client_url}/GetLoginData` (AES-enc pkt, field 29=JWT) → **activated=True**
