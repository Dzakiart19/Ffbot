"""
Auto guest account generator — working flow (verified OB54).
Flow:
  1. /guest:register      → dapat uid + password (Garena OAuth)
  2. /guest/token:grant   → dapat access_token + open_id
  3. /MajorRegister       → buat profil FF game
  4. create_jwt()         → verifikasi JWT dapat diambil, catat lock_region
  5. Simpan ke config

Tidak butuh TOR — IP Replit tidak diblok Garena per 2025.
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import string
import time

import httpx
import urllib3
urllib3.disable_warnings()

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from garena.get_jwt import create_jwt

logger = logging.getLogger(__name__)

# ── Garena OAuth constants ─────────────────────────────────────────────────────
CLIENT_SECRET  = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
OAUTH_AGENT    = "GarenaMSDK/4.0.39(FRL-AN00a ;Android 10;nu;HK;)"
REGISTER_URL   = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
TOKEN_URL      = "https://100067.connect.garena.com/api/v2/oauth/guest/token:grant"

# ── AES (same key as like_api / get_jwt) ──────────────────────────────────────
AES_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
AES_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

# ── XOR keystream used by generator for open_id encoding ─────────────────────
_KEYSTREAM = [
    0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,
    0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,
    0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,
]

# ── Region → language code mapping ───────────────────────────────────────────
REGION_LANG = {
    "IND":"hi","ID":"id","SG":"ms","EUROPE":"fr","BR":"pt",
    "VN":"vi","TH":"th","BD":"bn","ME":"ar","RU":"ru",
    "NA":"na","SAC":"es","PK":"ur","TW":"zh","US":"us",
}

# ── Config paths ──────────────────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
# Must match the file names used by like_api.py / token_manager.py
REGION_CONFIG = {
    "IND":    "ind_config.json",
    "ID":     "sg_config.json",   # ID accounts live in sg_config (shared pool)
    "SG":     "sg_config.json",
    "EUROPE": "europe_config.json",
    "RU":     "europe_config.json",
    "BR":     "br_config.json",
    "US":     "br_config.json",
}


# ─────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _varint(n: int) -> bytes:
    out = []
    while True:
        b = n & 0x7F; n >>= 7
        if n: out.append(b | 0x80)
        else: out.append(b); break
    return bytes(out)

def _pb_int(field: int, val: int) -> bytes:
    return _varint((field << 3) | 0) + _varint(val)

def _pb_str(field: int, val) -> bytes:
    data = val.encode() if isinstance(val, str) else val
    return _varint((field << 3) | 2) + _varint(len(data)) + data

def _aes_encrypt(raw: bytes) -> bytes:
    c = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return c.encrypt(pad(raw, 16))

def _xor_openid(open_id: str) -> bytes:
    """XOR encode open_id as used in MajorRegister field 14."""
    return bytes([ord(open_id[i]) ^ _KEYSTREAM[i % len(_KEYSTREAM)]
                  for i in range(len(open_id))])

async def _choose_region(jwt: str, region: str) -> bool:
    """Call ChooseRegion to lock a new account to the desired region."""
    pkt = _pb_str(1, region.upper())
    headers = {
        "Accept-Encoding": "gzip",
        "Authorization":   f"Bearer {jwt}",
        "Connection":      "Keep-Alive",
        "Content-Type":    "application/x-www-form-urlencoded",
        "Expect":          "100-continue",
        "ReleaseVersion":  "OB54",
        "User-Agent":      "okhttp/3.12.1",
        "X-GA":            "v1 1",
        "X-Unity-Version": "2018.4.",
    }
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            r = await client.post(
                "https://loginbp.ggpolarbear.com/ChooseRegion",
                content=_aes_encrypt(pkt),
                headers=headers,
            )
            logger.debug(f"[ChooseRegion] {region} -> {r.status_code}")
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"[ChooseRegion] error: {e}")
        return False


def _gen_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def _superscript(num: int) -> str:
    exp_digits = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴',
                  '5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    return ''.join(exp_digits[d] for d in f"{num:05d}")


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _config_path(region: str) -> str:
    fname = REGION_CONFIG.get(region.upper(), f"{region.lower()}_config.json")
    return os.path.join(CONFIG_DIR, fname)

def _load_config(region: str) -> list:
    path = _config_path(region)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []

def _save_config(region: str, accounts: list):
    path = _config_path(region)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(accounts, f, indent=2)

def _append_account(region: str, uid: str, password: str) -> bool:
    """Add a new account to config file (if uid not already present)."""
    accounts = _load_config(region)
    if any(str(a.get("uid")) == str(uid) for a in accounts):
        return False
    accounts.append({"uid": str(uid), "password": password})
    _save_config(region, accounts)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Core generation flow
# ─────────────────────────────────────────────────────────────────────────────

async def create_guest_account(region: str = "IND") -> dict | None:
    """
    Register one guest FF account for the given region.
    Returns {"uid", "password", "lock_region", "server_url"} or None on failure.
    """
    region = region.upper()
    lang   = REGION_LANG.get(region, "en")
    password = _gen_password()

    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:

            # ── Step 1: Register Garena OAuth guest ──────────────────────────
            body = json.dumps(
                {"app_id": 100067, "client_type": 2, "password": password, "source": 2},
                separators=(',', ':')
            )
            sig = hashlib.sha256((CLIENT_SECRET + body).encode()).hexdigest()
            r1 = await client.post(REGISTER_URL, content=body.encode(),
                headers={"User-Agent": OAUTH_AGENT,
                         "Authorization": f"Signature {sig}",
                         "Content-Type": "application/json; charset=utf-8"})
            d1 = r1.json()
            if d1.get("code") != 0:
                logger.warning(f"[gen] Register failed: {d1}")
                return None
            uid = str(d1["data"]["uid"])

            # ── Step 2: Get OAuth token ───────────────────────────────────────
            r2 = await client.post(TOKEN_URL,
                json={"client_id": 100067, "client_secret": CLIENT_SECRET,
                      "client_type": 2, "password": password,
                      "response_type": "token", "uid": int(uid)},
                headers={"User-Agent": OAUTH_AGENT, "Content-Type": "application/json"})
            d2 = r2.json().get("data", {})
            access_token = d2.get("access_token")
            open_id      = d2.get("open_id")
            if not access_token or not open_id:
                logger.warning(f"[gen] Token grant failed: {r2.text[:200]}")
                return None

            # ── Step 3: MajorRegister (create FF game profile) ───────────────
            nick = "KiosGmr" + _superscript(random.randint(1, 99999))
            pkt = (
                _pb_str(1,  nick)         +
                _pb_str(2,  access_token) +
                _pb_str(3,  open_id)      +
                _pb_int(5,  102000007)    +
                _pb_int(6,  4)            +
                _pb_int(7,  1)            +
                _pb_int(13, 1)            +
                _pb_str(14, _xor_openid(open_id)) +
                _pb_str(15, lang)         +
                _pb_int(16, 2)
            )
            r3 = await client.post(
                "https://loginbp.ggpolarbear.com/MajorRegister",
                content=_aes_encrypt(pkt),
                headers={
                    "Accept-Encoding": "gzip",
                    "Authorization":   "Bearer",
                    "Connection":      "Keep-Alive",
                    "Content-Type":    "application/x-www-form-urlencoded",
                    "Expect":          "100-continue",
                    "Host":            "loginbp.ggpolarbear.com",
                    "ReleaseVersion":  "OB54",
                    "User-Agent":      "okhttp/3.12.1",
                    "X-GA":            "v1 1",
                    "X-Unity-Version": "2018.4.",
                })
            if r3.status_code != 200:
                logger.warning(f"[gen] MajorRegister {r3.status_code}: {r3.text[:200]}")
                return None

        # ── Step 4: MajorLogin with region hint ──────────────────────────────
        jwt, lock_region, server_url = await create_jwt(uid, password, region=region)
        if not jwt:
            logger.warning(f"[gen] JWT verification failed for uid={uid}")
            return None

        # ── Step 5: ChooseRegion if lock doesn't match desired ────────────
        if lock_region and lock_region.upper() != region.upper():
            logger.info(f"[gen] lock={lock_region} != {region}, calling ChooseRegion...")
            chose_ok = await _choose_region(jwt, region)
            if chose_ok:
                # Re-login to get updated JWT with correct lock
                try:
                    jwt, lock_region, server_url = await create_jwt(uid, password, region=region)
                except Exception:
                    pass
            logger.info(f"[gen] After ChooseRegion: lock={lock_region}")

        logger.info(f"[gen] ✅ uid={uid} lock={lock_region} srv={server_url}")
        return {
            "uid":        uid,
            "password":   password,
            "lock_region": lock_region,
            "server_url":  server_url,
        }

    except Exception as e:
        logger.error(f"[gen] create_guest_account error: {e}")
        return None


async def bulk_create_guests_async(region: str, count: int = 10,
                                    delay: float = 0.8,
                                    progress_cb=None) -> list:
    """
    Generate `count` guest accounts for `region`, save to config.
    progress_cb(created, failed, total) called after each attempt if provided.
    """
    created = []
    failed  = 0

    for i in range(count):
        acc = await create_guest_account(region)
        if acc:
            saved = _append_account(
                acc.get("lock_region") or region,
                acc["uid"],
                acc["password"],
            )
            acc["saved"] = saved
            created.append(acc)
            logger.info(f"[gen] {i+1}/{count} OK uid={acc['uid']} saved={saved}")
        else:
            failed += 1
            logger.warning(f"[gen] {i+1}/{count} FAILED (total failed={failed})")

        if progress_cb:
            progress_cb(len(created), failed, count)

        if i < count - 1:
            await asyncio.sleep(delay)

    logger.info(f"[gen] Done — created={len(created)} failed={failed}")
    return created


def bulk_create_guests(region: str, count: int = 10) -> list:
    """Sync wrapper for bulk_create_guests_async (used by Flask routes)."""
    return asyncio.run(bulk_create_guests_async(region, count))
