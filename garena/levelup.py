"""
Free Fire TCP Level-Up Bot
Integrated from:
  - Muraxlee/Free-Fire-Level-up-bot  (TCP login + start-spam loop)
  - shypakistani/Freefire-TCP-BOT    (protobuf packet builders)

Public API:
  levelup_accounts(accounts, team_code, region, rounds) -> dict
  levelup_account(uid, password, team_code, region, rounds) -> dict
"""

import socket
import threading
import time
import logging
import json
import base64
import re
import requests
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.json_format import MessageToJson

from garena.get_jwt import create_jwt_full as _create_jwt_full

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────
_API_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
_API_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

START_SPAM_DURATION = 18    # seconds to spam start packets
WAIT_AFTER_MATCH    = 20    # seconds to wait for match to end
START_SPAM_DELAY    = 0.2   # delay between start packets

# TCP server ports (standard FF game server ports)
_TCP_ONLINE_PORT  = 17000
_TCP_WHISPER_PORT = 17001

# Region → fallback TCP server IPs if tp_url is empty
_REGION_TCP_IP = {
    "ID":     "34.126.76.45",
    "SG":     "34.126.76.45",
    "IND":    "13.251.127.247",
    "BR":     "18.228.180.10",
    "EUROPE": "35.205.151.200",
}

# join_teamcode pre-built packet base (from Muraxlee/Free-Fire-Level-up-bot byte.py)
_JOIN_TEAM_BASE = (
    "080412b705220701090a0b1219202a07{room_id_hex}300640014ae9040a8001303946454133424438453839"
    "323231443032303331423031313131313030303230303239303030323030323530303032353442383542303530"
    "393030303033423431373232393134323230313034303631343034376462626236636163626536363734373436"
    "356530303030303066663037303930353065313262636665363810dd011abf03755154571b08004d000c095009"
    "0c560c0b0857015a0f020f5d5009085657570c0b075d0f04080809120208440b0c0000080b5101060f0f060e"
    "5c010d0d5406560c0b0b0a5b005b0d0505000d1b020a445e5b0f026270697b636b5c606d4e5e437470517d59"
    "00665b5a04010e1a094f7c575b4a5178697f480878760e50606b585259697b077e5b605c4e0d12020a446b5e"
    "08610b4f465651546b465208740a7b436940780d7d4b561d610413094f684e54574a516a75547660484172750"
    "f5a7a416547540a6c4453080f1b08084d014e4c457c41066a1649485f08490413705b7e4f7a567f5e5c590005"
    "110b455e5e79760d0a775246005f52024751745148407c096f5d69794b750e1b0a4e6c747840625c7f415e6c1"
    "d6d5f081e02007f477f7d640e7e56567e041b50575654515e1f43564a5b5c565e5d484d595e5d5854525a5c53"
    "4c584c57037a015571555b545267095c6b6001017504794d6273524e765c051b0b4460037b0b41617641084871"
    "51694972606b426b75440a7c415b045205100d44540e4d6a697a4a55747c41730b6f5f487a61597d68537369"
    "745d520e1a0c4f505d037d7a7203410c77716a69536c7f755363746b667c736860600d22047c575755300b3a09"
    "1d6d647370687a1d144208312e3130382e3134480350015a0c0a044944433110761a024d455a0d0a04494443"
    "321084011a024d455a0d0a044944433310d7011a024d456a02656e8201024f52"
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _encrypt_api(plain_hex: str) -> str:
    data = bytes.fromhex(plain_hex)
    cipher = AES.new(_API_KEY, AES.MODE_CBC, _API_IV)
    return cipher.encrypt(pad(data, AES.block_size)).hex()


def _dec_to_hex(n: int) -> str:
    h = hex(n)[2:]
    return h if len(h) > 1 else "0" + h


def _encode_varint(n: int) -> bytes:
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            break
    return bytes(out)


def _create_varint_field(field_num: int, val: int) -> bytes:
    hdr = (field_num << 3) | 0
    return _encode_varint(hdr) + _encode_varint(val)


def _create_length_field(field_num: int, val) -> bytes:
    hdr = (field_num << 3) | 2
    enc = val.encode() if isinstance(val, str) else val
    return _encode_varint(hdr) + _encode_varint(len(enc)) + enc


def _build_proto(fields: dict) -> bytes:
    out = bytearray()
    for field, val in fields.items():
        if isinstance(val, dict):
            nested = _build_proto(val)
            out.extend(_create_length_field(field, nested))
        elif isinstance(val, int):
            out.extend(_create_varint_field(field, val))
        else:
            out.extend(_create_length_field(field, val))
    return bytes(out)


def _encrypt_tcp(data_hex: str, key: bytes, iv: bytes) -> str:
    data = bytes.fromhex(data_hex)
    key  = key if isinstance(key, bytes) else bytes.fromhex(key.hex())
    iv   = iv  if isinstance(iv,  bytes) else bytes.fromhex(iv.hex())
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(data, AES.block_size)).hex()


