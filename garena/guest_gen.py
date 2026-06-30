"""
guest_gen.py — Modul guest account generator untuk KiosGamer.
Menggunakan PERSIS fungsi-fungsi dari guest.py (root) yang sudah terbukti bekerja.
Menggantikan garena/guest_auto.py yang lama.

API publik:
  create_guest_account(region)       → dict | None
  bulk_create_guests(region, count)  → list[dict]
"""

import os
import sys
import re
import json
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
logger = logging.getLogger(__name__)

# ── Import langsung dari guest.py di root project ─────────────────────────────
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import guest as _g   # import seluruh modul untuk kemudahan akses

# ── Paths ──────────────────────────────────────────────────────────────────────
_CONFIG_DIR = os.path.join(_ROOT, "config")

_REGION_CONFIG = {
    "ID":     "id_config.json",
    "IND":    "ind_config.json",
    "SG":     "sg_config.json",
    "EUROPE": "europe_config.json",
    "RU":     "europe_config.json",
    "BR":     "br_config.json",
    "US":     "br_config.json",
}

_REGION_CLIENT = {
    "IND": "client.ind.freefiremobile.com",
    "BR":  "client.us.freefiremobile.com",
    "US":  "client.us.freefiremobile.com",
    "NA":  "client.us.freefiremobile.com",
    "SAC": "client.us.freefiremobile.com",
}
_DEFAULT_CLIENT = "clientbp.ggpolarbear.com"

_file_locks: dict = {}
_fl_meta    = threading.Lock()

def _get_flock(path):
    with _fl_meta:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]


def _new_session() -> requests.Session:
    s = requests.Session()
    s.verify  = False
    s.timeout = 15
    return s


# ── Expose untuk garena/activator.py ─────────────────────────────────────────
def _get_login_data(session, jwt_token: str, client_url: str) -> bool:
    """Wrapper tipis ke bYe() dari guest.py."""
    try:
        return bool(_g.bYe(session, jwt_token, client_url))
    except Exception:
        return False


# ── Simpan akun ke GEN/ dan config/ ──────────────────────────────────────────
def _save_account(region: str, uid: str, password: str,
                   game_uid: str, nickname: str):
    region_up = region.upper()

    # GEN/{region}/Accounts-{region}.txt
    gen_folder = os.path.join(_ROOT, "GEN", region_up)
    os.makedirs(gen_folder, exist_ok=True)
    txt_path = os.path.join(gen_folder, f"Accounts-{region_up}.txt")
    line = (f"BOT = {game_uid} | UiD = {uid} | PassWord = {password} "
            f"| NamE = {nickname} | ReGioN = {region_up}\n")

    flock = _get_flock(txt_path)
    with flock:
        existing = set()
        if os.path.exists(txt_path):
            with open(txt_path) as f:
                for ln in f:
                    m = re.search(r'UiD = (\d+)', ln)
                    if m:
                        existing.add(m.group(1))
        if uid not in existing:
            with open(txt_path, 'a') as f:
                f.write(line)

    # config/{region}_config.json (untuk like_api.py)
    cfg_name = _REGION_CONFIG.get(region_up, f"{region_up.lower()}_config.json")
    cfg_path = os.path.join(_CONFIG_DIR, cfg_name)
    cfl = _get_flock(cfg_path)
    with cfl:
        try:
            accounts = []
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    accounts = json.load(f)
            if not any(str(a.get("uid")) == str(uid) for a in accounts):
                accounts.append({
                    "uid":         uid,
                    "password":    password,
                    "game_uid":    game_uid,
                    "lock_region": region_up,
                })
                os.makedirs(_CONFIG_DIR, exist_ok=True)
                with open(cfg_path, 'w') as f:
                    json.dump(accounts, f, indent=2)
        except Exception as e:
            logger.warning(f"Config save error: {e}")


# ── Inisialisasi session pool (tanpa Tor) ─────────────────────────────────────
_pool_ready = False
_pool_lock  = threading.Lock()

def _ensure_pool():
    global _pool_ready
    if _pool_ready:
        return
    with _pool_lock:
        if _pool_ready:
            return
        try:
            import subprocess
            tor_ok = subprocess.run(['which','tor'],capture_output=True).returncode == 0
            if not tor_ok:
                _g.init_session_pool()
            _pool_ready = True
        except Exception as e:
            logger.debug(f"pool init: {e}")
            _pool_ready = True


