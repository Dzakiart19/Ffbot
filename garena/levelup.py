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

from garena.ff_proto.MajorLoginRes_pb2 import MajorLoginRes as _MajorLoginRes
from garena.ff_proto.jwt_generator_pb2 import Garena_420 as _Garena420

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────
_API_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
_API_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

START_SPAM_DURATION = 18    # seconds to spam start packets
WAIT_AFTER_MATCH    = 20    # seconds to wait for match to end
START_SPAM_DELAY    = 0.2   # delay between start packets

_OAUTH_URL        = "https://100067.connect.garena.com/oauth/guest/token/grant"
_MAJORLOGIN_URL   = "https://loginbp.ggblueshark.com/MajorLogin"
_GETLOGINDATA_URL = "https://client.ind.freefiremobile.com/GetLoginData"

_MAJORLOGIN_HEADERS = {
    "X-Unity-Version": "2018.4.11f1",
    "ReleaseVersion": "Ob51",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-GA": "v1 1",
    "Content-Length": "928",
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; ASUS_Z01QD Build/QKQ1.190825.002)",
    "Host": "loginbp.ggblueshark.com",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
}

# Template payload for MajorLogin (OB51 format, from Muraxlee/Free-Fire-Level-up-bot)
_TEMPLATE_HEX = (
    "1a13323032352d30372d33302031313a30323a3531220966726565206669726528013a07312e3131382e31"
    "422c416e64726f6964204f5320372e312e32202f204150492d323320284e32473438482f37303032353032"
    "3234294a0848616e6468656c645207416e64726f69645a045749464960c00c68840772033332307a1f4152"
    "4d7637205646507633204e454f4e20564d48207c2032343635207c203480019a1b8a010f416472656e6f20"
    "28544d292036343092010d4f70656e474c20455320332e319a012b476f6f676c657c31663361643662372d"
    "636562342d343934622d383730622d623164616364373230393131a2010c3139372e312e31322e313335aa"
    "0102656eb201203939366136323964626364623339363462653662363937386635643831346462ba010134"
    "c2010848616e6468656c64ca011073616d73756e6720534d2d473935354eea01406666393063303765623938"
    "3135616633306134336234613966363031393531366530653463373033623434303932353136643064656661"
    "346365663531663261f00101ca0207416e64726f6964d2020457494649ca03203734323862323533646566"
    "633136343031386336303461316562626665626466e003daa907e803899b07f003bf0ff803ae088004999b07"
    "8804daa9079004999b079804daa907c80403d204262f646174612f6170702f636f6d2e6474732e6672656566"
    "69726574682d312f6c69622f61726de00401ea044832303837663631633139663537663261663465376665666"
    "630623234643964397c2f646174612f6170702f636f6d2e6474732e667265656669726574682d312f626173"
    "652e61706bf00403f804018a050233329a050a32303139313138363933a80503b205094f70656e474c455332"
    "b805ff7fc00504e005dac901ea0507616e64726f6964f2055c4b71734854394748625876574c6668437950"
    "416c52526873626d43676542557562555551317375746d525536634e30524f3751453141486e496474385963"
    "784d614c575437636d4851322b7374745279377830663935542b6456593d8806019006019a060134a0601"
    "34b2061e40001147550d0c074f530b4d5c584d57416657545a065f2a091d6a0d5033"
)

_PLACEHOLDER_ACCESS   = b"ff90c07eb9815af30a43b4a9f6019516e0e4c703b44092516d0defa4cef51f2a"
_PLACEHOLDER_OPEN_ID  = b"996a629dbcdb3964be6b6978f5d814db"
_PLACEHOLDER_SIG_MD5  = b"7428b253defc164018c604a1ebbfebdf"
_PLACEHOLDER_DATETIME = b"2025-07-30 11:02:51"

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


# ─── Login flow (OB51 / ggblueshark) ─────────────────────────────────────────

def _oauth(uid: str, password: str):
    """OAuth → (access_token, open_id)"""
    resp = requests.post(_OAUTH_URL, headers={
        "Host": "100067.connect.garena.com",
        "User-Agent": "GarenaMSDK/4.0.19P4(G011A ;Android 10;en;EN;)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close",
    }, data={
        "uid": uid, "password": password,
        "response_type": "token", "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067",
    }, timeout=15)
    d = resp.json()
    return d["access_token"], d["open_id"]


