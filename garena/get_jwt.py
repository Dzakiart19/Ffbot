"""
Garena Free Fire JWT generator.
Flow: uid+password → OAuth token → MajorLogin protobuf (full device fingerprint) → JWT
Updated to use OB54 endpoint and detailed device fingerprint for higher success rate.
"""
import base64
import asyncio
import httpx
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from garena.ff_proto.MajoRLogin_pb2   import MajorLogin
from garena.ff_proto.MajorLoginRes_pb2 import MajorLoginRes

# AES keys (same as before)
MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')   # b'Yg&tc%DEuh6%Zc^8'
MAIN_IV  = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')   # b'6oyZDr22E3ychjM%'

RELEASE_VERSION = "OB54"
USER_AGENT      = "Dalvik/2.1.0 (Linux; U; Android 11; SM-S908E Build/TP1A.220624.014)"

OAUTH_URL     = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
CLIENT_ID     = "100067"
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# Updated login endpoint (ggpolarbear is newer than ggblueshark)
MAJOR_LOGIN_URL = "https://loginbp.ggpolarbear.com/MajorLogin"
LOGIN_URLS = {
    "IND": "https://loginbp.ind.freefiremobile.com/MajorLogin",
    "BR":  "https://loginbp.us.freefiremobile.com/MajorLogin",
    "US":  "https://loginbp.us.freefiremobile.com/MajorLogin",
}


def _aes_encrypt(plaintext: bytes) -> bytes:
    cipher = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def _aes_decrypt(data: bytes) -> bytes:
    try:
        cipher = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
        return unpad(cipher.decrypt(data), AES.block_size)
    except Exception:
        return data


def _build_majorlogin(access_token: str, open_id: str, platform_type: int = 4) -> bytes:
    """Build MajorLogin protobuf with full device fingerprint."""
    m = MajorLogin()
    m.event_time           = str(datetime.now())[:-7]
    m.game_name            = "free fire"
    m.platform_id          = platform_type
    m.client_version       = "1.120.1"
    m.system_software      = "Android OS 9 / API-28"
    m.system_hardware      = "Handheld"
    m.telecom_operator     = "Verizon"
    m.network_type         = "WIFI"
    m.screen_width         = 1920
    m.screen_height        = 1080
    m.screen_dpi           = "280"
    m.processor_details    = "ARM64 FP ASIMD AES VMH | 2865 | 4"
    m.memory               = 3003
    m.gpu_renderer         = "Adreno (TM) 640"
    m.gpu_version          = "OpenGL ES 3.1 v1.46"
    m.unique_device_id     = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    m.client_ip            = "223.191.51.89"
    m.language             = "en"
    m.open_id              = open_id
    m.open_id_type         = str(platform_type)
    m.device_type          = "Handheld"
    m.access_token         = access_token
    m.platform_sdk_id      = 1
    m.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    m.login_by             = 3
    m.channel_type         = 3
    m.cpu_type             = 2
    m.cpu_architecture     = "64"
    m.client_version_code  = "2019118695"
    m.login_open_id_type   = platform_type
    m.origin_platform_type = str(platform_type)
    m.primary_platform_type= str(platform_type)
    return _aes_encrypt(m.SerializeToString())


async def get_oauth_token(uid: str, password: str) -> tuple[str, str]:
    """Step 1: Get OAuth access_token from Garena OAuth server."""
    payload = (
        f"uid={uid}&password={password}"
        f"&response_type=token&client_type=2"
        f"&client_secret={CLIENT_SECRET}&client_id={CLIENT_ID}"
    )
    headers = {
        "User-Agent":      USER_AGENT,
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Content-Type":    "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(OAUTH_URL, data=payload, headers=headers)
        data = r.json()
        return data.get("access_token", "0"), data.get("open_id", "0")


async def create_jwt(uid: str, password: str) -> tuple[str, str, str]:
    """
    Full JWT generation flow using full device fingerprint MajorLogin.
    Returns: (jwt_token, lock_region, server_url)
    Tries platform types [4=Guest, 8=Google, 3=Facebook, 6=Huawei] in order.
    """
    access_token, open_id = await get_oauth_token(uid, password)
    if access_token == "0":
        raise ValueError(f"OAuth failed for uid={uid}")

    headers = {
        "User-Agent":      USER_AGENT,
        "Connection":      "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Content-Type":    "application/octet-stream",
        "Expect":          "100-continue",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA":            "v1 1",
        "ReleaseVersion":  RELEASE_VERSION,
    }

    # Try platform types — Guest (4) first, then Google, Facebook, Huawei
    for p_type in [4, 8, 3, 6]:
        try:
            payload = _build_majorlogin(access_token, open_id, p_type)
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                r = await client.post(MAJOR_LOGIN_URL, content=payload, headers=headers)
                if r.status_code != 200:
                    continue

                # Try AES-decrypted response first, then raw
                login_res = MajorLoginRes()
                try:
                    login_res.ParseFromString(_aes_decrypt(r.content))
                except Exception:
                    login_res.ParseFromString(r.content)

                token      = login_res.token
                region     = login_res.lock_region
                server_url = login_res.server_url

                if token:
                    return token, region or "0", server_url or "0"
        except Exception:
            continue

    raise ValueError(f"MajorLogin failed for uid={uid} — all platform types tried")
