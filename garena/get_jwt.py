"""
Garena Free Fire JWT generator.
Flow: uid+password → OAuth token → LoginReq protobuf → AES encrypt → MajorLogin → JWT
Based on: github.com/kaifcodec/freefire-like-and-guest-api
"""
import base64
import json
import asyncio
import httpx
from google.protobuf import json_format
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from garena.ff_proto import freefire_pb2

# AES keys (base64 encoded in source)
MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')   # = b'Yg&tc%DEuh6%Zc^8'
MAIN_IV  = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')   # = b'6oyZDr22E3ychjM%'

RELEASE_VERSION = "OB50"
USER_AGENT      = "Dalvik/2.1.0 (Linux; U; Android 13; CPH2095 Build/RKQ1.211119.001)"

OAUTH_URL   = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
CLIENT_ID   = "100067"
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

LOGIN_URLS = {
    "IND": "https://loginbp.ind.freefiremobile.com/MajorLogin",
    "BR":  "https://loginbp.us.freefiremobile.com/MajorLogin",
    "US":  "https://loginbp.us.freefiremobile.com/MajorLogin",
}
DEFAULT_LOGIN_URL = "https://loginbp.ggblueshark.com/MajorLogin"


def _aes_encrypt(plaintext: bytes) -> bytes:
    cipher = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def _decode_proto(data: bytes, msg_class):
    obj = msg_class()
    obj.ParseFromString(data)
    return obj


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
    Full JWT generation flow.
    Returns: (jwt_token, lock_region, server_url)
    """
    access_token, open_id = await get_oauth_token(uid, password)
    if access_token == "0":
        raise ValueError(f"OAuth failed for uid={uid}")

    # Build LoginReq protobuf
    login_req = freefire_pb2.LoginReq()
    login_req.open_id            = open_id
    login_req.open_id_type       = "4"
    login_req.login_token        = access_token
    login_req.orign_platform_type = "4"

    proto_bytes   = login_req.SerializeToString()
    encrypted     = _aes_encrypt(proto_bytes)

    login_url = DEFAULT_LOGIN_URL
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

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(login_url, content=encrypted, headers=headers)
        login_res = _decode_proto(r.content, freefire_pb2.LoginRes)
        msg = json.loads(json_format.MessageToJson(login_res))

        token      = msg.get("token", "0")
        region     = msg.get("lockRegion", msg.get("lock_region", "0"))
        server_url = msg.get("serverUrl", msg.get("server_url", "0"))

        if token == "0":
            raise ValueError(f"MajorLogin failed for uid={uid}, response: {msg}")

        return token, region, server_url