def _major_login_ob51(access_token: str, open_id: str):
    """MajorLogin (OB51/ggblueshark) → (jwt, tcp_key, tcp_iv, timestamp)"""
    OLD_ACCESS = "ff90c07eb9815af30a43b4a9f6019516e0e4c703b44092516d0defa4cef51f2a"
    OLD_OID    = "996a629dbcdb3964be6b6978f5d814db"

    payload = bytes.fromhex(_TEMPLATE_HEX.replace("\n", ""))
    payload = payload.replace(OLD_OID.encode(),    open_id.encode())
    payload = payload.replace(OLD_ACCESS.encode(), access_token.encode())
    enc_payload = bytes.fromhex(_encrypt_api(payload.hex()))

    resp = requests.post(
        _MAJORLOGIN_URL, headers=_MAJORLOGIN_HEADERS,
        data=enc_payload, timeout=20, verify=False
    )
    if resp.status_code != 200 or len(resp.content) < 10:
        raise ValueError(f"MajorLogin OB51 failed: {resp.status_code}")

    res = _MajorLoginRes()
    res.ParseFromString(resp.content)

    ts_obj = Timestamp()
    ts_obj.FromNanoseconds(res.kts)
    timestamp = ts_obj.seconds * 1_000_000_000 + ts_obj.nanos

    return res.token, res.ak, res.aiv, timestamp


def _get_login_data(jwt_token: str, access_token: str):
    """Second-step: build second payload using JWT fields → GetLoginData → (whisper_ip, whisper_port, online_ip, online_port)"""
    # Decode JWT payload
    parts = jwt_token.split(".")
    padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    jwt_payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    external_id  = jwt_payload["external_id"]
    signature_md5 = jwt_payload["signature_md5"]

    now = str(datetime.now())[:-7]
    payload = bytes.fromhex(_TEMPLATE_HEX.replace("\n", ""))
    payload = payload.replace(b"2025-07-30 11:02:51", now.encode())
    payload = payload.replace(
        b"ff90c07eb9815af30a43b4a9f6019516e0e4c703b44092516d0defa4cef51f2a",
        access_token.encode()
    )
    payload = payload.replace(
        b"996a629dbcdb3964be6b6978f5d814db",
        external_id.encode()
    )
    payload = payload.replace(
        b"7428b253defc164018c604a1ebbfebdf",
        signature_md5.encode()
    )
    enc_payload = bytes.fromhex(_encrypt_api(payload.hex()))

    # GetLoginData
    headers = {
        "Expect": "100-continue",
        "Authorization": f"Bearer {jwt_token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "Ob51",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; G011A Build/PI)",
        "Host": "clientbp.common.ggbluefox.com",
        "Connection": "close",
        "Accept-Encoding": "gzip, deflate, br",
    }
    resp = requests.post(
        _GETLOGINDATA_URL, headers=headers,
        data=enc_payload, timeout=20, verify=False
    )
    resp.raise_for_status()

    # Parse protobuf response for server IPs
    from protobuf_decoder.protobuf_decoder import Parser

    def _parse(results):
        out = {}
        for r in results:
            if r.wire_type in ("varint", "string", "bytes"):
                out[int(r.field)] = {"data": r.data}
            elif r.wire_type == "length_delimited":
                out[int(r.field)] = {"data": _parse(r.data.results)}
        return out

    parsed = _parse(Parser().parse(resp.content.hex()))

    whisper_addr = parsed[32]["data"]   # IP:port
    online_addr  = parsed[14]["data"]

    def _split_addr(addr):
        ip   = addr[: len(addr) - 6]
        port = int(addr[len(addr) - 5:])
        return ip, port

    w_ip, w_port = _split_addr(whisper_addr)
    o_ip, o_port = _split_addr(online_addr)
    return w_ip, w_port, o_ip, o_port


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

    def login(self):
        """Full login flow → sets self.key / self.iv, returns tcp_token_hex and server IPs."""
        access_token, open_id = _oauth(self.uid, self.password)
        jwt_token, key, iv, timestamp = _major_login_ob51(access_token, open_id)
        self.key = key
        self.iv  = iv

        try:
            w_ip, w_port, o_ip, o_port = _get_login_data(jwt_token, access_token)
        except Exception as e:
            logger.warning(f"[{self.uid}] GetLoginData failed ({e}), using fallback server")
            w_ip, w_port = "13.251.127.247", 17000
            o_ip, o_port = "13.251.127.247", 17000

        tcp_token = _build_tcp_token(jwt_token, key, iv, timestamp)
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

    def run_levelup(self, team_code: str, rounds: int = 3) -> dict:
        """
        Login, connect, join team, spam start for `rounds` match cycles.
        Returns a summary dict.
        """
        result = {"uid": self.uid, "success": False, "rounds_done": 0, "error": None}
        try:
            logger.info(f"[{self.uid}] Logging in...")
            tcp_token, w_ip, w_port, o_ip, o_port = self.login()

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
    return bot.run_levelup(team_code, rounds)


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
