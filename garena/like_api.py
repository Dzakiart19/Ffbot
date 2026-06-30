"""
Send likes to Free Fire profiles.
Based on: github.com/kaifcodec/freefire-like-and-guest-api
"""
import asyncio
import logging
import json
import base64
import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from garena.ff_proto.send_like_pb2  import like   as LikeProfileReq
from garena.ff_proto.account_show_pb2 import AccountPersonalShowInfo
from garena.ff_proto.core_pb2       import GetPlayerPersonalShow
from garena.get_jwt                 import create_jwt, MAIN_KEY, MAIN_IV, RELEASE_VERSION, USER_AGENT

logger = logging.getLogger(__name__)

SERVER_MAP = {
    "IND": "https://client.ind.freefiremobile.com",
    "BR":  "https://client.us.freefiremobile.com",
    "US":  "https://client.us.freefiremobile.com",
    "SAC": "https://client.us.freefiremobile.com",
    "NA":  "https://client.us.freefiremobile.com",
}
DEFAULT_SERVER = "https://clientbp.ggblueshark.com"

# AES for like payload (same key but bytes literal)
LIKE_KEY = b'Yg&tc%DEuh6%Zc^8'
LIKE_IV  = b'6oyZDr22E3ychjM%'


def _build_like_payload(uid: str, region: str) -> bytes:
    msg = LikeProfileReq()
    msg.uid    = int(uid)
    msg.region = region
    proto_bytes = msg.SerializeToString()
    cipher = AES.new(LIKE_KEY, AES.MODE_CBC, LIKE_IV)
    return cipher.encrypt(pad(proto_bytes, AES.block_size))


def _build_info_payload(uid: str) -> bytes:
    msg = GetPlayerPersonalShow()
    msg.a = int(uid)
    msg.b = 0
    proto_bytes = msg.SerializeToString()
    key = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')
    iv  = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(proto_bytes, AES.block_size))


def _make_headers(token: str) -> dict:
    return {
        "User-Agent":      USER_AGENT,
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Content-Type":    "application/octet-stream",
        "Expect":          "100-continue",
        "Authorization":   f"Bearer {token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA":            "v1 1",
        "ReleaseVersion":  RELEASE_VERSION,
    }


async def _get_player_info(uid: str, server_url: str, token: str) -> dict:
    try:
        payload = _build_info_payload(uid)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{server_url}/GetPlayerPersonalShow",
                content=payload,
                headers=_make_headers(token)
            )
            if r.status_code == 200 and r.content:
                info = AccountPersonalShowInfo()
                info.ParseFromString(r.content)
                basic = info.basic_info
                return {
                    "name":  basic.nickname or f"UID#{uid}",
                    "likes": basic.liked,
                    "level": basic.level,
                    "region": basic.region,
                }
    except Exception as e:
        logger.warning(f"GetPlayerPersonalShow error: {e}")
    return {"name": f"UID#{uid}", "likes": 0, "level": 0, "region": ""}


async def _send_one_like(guest: dict, target_uid: str, region: str) -> bool:
    try:
        token, lock_region, server_url = await create_jwt(guest["uid"], guest["password"])
        if not server_url or server_url == "0":
            server_url = SERVER_MAP.get(region, DEFAULT_SERVER)

        payload = _build_like_payload(target_uid, lock_region or region)
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{server_url}/LikeProfile",
                content=payload,
                headers=_make_headers(token)
            )
            success = r.status_code in (200, 204)
            if success:
                logger.debug(f"[{guest['uid']}] Like sent → {target_uid} ({r.status_code})")
            else:
                logger.debug(f"[{guest['uid']}] Like failed → {r.status_code}")
            return success
    except Exception as e:
        logger.warning(f"[{guest['uid']}] Like error: {e}")
        return False


def _load_accounts(region: str) -> list:
    """Load ALL available accounts from all config files for maximum likes."""
    all_accounts = []
    seen_uids = set()
    configs = [
        "config/sg_config.json",
        "config/ind_config.json",
        "config/br_config.json",
        "config/europe_config.json",
    ]
    for path in configs:
        try:
            with open(path) as f:
                for acc in json.load(f):
                    uid = str(acc.get("uid", ""))
                    if uid and uid not in seen_uids:
                        seen_uids.add(uid)
                        all_accounts.append(acc)
        except Exception:
            pass
    return all_accounts


def send_like_real(uid: str, region: str) -> dict:
    region = region.upper()
    accounts = _load_accounts(region)

    if not accounts:
        return {
            "success": False,
            "error": f"Tidak ada guest account untuk region {region}.",
            "likes_sent": 0,
        }

    # ── Phase 1: Pre-fetch JWT tokens sequentially to avoid rate-limiting ──
    # Garena queues logins when too many come from same IP simultaneously.
    # We fetch tokens one-by-one with a small delay, then blast likes in parallel.

    JWT_DELAY      = 0.35   # seconds between login requests
    LIKE_CONCURRENT = 30    # parallel like sends (after tokens ready)

    async def _blast():
        # Step 1 — info before (use first working account)
        before_info = {"name": f"UID#{uid}", "likes": 0}
        first_token = None
        first_srv   = DEFAULT_SERVER

        for acc in accounts[:5]:
            try:
                tok, _, srv = await create_jwt(acc["uid"], acc["password"])
                srv = srv if srv and srv != "0" else DEFAULT_SERVER
                first_token = tok
                first_srv   = srv
                before_info = await _get_player_info(uid, srv, tok)
                break
            except Exception:
                await asyncio.sleep(0.2)

        # Step 2 — pre-fetch all JWT tokens sequentially
        ready = []  # list of (token, server_url, region)
        for acc in accounts:
            try:
                tok, lock_reg, srv = await create_jwt(acc["uid"], acc["password"])
                srv = srv if srv and srv != "0" else DEFAULT_SERVER
                ready.append((tok, srv, lock_reg or region))
                logger.debug(f"[token] {acc['uid']} OK")
            except Exception as e:
                logger.debug(f"[token] {acc['uid']} fail: {e}")
            await asyncio.sleep(JWT_DELAY)

        if not ready:
            return before_info, before_info, 0

        # Step 3 — blast likes concurrently using pre-fetched tokens
        like_payload = _build_like_payload(uid, region)
        semaphore = asyncio.Semaphore(LIKE_CONCURRENT)

        async def _do_like(token, srv, _reg):
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        r = await client.post(
                            f"{srv}/LikeProfile",
                            content=like_payload,
                            headers=_make_headers(token)
                        )
                        return r.status_code in (200, 204)
                except Exception:
                    return False

        like_tasks = [_do_like(tok, srv, reg) for tok, srv, reg in ready]
        results    = await asyncio.gather(*like_tasks, return_exceptions=True)
        sent       = sum(1 for r in results if r is True)

        # Step 4 — info after
        after_info = before_info.copy()
        if first_token:
            try:
                after_info = await _get_player_info(uid, first_srv, first_token)
            except Exception:
                pass

        return before_info, after_info, sent

    try:
        before, after, sent = asyncio.run(_blast())
    except Exception as e:
        logger.error(f"Blast error: {e}")
        return {"success": False, "error": str(e)}

    added = max(0, after["likes"] - before["likes"])

    return {
        "success":        sent > 0,
        "demo":           False,
        "player_name":    before["name"],
        "uid":            uid,
        "region":         region,
        "likes_before":   before["likes"],
        "likes_after":    after["likes"],
        "likes_added":    added,
        "accounts_used":  sent,
        "total_accounts": len(accounts),
    }
