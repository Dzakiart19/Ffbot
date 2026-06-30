"""
activator.py — Aktivasi akun Free Fire agar like bisa terhitung.

Strategi aktivasi:
  1. create_jwt() → dapat JWT + server_url resmi dari Garena
  2. bYe() (GetLoginData) 3× keepalive ke server game
  3. Mass parallel via ThreadPoolExecutor

Fungsi publik:
  activate_account(uid, password, region)    → bool
  activate_bulk(accounts, region, workers)   → dict
  activate_from_file(filepath, region)       → dict
"""

import os
import re
import sys
import time
import logging
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Region → fallback client_url jika server_url tidak tersedia
_REGION_CLIENT = {
    "IND": "client.ind.freefiremobile.com",
    "BR":  "client.us.freefiremobile.com",
    "US":  "client.us.freefiremobile.com",
    "NA":  "client.us.freefiremobile.com",
    "SAC": "client.us.freefiremobile.com",
}
_DEFAULT_CLIENT = "clientbp.ggpolarbear.com"


def activate_account(uid: str, password: str, region: str = "IND",
                     keepalive_rounds: int = 3) -> bool:
    """
    Aktivasi satu akun dengan GetLoginData + keepalive rounds.
    Return True jika minimal 1 round berhasil.
    """
    region = region.upper()
    try:
        # ── Ambil JWT via create_jwt (garena/get_jwt.py) ──
        from garena.get_jwt import create_jwt

        loop = asyncio.new_event_loop()
        try:
            jwt, lock_reg, server_url = loop.run_until_complete(
                create_jwt(uid, password, region=region)
            )
        finally:
            loop.close()

        if not jwt:
            logger.warning(f"[act] {uid}: JWT gagal")
            return False

        # ── Tentukan client_url (hostname) ──────────────────
        # server_url dari create_jwt sudah hostname (misal "clientbp.ggpolarbear.com")
        # atau mungkin "0"/"" jika tidak ada → fallback ke mapping region
        client_url = server_url if (server_url and server_url not in ("0", "")) else None
        if not client_url:
            effective = (lock_reg or region).upper()
            client_url = _REGION_CLIENT.get(effective, _DEFAULT_CLIENT)
        # Hapus prefix https:// jika ada
        if client_url.startswith("https://"):
            client_url = client_url[8:]

        # ── GetLoginData keepalive via bYe() dari guest.py ──
        _ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        import guest as _g

        # Init pool jika belum, lalu ambil session
        try:
            if not _g.session_pool:
                _g.init_session_pool()
            session = _g.get_pool_session()
        except Exception:
            session = _make_session()
        success_count = 0

        for i in range(keepalive_rounds):
            try:
                ok = _g.bYe(session, jwt, client_url)
                if ok:
                    success_count += 1
                    logger.debug(f"[act] {uid} round {i+1}/{keepalive_rounds} ✓")
                else:
                    logger.debug(f"[act] {uid} round {i+1}/{keepalive_rounds} ✗")
            except Exception as e:
                logger.debug(f"[act] {uid} round {i+1} error: {e}")
            if i < keepalive_rounds - 1:
                time.sleep(1.5)

        activated = success_count > 0
        logger.info(f"[act] {uid}: activated={activated} "
                    f"({success_count}/{keepalive_rounds} rounds) client={client_url}")
        return activated

    except Exception as e:
        logger.warning(f"[act] {uid}: error — {e}")
        return False


def _make_session():
    import requests, urllib3
    urllib3.disable_warnings()
    s = requests.Session()
    s.verify  = False
    s.timeout = 15
    return s


def activate_bulk(accounts: list, region: str = "IND",
                  max_workers: int = 20,
                  keepalive_rounds: int = 3,
                  progress_cb=None) -> dict:
    """
    Aktivasi massal secara paralel.
    accounts: list of {"uid": ..., "password": ...}
    Return: {"ok": [...uid], "fail": [...uid], "total": n}
    """
    region    = region.upper()
    ok_list   = []
    fail_list = []
    lock      = threading.Lock()

    def _worker(acc):
        uid    = str(acc.get("uid", ""))
        pwd    = str(acc.get("password", ""))
        result = activate_account(uid, pwd, region, keepalive_rounds)
        with lock:
            if result:
                ok_list.append(uid)
            else:
                fail_list.append(uid)
            if progress_cb:
                try:
                    progress_cb(len(ok_list), len(fail_list), len(accounts))
                except Exception:
                    pass
        return result

    workers = max(1, min(max_workers, len(accounts)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_worker, accounts))

    summary = {"ok": ok_list, "fail": fail_list, "total": len(accounts)}
    logger.info(f"[act-bulk] {region}: {len(ok_list)} OK, "
                f"{len(fail_list)} fail dari {len(accounts)}")
    return summary


def activate_from_file(filepath: str, region: str = "IND",
                        max_workers: int = 20) -> dict:
    """
    Baca akun dari GEN txt file dan aktivasi massal.
    Format baris: BOT = ... | UiD = ... | PassWord = ... | ...
    """
    accounts = []
    try:
        with open(filepath) as f:
            for line in f:
                uid_m = re.search(r'UiD = (\d+)', line)
                pw_m  = re.search(r'PassWord = (\S+)', line)
                if uid_m and pw_m:
                    accounts.append({
                        "uid":      uid_m.group(1),
                        "password": pw_m.group(1),
                    })
    except Exception as e:
        logger.error(f"[act] Baca file gagal: {e}")
        return {"ok": [], "fail": [], "total": 0}

    logger.info(f"[act] Aktivasi {len(accounts)} akun dari {filepath}...")
    return activate_bulk(accounts, region, max_workers)
