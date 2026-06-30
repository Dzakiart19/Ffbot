"""
Auto guest account generator — working flow (verified OB54).
Flow:
  1. /guest:register      → dapat uid + password (Garena OAuth)
  2. /guest/token:grant   → dapat access_token + open_id
  3. /MajorRegister       → buat profil FF game → dapat game_uid (field 3)
  4. MajorLogin           → dapat JWT (AES-decrypt response, proper proto parse)
  5. ChooseRegion         → selalu dipanggil agar lock_region di-set
  6. MajorLogin lagi      → dapat JWT final dengan lock_region
  7. GetLoginData         → AKTIVASI akun agar profil nyata di game ✅
  8. Simpan ke config (uid, password, game_uid)
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import string
import time
from datetime import datetime

import httpx
import urllib3
urllib3.disable_warnings()

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)

# ── Garena OAuth constants ─────────────────────────────────────────────────────
CLIENT_SECRET  = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
OAUTH_AGENT    = "GarenaMSDK/4.0.39(FRL-AN00a ;Android 10;nu;HK;)"
REGISTER_URL   = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
TOKEN_URL      = "https://100067.connect.garena.com/api/v2/oauth/guest/token:grant"

RELEASE_VERSION = "OB54"
LOGIN_AGENT     = "Dalvik/2.1.0 (Linux; U; Android 11; SM-S908E Build/TP1A.220624.014)"
OKHTTP_AGENT    = "okhttp/3.12.1"

# ── AES ───────────────────────────────────────────────────────────────────────
AES_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
AES_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

def _aes_enc(data: bytes) -> bytes:
    c = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return c.encrypt(pad(data, 16))

def _aes_dec(data: bytes) -> bytes:
    try:
        c = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        return unpad(c.decrypt(data), 16)
    except Exception:
        return data

# ── XOR keystream for open_id encoding in MajorRegister ─────────────────────
_KEYSTREAM = [
    0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,
    0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,
    0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,
]

# ── Region → language code ────────────────────────────────────────────────────
REGION_LANG = {
    "IND":"hi","ID":"id","SG":"ms","EUROPE":"fr","BR":"pt",
    "VN":"vi","TH":"th","BD":"bn","ME":"ar","RU":"ru",
    "NA":"na","SAC":"es","PK":"ur","TW":"zh","US":"us",
}

# ── Client server per region ──────────────────────────────────────────────────
REGION_CLIENT_URL = {
    "IND": "client.ind.freefiremobile.com",
    "BR":  "client.us.freefiremobile.com",
    "US":  "client.us.freefiremobile.com",
    "NA":  "client.us.freefiremobile.com",
    "SAC": "client.us.freefiremobile.com",
}
DEFAULT_CLIENT_URL = "clientbp.ggpolarbear.com"

# ── Config paths ──────────────────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
REGION_CONFIG = {
    "IND":    "ind_config.json",
    "ID":     "id_config.json",
    "SG":     "sg_config.json",
    "EUROPE": "europe_config.json",
    "RU":     "europe_config.json",
    "BR":     "br_config.json",
    "US":     "br_config.json",
}


# ─────────────────────────────────────────────────────────────────────────────
# Protobuf helpers (minimal, no external proto library needed)
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

def _read_varint(data: bytes, pos: int):
    result = 0; shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80): break
    return result, pos

def _parse_proto(data: bytes) -> dict:
    """Parse raw protobuf bytes into {field_num: value_str_or_int}."""
    fields: dict = {}; pos = 0
    while pos < len(data):
        if pos >= len(data): break
        tag, pos = _read_varint(data, pos)
        field = tag >> 3; wire = tag & 0x7
        if wire == 0:
            val, pos = _read_varint(data, pos)
            fields[field] = val
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            raw = data[pos:pos+length]; pos += length
            try: fields[field] = raw.decode('utf-8')
            except Exception: fields[field] = raw.hex()
        else:
            break
    return fields

def _xor_openid(open_id: str) -> bytes:
    return bytes([ord(open_id[i]) ^ _KEYSTREAM[i % len(_KEYSTREAM)]
                  for i in range(len(open_id))])

def _superscript(num: int) -> str:
    d = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    return ''.join(d[c] for c in f"{num:05d}")

def _gen_password(length: int = 12) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _config_path(region: str) -> str:
    fname = REGION_CONFIG.get(region.upper(), f"{region.lower()}_config.json")
    return os.path.join(CONFIG_DIR, fname)

def _load_config(region: str) -> list:
    path = _config_path(region)
    if not os.path.exists(path): return []
    try:
        with open(path) as f: return json.load(f)
    except Exception: return []

def _save_config(region: str, accounts: list):
    path = _config_path(region)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(accounts, f, indent=2)

def _append_account(region: str, uid: str, password: str, game_uid: str = "") -> bool:
    accounts = _load_config(region)
    if any(str(a.get("uid")) == str(uid) for a in accounts):
        return False
    entry = {"uid": str(uid), "password": password}
    if game_uid:
        entry["game_uid"] = str(game_uid)
    accounts.append(entry)
    _save_config(region, accounts)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Step: MajorLogin (extended fields, AES-decrypt response, try raw fallback)
# ─────────────────────────────────────────────────────────────────────────────

MAJOR_LOGIN_URL = "https://loginbp.ggpolarbear.com/MajorLogin"

_REGION_PROFILE = {
    "SG":     {"ip": "103.252.202.50",  "carrier": "Singtel",   "lang": "en", "city": "Singapore"},
    "ID":     {"ip": "103.85.24.10",    "carrier": "Telkomsel",  "lang": "id", "city": "Jakarta"},
    "IND":    {"ip": "103.47.144.1",    "carrier": "Jio",        "lang": "hi", "city": "Mumbai"},
    "EUROPE": {"ip": "91.108.56.100",   "carrier": "Orange",     "lang": "fr", "city": "Paris"},
    "RU":     {"ip": "77.88.8.8",       "carrier": "Beeline",    "lang": "ru", "city": "Moscow"},
    "BR":     {"ip": "177.75.8.10",     "carrier": "Claro",      "lang": "pt", "city": "Sao Paulo"},
    "US":     {"ip": "8.8.8.8",         "carrier": "AT&T",       "lang": "en", "city": "New York"},
    "ME":     {"ip": "5.1.41.10",       "carrier": "STC",        "lang": "ar", "city": "Riyadh"},
    "TH":     {"ip": "27.145.130.10",   "carrier": "AIS",        "lang": "th", "city": "Bangkok"},
    "VN":     {"ip": "14.177.16.10",    "carrier": "Viettel",    "lang": "vi", "city": "Hanoi"},
    "IND":    {"ip": "103.47.144.1",    "carrier": "Jio",        "lang": "hi", "city": "Mumbai"},
}
_DEFAULT_PROF = {"ip": "1.1.1.1", "carrier": "WIFI", "lang": "en", "city": "Singapore"}

async def _major_login(access_token: str, open_id: str,
                       region: str = "ID") -> tuple[str | None, str | None]:
    """
    MajorLogin with extended device fields (from Gen tool).
    Tries AES-decrypt then raw parse for response.
    Returns (jwt_token, lock_region).
    """
    prof = _REGION_PROFILE.get(region.upper(), _DEFAULT_PROF)

    def _pack() -> bytes:
        pkt = b''
        fields = {
            3:  str(datetime.now())[:-7],
            4:  "free fire",
            5:  1,
            7:  "1.126.5",
            8:  "Android OS 9 / API-28",
            9:  "Handheld",
            10: prof["carrier"],
            11: "WIFI",
            17: "Adreno (TM) 640",
            18: "OpenGL ES 3.0",
            19: "Google|4645e530-e790-4be2-ae7c-6f64d1259603",
            20: prof["ip"],
            21: prof["lang"],
            22: open_id,
            23: 4,
            24: "Handheld",
            25: "Samsung SM-G998B",
            26: region.upper(),
            29: access_token,
            33: prof["carrier"],
            34: "WIFI",
            37: "7428b253defc164018c604a1ebbfebdf",
            73: "/data/app/com.dts.freefireth-1/lib/arm",
            75: "H4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-1/base.apk",
            76: 2,
            78: 2,
            79: 2,
            83: "OpenGLES2",
            85: prof["city"],
            87: "android",
            88: "KqsHTywQqGHMgPbDY9P2mhkxXj/beObk/TFNpmgaucQwxyLu9hA478WEQCV0Mgaz9UivYUPpKNwPzgZhvDhSsUDMAFY=",
            90: '{"cur_rate":null,"support_etc2":false}',
            97: 1,
            98: 1,
            99: "4",
            100: "4",
        }
        for f, v in fields.items():
            if isinstance(v, int):   pkt += _pb_int(f, v)
            elif isinstance(v, str): pkt += _pb_str(f, v)
        return _aes_enc(pkt)

    headers = {
        "User-Agent":      LOGIN_AGENT,
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Content-Type":    "application/x-www-form-urlencoded",
        "Expect":          "100-continue",
        "ReleaseVersion":  RELEASE_VERSION,
        "X-GA":            "v1 1",
        "X-Unity-Version": "2018.4.11f1",
    }

    try:
        async with httpx.AsyncClient(timeout=20, verify=False) as client:
            r = await client.post(MAJOR_LOGIN_URL, content=_pack(), headers=headers)
            if r.status_code != 200:
                logger.warning(f"[MajorLogin] {r.status_code}")
                return None, None

            # Try AES-decrypt first, then raw (some responses are not encrypted)
            try:
                raw = _aes_dec(r.content)
            except Exception:
                raw = r.content

            parsed = _parse_proto(raw)
            jwt = parsed.get(8) or parsed.get(1)
            lock = parsed.get(2) or parsed.get(11)

            # If we got bytes instead of str, try decode
            if isinstance(jwt, str) and jwt.startswith("ey"):
                pass  # good
            elif isinstance(lock, str) and not jwt:
                # field assignment might be flipped
                jwt, lock = lock, jwt
            
            logger.debug(f"[MajorLogin] parsed fields: {list(parsed.keys())}")
            if not jwt or not str(jwt).startswith("ey"):
                # Try without AES decrypt (raw proto directly)
                parsed2 = _parse_proto(r.content)
                jwt = parsed2.get(8) or parsed2.get(1)
                lock = parsed2.get(2) or parsed2.get(11)

            if not jwt or not str(jwt).startswith("ey"):
                logger.warning(f"[MajorLogin] no JWT in response — fields: {list(parsed.keys())}")
                return None, None

            return str(jwt), str(lock) if lock else None
    except Exception as e:
        logger.warning(f"[MajorLogin] error: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Step: ChooseRegion
# ─────────────────────────────────────────────────────────────────────────────

async def _choose_region(jwt: str, region: str) -> bool:
    pkt = _aes_enc(_pb_str(1, region.upper()))
    headers = {
        "Accept-Encoding": "gzip",
        "Authorization":   f"Bearer {jwt}",
        "Connection":      "Keep-Alive",
        "Content-Type":    "application/x-www-form-urlencoded",
        "Expect":          "100-continue",
        "ReleaseVersion":  RELEASE_VERSION,
        "User-Agent":      OKHTTP_AGENT,
        "X-GA":            "v1 1",
        "X-Unity-Version": "2018.4.",
    }
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            r = await client.post(
                "https://loginbp.ggpolarbear.com/ChooseRegion",
                content=pkt, headers=headers)
            logger.info(f"[ChooseRegion] {region} → {r.status_code}")
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"[ChooseRegion] error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Step: GetLoginData — AKTIVASI akun agar profil nyata di game ✅
# ─────────────────────────────────────────────────────────────────────────────

async def _get_login_data(jwt: str, region: str) -> bool:
    """
    Calls GetLoginData on the game client server.
    This is the critical activation step that makes the FF profile visible in-game.
    Uses JWT (not OAuth token) at field 29.
    """
    client_url = REGION_CLIENT_URL.get(region.upper(), DEFAULT_CLIENT_URL)
    prof = _REGION_PROFILE.get(region.upper(), _DEFAULT_PROF)

    pkt = b''
    fields = {
        3:  str(datetime.now())[:-7],
        4:  "free fire",
        5:  1,
        7:  "1.126.5",
        8:  "Android OS 5.1.1 / API-22 (LMY48Z/rel.se.infra.20220128.171448)",
        9:  "Handheld",
        10: prof["carrier"],
        11: "WIFI",
        17: "Adreno (TM) 640",
        18: "OpenGL ES 3.0",
        19: "Google|4645e530-e790-4be2-ae7c-6f64d1259603",
        20: prof["ip"],
        21: prof["lang"],
        22: "24adf2d6806cf61bd95d4cd3b57a0bd9",
        23: 4,
        24: "Handheld",
        25: "Samsung SM-G998B",
        26: region.upper(),
        29: jwt,        # JWT token (field 29 = access_token in login proto)
        33: prof["carrier"],
        34: "WIFI",
        37: "7428b253defc164018c604a1ebbfebdf",
        73: "/data/app/com.dts.freefireth-1/lib/arm",
        75: "H4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-1/base.apk",
        83: "OpenGLES2",
        85: prof["city"],
        87: "android",
        88: "KqsHT8nWdkA7u/m7k8vg2H5FgrCGa4lfww3nHBGRHRPwDFV4LyCj8sT23O/P6K06qC3MOLZRThwWwul+g2goHwtQJy8=",
        90: '{"cur_rate":null,"support_etc2":false}',
    }
    for f, v in fields.items():
        if isinstance(v, int):   pkt += _pb_int(f, v)
        elif isinstance(v, str): pkt += _pb_str(f, v)

    headers = {
        "User-Agent":      "Dalvik/2.1.0 (Linux; U; Android 12)",
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Content-Type":    "application/x-www-form-urlencoded",
        "Authorization":   f"Bearer {jwt}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA":            "v1 1",
        "ReleaseVersion":  RELEASE_VERSION,
    }

    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            r = await client.post(
                f"https://{client_url}/GetLoginData",
                content=_aes_enc(pkt), headers=headers)
            ok = r.status_code == 200
            logger.info(f"[GetLoginData] {region} @ {client_url} → {r.status_code} ok={ok}")
            return ok
    except Exception as e:
        logger.warning(f"[GetLoginData] error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Core: create one guest account
# ─────────────────────────────────────────────────────────────────────────────

async def create_guest_account(region: str = "ID") -> dict | None:
    """
    Register one guest FF account for the given region.
    Returns {"uid", "password", "game_uid", "lock_region", "activated"} or None.
    """
    region   = region.upper()
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
                _pb_str(1,  nick)                     +
                _pb_str(2,  access_token)              +
                _pb_str(3,  open_id)                   +
                _pb_int(5,  102000007)                 +
                _pb_int(6,  4)                         +
                _pb_int(7,  1)                         +
                _pb_int(13, 1)                         +
                _pb_str(14, _xor_openid(open_id))      +
                _pb_str(15, REGION_LANG.get(region, "en")) +
                _pb_int(16, 2)
            )
            r3 = await client.post(
                "https://loginbp.ggpolarbear.com/MajorRegister",
                content=_aes_enc(pkt),
                headers={
                    "Accept-Encoding": "gzip", "Authorization": "Bearer",
                    "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded",
                    "Expect": "100-continue", "Host": "loginbp.ggpolarbear.com",
                    "ReleaseVersion": RELEASE_VERSION, "User-Agent": OKHTTP_AGENT,
                    "X-GA": "v1 1", "X-Unity-Version": "2018.4.",
                })
            if r3.status_code != 200:
                logger.warning(f"[gen] MajorRegister {r3.status_code}")
                return None

            reg_fields = _parse_proto(r3.content)
            game_uid = str(reg_fields.get(3, ""))
            logger.info(f"[gen] MajorRegister OK — oauth_uid={uid} game_uid={game_uid}")

        # ── Step 4: MajorLogin (first) ────────────────────────────────────────
        jwt, lock_region = await _major_login(access_token, open_id, region)
        if not jwt:
            # Fallback: try using get_jwt module (uses protobuf class + AES)
            try:
                from garena.get_jwt import create_jwt, get_oauth_token
                jwt, lock_region, _ = await create_jwt(uid, password, region=region)
            except Exception as e:
                logger.warning(f"[gen] fallback login also failed: {e}")
                return None

        if not jwt:
            logger.warning(f"[gen] Could not obtain JWT for uid={uid}")
            return None

        logger.info(f"[gen] MajorLogin OK — jwt={'✓' if jwt else '✗'} lock={lock_region!r}")

        # ── Step 5: ChooseRegion (ALWAYS — needed to lock account to region) ──
        # Per Gen tool: call ChooseRegion if lock_region is None/empty or wrong
        need_choose = not lock_region or lock_region in ("0", "None", "..", "")
        if not need_choose and str(lock_region).upper() != region.upper():
            need_choose = True

        if need_choose:
            logger.info(f"[gen] Calling ChooseRegion({region})...")
            await _choose_region(jwt, region)
            await asyncio.sleep(0.5)

            # Re-login to get JWT with lock_region properly set
            jwt2, lock_region2 = await _major_login(access_token, open_id, region)
            if jwt2:
                jwt = jwt2
                lock_region = lock_region2
                logger.info(f"[gen] Re-login after ChooseRegion — lock={lock_region!r}")

        # ── Step 6: GetLoginData — ACTIVATE account ───────────────────────────
        effective_region = lock_region if lock_region and lock_region not in ("0","None","..","") else region
        activated = await _get_login_data(jwt, effective_region)

        logger.info(f"[gen] ✅ uid={uid} game_uid={game_uid} lock={lock_region} activated={activated}")

        return {
            "uid":         uid,
            "password":    password,
            "game_uid":    game_uid,
            "lock_region": lock_region or region,
            "activated":   activated,
        }

    except Exception as e:
        logger.error(f"[gen] create_guest_account error: {e}", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Bulk creation helpers
# ─────────────────────────────────────────────────────────────────────────────

async def bulk_create_guests_async(region: str, count: int = 10,
                                    delay: float = 1.0,
                                    progress_cb=None) -> list:
    created = []; failed = 0

    for i in range(count):
        acc = await create_guest_account(region)
        if acc:
            save_region = acc.get("lock_region") or region
            saved = _append_account(save_region, acc["uid"], acc["password"],
                                    acc.get("game_uid", ""))
            acc["saved"] = saved
            created.append(acc)
            logger.info(f"[gen] {i+1}/{count} OK uid={acc['uid']} game_uid={acc.get('game_uid')} "
                        f"activated={acc.get('activated')} saved={saved}")
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
    """Sync wrapper (used by Flask routes)."""
    return asyncio.run(bulk_create_guests_async(region, count))
