"""
Auto guest account generator.
Menggunakan endpoint Garena untuk mendaftar akun guest baru secara otomatis.
"""
import uuid
import time
import logging
import requests
import json
import os

from garena.token_manager import token_manager

logger = logging.getLogger(__name__)

# Garena guest registration endpoint (from APK reverse engineering)
GUEST_REGISTER_URLS = {
    "ID":     "https://loginbp.ggblueshark.com/MajorLogin",
    "SG":     "https://loginbp.ggblueshark.com/MajorLogin",
    "EUROPE": "https://loginbp.ggblueshark.com/MajorLogin",
    "IND":    "https://loginbp.ind.freefiremobile.com/MajorLogin",
    "BR":     "https://loginbp.us.freefiremobile.com/MajorLogin",
}

REGISTER_HEADERS = {
    "User-Agent":      "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
    "Connection":      "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type":    "application/x-www-form-urlencoded",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA":            "v1 1",
    "ReleaseVersion":  "OB47.0.1",
}


def _generate_device_id() -> str:
    return str(uuid.uuid4()).replace("-", "").upper()[:16]


def _build_guest_payload(device_id: str) -> bytes:
    """
    Build protobuf payload for guest account registration.
    Uses raw protobuf encoding for GuestMajorLogin.
    Field 1 (platform, int32) = 3 (Android)
    Field 2 (device_id, string)
    Field 6 (garena, int32) = 1
    """
    def encode_varint(v):
        buf = []
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                buf.append(b | 0x80)
            else:
                buf.append(b)
                break
        return bytes(buf)

    def encode_field(field_number, wire_type, value):
        tag = (field_number << 3) | wire_type
        return encode_varint(tag) + value

    def encode_string(s):
        b = s.encode("utf-8")
        return encode_varint(len(b)) + b

    payload  = encode_field(1, 0, encode_varint(3))
    payload += encode_field(2, 2, encode_string(device_id))
    payload += encode_field(6, 0, encode_varint(1))
    return payload


def create_guest_account(region: str = "ID") -> dict | None:
    """
    Try to auto-register a guest FF account.
    Returns {"uid": str, "password": str} or None on failure.
    """
    region = region.upper()
    url    = GUEST_REGISTER_URLS.get(region, GUEST_REGISTER_URLS["ID"])
    device_id = _generate_device_id()

    try:
        payload = _build_guest_payload(device_id)
        r = requests.post(url, data=payload, headers=REGISTER_HEADERS, timeout=12)

        if r.status_code == 200 and r.content:
            # Try to parse response protobuf
            # Response typically contains uid (field 1) and token/password (field 2)
            content = r.content
            # Simple varint extractor for field 1 (uid)
            uid = _extract_field_varint(content, 1)
            pwd = _extract_field_string(content, 2) or device_id

            if uid and uid > 0:
                logger.info(f"Guest account created: uid={uid}, region={region}")
                return {"uid": str(uid), "password": str(pwd)}

        logger.warning(f"Guest registration failed [{region}]: status={r.status_code}, body={r.content[:100]}")
        return None

    except Exception as e:
        logger.error(f"Guest auto-create error [{region}]: {e}")
        return None


def _extract_field_varint(data: bytes, field_number: int) -> int | None:
    i = 0
    while i < len(data):
        try:
            tag_byte = data[i]; i += 1
            field = tag_byte >> 3
            wire  = tag_byte & 0x07
            if wire == 0:  # varint
                val, shift = 0, 0
                while True:
                    b = data[i]; i += 1
                    val |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80):
                        break
                if field == field_number:
                    return val
            elif wire == 2:  # length-delimited
                length, shift = 0, 0
                while True:
                    b = data[i]; i += 1
                    length |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80):
                        break
                i += length
            else:
                break
        except IndexError:
            break
    return None


def _extract_field_string(data: bytes, field_number: int) -> str | None:
    i = 0
    while i < len(data):
        try:
            tag_byte = data[i]; i += 1
            field = tag_byte >> 3
            wire  = tag_byte & 0x07
            if wire == 0:  # varint
                while True:
                    b = data[i]; i += 1
                    if not (b & 0x80): break
            elif wire == 2:  # length-delimited
                length, shift = 0, 0
                while True:
                    b = data[i]; i += 1
                    length |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80): break
                chunk = data[i:i+length]; i += length
                if field == field_number:
                    try:
                        return chunk.decode("utf-8")
                    except Exception:
                        return chunk.hex()
            else:
                break
        except IndexError:
            break
    return None


def bulk_create_guests(region: str, count: int = 10) -> list:
    """Create multiple guest accounts for a region."""
    created = []
    failed  = 0
    for i in range(count):
        acc = create_guest_account(region)
        if acc:
            saved = token_manager.add_account(region, acc["uid"], acc["password"])
            acc["saved"] = saved
            created.append(acc)
        else:
            failed += 1
        time.sleep(0.5)  # rate limit
    logger.info(f"Bulk create [{region}]: {len(created)} created, {failed} failed")
    return created