def _make_packet(pkt_type: str, data_hex: str, key: bytes, iv: bytes) -> bytes:
    """Encrypt data and wrap with packet header."""
    enc = _encrypt_tcp(data_hex, key, iv)
    length_hex = _dec_to_hex(len(enc) // 2)
    llen = len(length_hex)
    if llen == 2:
        header = pkt_type + "000000" + length_hex
    elif llen == 3:
        header = pkt_type + "00000"  + length_hex
    elif llen == 4:
        header = pkt_type + "0000"   + length_hex
    else:
        header = pkt_type + "000"    + length_hex
    return bytes.fromhex(header + enc)


# ─── Login flow (OB54 / ggpolarbear — same endpoint as like_api) ─────────────

def _login_sync(uid: str, password: str, region: str = "ID") -> dict:
    """Synchronous wrapper around create_jwt_full(). Returns login info dict."""
    import asyncio
    return asyncio.run(_create_jwt_full(uid, password, region))


def _parse_tcp_servers(tp_url: str, region: str):
    """Extract online/whisper IPs from tp_url field. Returns (o_ip, w_ip)."""
    if tp_url:
        parts = [p.strip() for p in tp_url.split(";") if p.strip()]
        # Skip hostname (first part if it's not an IP), take first real IP
        ips = [p for p in parts if p and p[0].isdigit()]
        if ips:
            return ips[0], ips[0]
    fallback = _REGION_TCP_IP.get(region.upper(), "34.126.76.45")
    return fallback, fallback


def _build_tcp_token(jwt_token: str, key: bytes, iv: bytes, timestamp: int) -> str:
    """Build the initial TCP handshake token hex string."""
    import jwt as _jwt
    decoded = _jwt.decode(jwt_token, options={"verify_signature": False})
    account_id = decoded.get("account_id", 0)
    encoded_acc = hex(account_id)[2:]
    time_hex = _dec_to_hex(timestamp)
    token_hex = jwt_token.encode().hex()
    enc_token = _encrypt_tcp(token_hex, key, iv)
    head_len = len(enc_token) // 2
    head_len_hex = hex(head_len)[2:]

    length = len(encoded_acc)
    zeros = {9: "0000000", 8: "00000000", 10: "000000", 7: "000000000"}.get(length, "00000000")
    head = f"0115{zeros}{encoded_acc}{time_hex}00000{head_len_hex}"
    return head + enc_token


# ─── Packet builders ─────────────────────────────────────────────────────────

def _build_start_packet(key: bytes, iv: bytes) -> bytes:
    """Build 0515 start-match packet."""
    proto = _build_proto({1: 9, 2: {1: 12480598706}})
    return _make_packet("0515", proto.hex(), key, iv)


def _build_leave_packet(key: bytes, iv: bytes) -> bytes:
    """Build 0515 leave-match packet."""
    proto = _build_proto({1: 7, 2: {1: 12480598706}})
    return _make_packet("0515", proto.hex(), key, iv)


def _build_join_team_packet(team_code: str, key: bytes, iv: bytes) -> bytes:
    """Build join-team-code packet (from Muraxlee/Free-Fire-Level-up-bot byte.py)."""
    room_id_hex = "".join(format(ord(c), "x") for c in team_code)
    template = _JOIN_TEAM_BASE.replace("\n", "")
    packet = template.format(room_id_hex=room_id_hex)
    enc = _encrypt_tcp(packet, key, iv)
    length_hex = _dec_to_hex(len(enc) // 2)
    llen = len(length_hex)
    if llen == 2:
        return bytes.fromhex("0515000000" + length_hex + enc)
    elif llen == 3:
        return bytes.fromhex("051500000"  + length_hex + enc)
    elif llen == 4:
        return bytes.fromhex("05150000"   + length_hex + enc)
    else:
        return bytes.fromhex("05150000"   + length_hex + enc)


# ─── TCP Bot Client ───────────────────────────────────────────────────────────

class _FFBotClient:
    """
    Manages the TCP connection lifecycle for one FF guest account.
    Connects, joins team, spams start packets for `rounds` cycles, then disconnects.
    """

    def __init__(self, uid: str, password: str):
        self.uid      = uid
        self.password = password
        self.key: bytes | None = None
        self.iv:  bytes | None = None
        self._online_sock:  socket.socket | None = None
        self._whisper_sock: socket.socket | None = None
        self._stop = threading.Event()

    # ── Login ────────────────────────────────────────────────────────────────

    def login(self, region: str = "ID"):
        """Full login → sets self.key / self.iv, returns (tcp_token_hex, w_ip, w_port, o_ip, o_port)."""
        info = _login_sync(self.uid, self.password, region)
        jwt_token = info["token"]
        self.key  = info["ak"]
        self.iv   = info["aiv"]
        timestamp = info["kts"]

        o_ip, w_ip = _parse_tcp_servers(info.get("tp_url", ""), region)
        o_port, w_port = _TCP_ONLINE_PORT, _TCP_WHISPER_PORT

        tcp_token = _build_tcp_token(jwt_token, self.key, self.iv, timestamp)
        return tcp_token, w_ip, w_port, o_ip, o_port

    # ── Socket helpers ───────────────────────────────────────────────────────

    def _connect_online(self, tcp_token: str, o_ip: str, o_port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((o_ip, o_port))
        sock.settimeout(None)
        sock.send(bytes.fromhex(tcp_token))
        self._online_sock = sock
        logger.debug(f"[{self.uid}] Online connected {o_ip}:{o_port}")

    def _connect_whisper(self, tcp_token: str, w_ip: str, w_port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((w_ip, w_port))
        sock.settimeout(None)
        sock.send(bytes.fromhex(tcp_token))
        self._whisper_sock = sock
        logger.debug(f"[{self.uid}] Whisper connected {w_ip}:{w_port}")

    def _disconnect(self):
        for sock in (self._online_sock, self._whisper_sock):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self._online_sock  = None
        self._whisper_sock = None

    # ── Levelup loop ─────────────────────────────────────────────────────────

    def run_levelup(self, team_code: str, region: str = "ID", rounds: int = 3) -> dict:
        """
        Login, connect, join team, spam start for `rounds` match cycles.
        Returns a summary dict.
        """
        result = {"uid": self.uid, "success": False, "rounds_done": 0, "error": None}
        try:
            logger.info(f"[{self.uid}] Logging in for levelup...")
            tcp_token, w_ip, w_port, o_ip, o_port = self.login(region)

            self._connect_online(tcp_token, o_ip, o_port)
            self._connect_whisper(tcp_token, w_ip, w_port)

            join_pkt  = _build_join_team_packet(team_code, self.key, self.iv)
            start_pkt = _build_start_packet(self.key, self.iv)
            leave_pkt = _build_leave_packet(self.key, self.iv)

            for rnd in range(rounds):
                if self._stop.is_set():
                    break
                logger.info(f"[{self.uid}] Round {rnd+1}/{rounds} — joining team {team_code}")
                try:
                    self._online_sock.send(join_pkt)
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"[{self.uid}] Join failed: {e}")
                    break

                # Spam start packets
                end_time = time.time() + START_SPAM_DURATION
                while time.time() < end_time and not self._stop.is_set():
                    try:
                        self._online_sock.send(start_pkt)
                    except Exception as e:
                        logger.warning(f"[{self.uid}] Start packet error: {e}")
                        break
                    time.sleep(START_SPAM_DELAY)

                logger.info(f"[{self.uid}] Waiting {WAIT_AFTER_MATCH}s for match...")
                for _ in range(WAIT_AFTER_MATCH):
                    if self._stop.is_set():
                        break
                    time.sleep(1)

                # Leave
                try:
                    self._online_sock.send(leave_pkt)
                    time.sleep(2)
                except Exception:
                    pass

                result["rounds_done"] += 1

            result["success"] = result["rounds_done"] > 0
        except Exception as e:
            logger.error(f"[{self.uid}] Levelup error: {e}")
            result["error"] = str(e)
        finally:
            self._disconnect()

        return result

    def stop(self):
        self._stop.set()


# ─── Public API ───────────────────────────────────────────────────────────────

def levelup_account(uid: str, password: str, team_code: str,
                    region: str = "ID", rounds: int = 3) -> dict:
    """Level up a single account. Blocking."""
    bot = _FFBotClient(uid, password)
    return bot.run_levelup(team_code, region, rounds)


def levelup_accounts(accounts: list[dict], team_code: str,
                     region: str = "ID", rounds: int = 3,
                     max_concurrent: int = 5) -> dict:
    """
    Level up multiple accounts concurrently.
    accounts: list of {"uid": str, "password": str}
    Returns aggregate result.
    """
    results = []
    lock = threading.Lock()
    semaphore = threading.Semaphore(max_concurrent)

    def _run(acc):
        with semaphore:
            r = levelup_account(acc["uid"], acc["password"], team_code, region, rounds)
            with lock:
                results.append(r)

    threads = [threading.Thread(target=_run, args=(a,), daemon=True) for a in accounts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    success  = sum(1 for r in results if r["success"])
    failed   = len(results) - success
    return {
        "total":    len(accounts),
        "success":  success,
        "failed":   failed,
        "details":  results,
    }