# ── Core: buat satu akun (logika PERSIS sama dengan AcCoUnTcReAtOr.cReAtE) ───
def create_guest_account(region: str = "IND") -> dict | None:
    """
    Buat satu akun guest Free Fire.
    Region paling stabil: "IND".
    "ID" bisa digunakan — hasilnya akun yang terlihat di server Indonesia.

    Return: {"uid","password","game_uid","lock_region","nickname","activated"}
    atau None jika gagal.
    """
    region  = region.upper()
    _ensure_pool()
    session = _g.get_pool_session() if _pool_ready else _new_session()

    try:
        # Password
        r1       = _g.yEet(6)
        r2       = _g.yEet(6)
        api_pass = f"KIOSGMR_{r1}-GMRS{r2}"

        # Step 1: Register Garena OAuth
        uid = _g.wOw(_g.hAhA, session, api_pass)

        # Step 2: Token grant
        access_token, open_id = _g.wOw(_g.lMaO, session, uid, api_pass)

        # Step 3: MajorRegister → game_uid
        reg_resp   = _g.wOw(_g.gG, session, "KiosGmr",
                             access_token, open_id, region, False)
        game_uid   = str(reg_resp.get(3, "")) if reg_resp else ""
        if not game_uid:
            raise Exception("No game_uid")

        # Step 4: MajorLogin → JWT
        lang_code = _g.rEgIoNlAnG.get(region, "en")
        login_resp, jwt_token = _g.wOw(_g.nIcE, session,
                                       access_token, open_id, region, lang_code)
        if not jwt_token:
            raise Exception("No JWT")

        lock_region, nickname = _g.hElLo(jwt_token)
        if not nickname:
            nickname = "KiosGmr"

        # Step 5: ChooseRegion jika belum terkunci
        final_jwt  = jwt_token
        need_lock  = (
            not lock_region
            or lock_region in (None, 'None', '..', '')
            or lock_region.upper() != region
        )
        if need_lock:
            _g.dUdE(session, region, jwt_token)
            login_resp2, jwt2 = _g.wOw(_g.nIcE, session,
                                        access_token, open_id, region, lang_code)
            if jwt2:
                final_jwt = jwt2
                lock_region2, nickname2 = _g.hElLo(jwt2)
                if nickname2:
                    nickname = nickname2
                lock_region = lock_region2
                login_resp = login_resp2

        # Ambil client_url dari response
        client_url_raw = login_resp.get(10)
        if isinstance(client_url_raw, str):
            client_url = client_url_raw
        elif isinstance(client_url_raw, list):
            client_url = client_url_raw[0] if client_url_raw else None
        else:
            client_url = None
        if client_url and client_url.startswith("https://"):
            client_url = client_url[8:]
        if not client_url:
            client_url = _REGION_CLIENT.get(region, _DEFAULT_CLIENT)

        # Step 6: GetLoginData (aktivasi)
        activated = False
        if final_jwt and client_url:
            try:
                activated = bool(_g.wOw(_g.bYe, session, final_jwt, client_url))
            except Exception:
                pass

        effective_region = (lock_region or region).upper()

        # Simpan ke GEN/ dan config/
        _save_account(effective_region, uid, api_pass, game_uid, nickname)

        acc = {
            "uid":         uid,
            "password":    api_pass,
            "game_uid":    game_uid,
            "lock_region": effective_region,
            "nickname":    nickname,
            "activated":   activated,
        }
        logger.info(f"[gen] ✅ uid={uid} game={game_uid} "
                    f"lock={effective_region} activated={activated}")
        return acc

    except Exception as e:
        logger.warning(f"[gen] ❌ {region}: {e}")
        return None


# ── Bulk paralel ───────────────────────────────────────────────────────────────
def bulk_create_guests(region: str = "IND", count: int = 10,
                        max_workers: int = 20,
                        progress_cb=None) -> list:
    """
    Buat `count` akun guest secara paralel.
    Setiap akun otomatis disimpan ke GEN/ dan config/.
    progress_cb(created_ok, failed, total) dipanggil tiap update.
    """
    region = region.upper()
    _ensure_pool()

    results  = []
    lock     = threading.Lock()
    counters = {"ok": 0, "fail": 0}

    def _worker(_):
        acc = create_guest_account(region)
        with lock:
            if acc:
                results.append(acc)
                counters["ok"] += 1
            else:
                counters["fail"] += 1
            if progress_cb:
                try:
                    progress_cb(counters["ok"], counters["fail"], count)
                except Exception:
                    pass

    workers = min(max_workers, count)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_worker, range(count)))

    logger.info(f"[bulk] {region}: {counters['ok']} berhasil, "
                f"{counters['fail']} gagal dari {count}")
    return results
