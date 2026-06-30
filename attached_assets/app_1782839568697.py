import os
import sys
import json
import time
import urllib.parse
import base64
import hashlib
import urllib3
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import requests
import logging

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# -------------------- BOT TOKEN (set at the start) --------------------
BOT_TOKEN = "8613550531:AAG76XHcz1OfSZ3mruM3i7ucxBzHLZN6aFU"
# ----------------------------------------------------------------------

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import protobuf modules
try:
    import MajoRLogin_pb2 as mLpB
    import MajorLoginRes_pb2 as mLrPb
except ImportError:
    print("\nProtobuf files missing! Exiting.")
    sys.exit(1)

# ----------------------------------------------------------------------
# Small‑caps converter (exactly as requested)
# ----------------------------------------------------------------------
small = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ',
    'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
    'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ',
    'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ'
}

def smallcaps(text: str) -> str:
    """Convert lowercase letters to small caps; leave others unchanged."""
    return ''.join(small.get(ch, ch) for ch in text)

def label_value(label: str, value: str) -> str:
    """Format a label‑value pair: both in small‑caps."""
    return f"{smallcaps(label)}: {smallcaps(str(value))}"

# ----------------------------------------------------------------------
# JSON command list – defines the main menu buttons
# ----------------------------------------------------------------------
COMMANDS = [
    {
        "text": "🔍 Cʜᴇᴄᴋ Bɪɴᴅ Iɴꜰᴏ",
        "callback_data": "check_bind_info",
        "style": "primary"
    },
    {
        "text": "📧 Bɪɴᴅ Eᴍᴀɪʟ",
        "callback_data": "bind_email",
        "style": "success"
    },
    {
        "text": "🔓 Uɴʙɪɴᴅ Eᴍᴀɪʟ",
        "callback_data": "unbind_email",
        "style": "danger"
    },
    {
        "text": "🔄 Cʜᴀɴɢᴇ Bɪɴᴅ Eᴍᴀɪʟ",
        "callback_data": "change_bind_email",
        "style": "primary"
    },
    {
        "text": "❌ Cᴀɴᴄᴇʟ Bɪɴᴅ Rᴇǫᴜᴇsᴛ",
        "callback_data": "cancel_bind_request",
        "style": "danger"
    },
    {
        "text": "🔄 Eᴀᴛ Tᴏ Aᴄᴄᴇss Tᴏᴋᴇɴ",
        "callback_data": "eat_access_token",
        "style": "success"
    },
    {
        "text": "🚫 Rᴇᴠᴏᴋᴇ Aᴄᴄᴇss Tᴏᴋᴇɴ",
        "callback_data": "revoke_access_token",
        "style": "danger"
    },
    {
        "text": "📜 Gᴇᴛ Lᴏɢɪɴ Hɪsᴛᴏʀʏ",
        "callback_data": "get_login_history",
        "style": "primary"
    },
    {
        "text": "🔗 Cʜᴇᴄᴋ Bɪɴᴅ Aᴄᴄᴏᴜɴᴛs",
        "callback_data": "check_Bɪɴᴅ_accounts",
        "style": "primary"
    },
    {
        "text": "👤 Oᴡɴᴇʀ Dᴇᴛᴀɪʟs",
        "callback_data": "owner_details",
        "style": "success"
    }
]

# ----------------------------------------------------------------------
# All helper functions (all outputs use smallcaps)
# ----------------------------------------------------------------------
def convert_seconds(s):
    d, h = divmod(s, 86400)
    h, m = divmod(h, 3600)
    m, s = divmod(m, 60)
    return f"{d} Day {h} Hour {m} Min {s} Sec"

def format_response_text(response_text, title="API Response"):
    try:
        parsed = json.loads(response_text)
        result_code = parsed.get("result")
        if result_code == 0:
            return f"✅ {smallcaps(title)}: {smallcaps('SUCCESS')}"
        elif result_code is not None:
            error_msg = parsed.get("error", "Unknown error")
            return f"❌ {smallcaps(title)}: {smallcaps('FAILED')} ({smallcaps('Code')} {result_code} | {error_msg})"
        else:
            return f"ℹ️ {smallcaps(title)}: {smallcaps('Completed (No standard result code)')}"
    except Exception:
        if '"result": 0' in response_text.replace(" ", ""):
            return f"✅ {smallcaps(title)}: {smallcaps('SUCCESS')}"
        else:
            return f"❌ {smallcaps(title)}: {smallcaps('Unrecognized response format')}"

def get_player_info(access_token):
    try:
        player_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(player_url, headers=headers, timeout=15, allow_redirects=True)
        parsed = urllib.parse.urlparse(resp.url)
        params = urllib.parse.parse_qs(parsed.query)
        uid = params.get("account_id", ["Unknown"])[0]
        nickname = params.get("nickname", ["Unknown"])[0]
        region = params.get("region", ["Unknown"])[0]
        return {"uid": uid, "nickname": urllib.parse.unquote(nickname), "region": region}
    except Exception:
        return {"uid": "Unknown", "nickname": "Unknown", "region": "Unknown"}

def check_bind_info(access_token):
    lines = []
    info = get_player_info(access_token)
    lines.append(smallcaps("👤 Player Information"))
    lines.append(label_value("UID", info['uid']))
    lines.append(label_value("Nickname", info['nickname']))
    lines.append(label_value("Region", info['region']))
    lines.append("")

    url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
    payload = {'app_id': "100067", 'access_token': access_token}
    headers = {
        'User-Agent': "GarenaMSDK/4.0.19P9(Redmi Note 5 ;Android 9;en;US;)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip"
    }
    try:
        response = requests.get(url, params=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            email = data.get("email", "")
            email_to_be = data.get("email_to_be", "")
            countdown = data.get("request_exec_countdown", 0)
            countdown_human = convert_seconds(countdown)
            result_code = data.get("result", -1)

            lines.append(smallcaps("🔐 Bind Information"))
            lines.append(label_value("Current Email", email if email else 'None'))
            lines.append(label_value("Pending Email", email_to_be if email_to_be else 'None'))
            if email_to_be:
                lines.append(label_value("Countdown", countdown_human))
            if result_code == 0:
                lines.append(label_value("Result", "✅ SUCCESS"))
            else:
                lines.append(label_value("Result", f"❌ FAILED (Code: {result_code})"))

            if email == "" and email_to_be != "":
                lines.append(f"ℹ️ {smallcaps('Summary')}: {smallcaps(f'Pending confirmation for {email_to_be} – confirms in {countdown_human}')}")
            elif email != "" and email_to_be == "":
                lines.append(f"ℹ️ {smallcaps('Summary')}: {smallcaps(f'Email confirmed: {email}')}")
            elif email == "" and email_to_be == "":
                lines.append(f"ℹ️ {smallcaps('Summary')}: {smallcaps('No recovery email set')}")
        else:
            lines.append(f"❌ {smallcaps('API Error')} (Status {response.status_code})")
    except Exception as e:
        lines.append(f"❌ {smallcaps('Failed to fetch info')}: {smallcaps(str(e))}")
    return "\n".join(lines)

def bind_email_flow(access_token, email, otp, security_code):
    headers = {
        "User-Agent": "GarenaMSDK/4.0.30",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    send_otp_data = {
        "email": email,
        "locale": "en_PK",
        "region": "PK",
        "app_id": "100067",
        "access_token": access_token
    }
    resp_send = requests.post(send_otp_url, headers=headers, data=send_otp_data)
    send_msg = format_response_text(resp_send.text, "Send OTP")
    if '"result":0' not in resp_send.text.replace(" ", ""):
        return False, f"❌ {smallcaps('Send OTP failed')}.\n{send_msg}"

    verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    verify_data = {
        "app_id": "100067",
        "access_token": access_token,
        "email": email,
        "code": otp,
        "otp": otp,
        "type": "1"
    }
    resp_verify = requests.post(verify_url, headers=headers, data=verify_data)
    verify_msg = format_response_text(resp_verify.text, "Verify OTP")
    try:
        verifier_token = resp_verify.json().get("verifier_token", "")
    except:
        verifier_token = ""
    if not verifier_token:
        return False, f"❌ {smallcaps('Verification failed')} – {smallcaps('no verifier token')}.\n{verify_msg}"

    bind_url = "https://100067.connect.garena.com/game/account_security/bind:create_bind_request"
    bind_data = {
        "email": email,
        "app_id": "100067",
        "access_token": access_token,
        "verifier_token": verifier_token,
        "secondary_password": security_code
    }
    resp_bind = requests.post(bind_url, headers=headers, data=bind_data)
    bind_msg = format_response_text(resp_bind.text, "Final Bind Request")
    return True, f"✅ {smallcaps('Bind process completed')}.\n{send_msg}\n{verify_msg}\n{bind_msg}"

def unbind_email_flow(access_token, method, otp_or_code):
    headers = {
        "User-Agent": "GarenaMSDK/4.0.30",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    try:
        url_info = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        info_payload = {'app_id': "100067", 'access_token': access_token}
        r_info = requests.get(url_info, params=info_payload, headers=headers, timeout=10)
        email = r_info.json().get("email", "")
    except:
        email = ""
    if not email:
        return False, f"❌ {smallcaps('No currently Bɪɴᴅ email found')}. {smallcaps('Cannot unbind.')}"

    identity_token = None
    if method == 1:  # OTP
        send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        send_data = {"email": email, "locale": "en_PK", "region": "PK",
                     "app_id": "100067", "access_token": access_token}
        resp = requests.post(send_otp_url, headers=headers, data=send_data)
        send_msg = format_response_text(resp.text, "Send OTP")
        if '"result":0' not in resp.text.replace(" ", ""):
            return False, f"❌ {smallcaps('Send OTP failed')}.\n{send_msg}"

        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": email, "app_id": "100067", "access_token": access_token, "otp": otp_or_code}
        resp = requests.post(verify_url, headers=headers, data=verify_data)
        verify_msg = format_response_text(resp.text, "Verify Identity")
        try:
            identity_token = resp.json().get("identity_token")
        except:
            identity_token = None
        if not identity_token:
            return False, f"❌ {smallcaps('Identity verification failed')}.\n{verify_msg}"
    else:  # Security Code
        hashed_code = hashlib.sha256(otp_or_code.encode('utf-8')).hexdigest()
        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": email, "app_id": "100067", "access_token": access_token,
                       "secondary_password": hashed_code}
        resp = requests.post(verify_url, headers=headers, data=verify_data)
        verify_msg = format_response_text(resp.text, "Verify Identity")
        try:
            identity_token = resp.json().get("identity_token")
        except:
            identity_token = None
        if not identity_token:
            return False, f"❌ {smallcaps('Identity verification failed')}.\n{verify_msg}"

    unbind_url = "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request"
    unbind_data = {"app_id": "100067", "access_token": access_token, "identity_token": identity_token}
    resp = requests.post(unbind_url, headers=headers, data=unbind_data)
    unbind_msg = format_response_text(resp.text, "Unbind Request")
    return True, f"✅ {smallcaps('Unbind completed')}.\n{verify_msg}\n{unbind_msg}"

def change_bind_flow(access_token, method, old_code, new_email, new_otp):
    headers = {
        "User-Agent": "GarenaMSDK/4.0.30",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    try:
        url_info = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        info_payload = {'app_id': "100067", 'access_token': access_token}
        r_info = requests.get(url_info, params=info_payload, headers=headers, timeout=10)
        old_email = r_info.json().get("email", "")
    except:
        old_email = ""
    if not old_email:
        return False, f"❌ {smallcaps('No currently Bɪɴᴅ email found')}."

    identity_token = None
    if method == 1:  # OTP
        send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        send_data = {"email": old_email, "locale": "en_PK", "region": "PK",
                     "app_id": "100067", "access_token": access_token}
        resp = requests.post(send_otp_url, headers=headers, data=send_data)
        send_msg = format_response_text(resp.text, "Send OTP (old)")
        if '"result":0' not in resp.text.replace(" ", ""):
            return False, f"❌ {smallcaps('Send OTP to old email failed')}.\n{send_msg}"

        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": old_email, "app_id": "100067", "access_token": access_token, "otp": old_code}
        resp = requests.post(verify_url, headers=headers, data=verify_data)
        verify_msg = format_response_text(resp.text, "Verify Identity")
        try:
            identity_token = resp.json().get("identity_token")
        except:
            identity_token = None
        if not identity_token:
            return False, f"❌ {smallcaps('Identity verification failed')}.\n{verify_msg}"
    else:  # Security Code
        hashed_code = hashlib.sha256(old_code.encode('utf-8')).hexdigest()
        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": old_email, "app_id": "100067", "access_token": access_token,
                       "secondary_password": hashed_code}
        resp = requests.post(verify_url, headers=headers, data=verify_data)
        verify_msg = format_response_text(resp.text, "Verify Identity")
        try:
            identity_token = resp.json().get("identity_token")
        except:
            identity_token = None
        if not identity_token:
            return False, f"❌ {smallcaps('Identity verification failed')}.\n{verify_msg}"

    send_otp_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
    send_data = {"email": new_email, "locale": "en_PK", "region": "PK",
                 "app_id": "100067", "access_token": access_token}
    resp = requests.post(send_otp_url, headers=headers, data=send_data)
    send_new_msg = format_response_text(resp.text, "Send OTP (new)")
    if '"result":0' not in resp.text.replace(" ", ""):
        return False, f"❌ {smallcaps('Send OTP to new email failed')}.\n{send_new_msg}"

    verify_otp_url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
    verify_otp_data = {"email": new_email, "app_id": "100067", "access_token": access_token, "otp": new_otp}
    resp = requests.post(verify_otp_url, headers=headers, data=verify_otp_data)
    verify_otp_msg = format_response_text(resp.text, "Verify OTP (new)")
    try:
        verifier_token = resp.json().get("verifier_token")
    except:
        verifier_token = None
    if not verifier_token:
        return False, f"❌ {smallcaps('New email OTP verification failed')}.\n{verify_otp_msg}"

    rebind_url = "https://100067.connect.garena.com/game/account_security/bind:create_rebind_request"
    rebind_data = {"identity_token": identity_token, "email": new_email,
                   "app_id": "100067", "verifier_token": verifier_token,
                   "access_token": access_token}
    resp = requests.post(rebind_url, headers=headers, data=rebind_data)
    rebind_msg = format_response_text(resp.text, "Rebind Request")
    return True, f"✅ {smallcaps('Change bind completed')}.\n{verify_msg}\n{send_new_msg}\n{verify_otp_msg}\n{rebind_msg}"

def cancel_bind_request(access_token):
    url = "https://100067.connect.garena.com/game/account_security/bind:cancel_request"
    headers = {
        "User-Agent": "GarenaMSDK/4.0.30",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    data = {"app_id": "100067", "access_token": access_token}
    response = requests.post(url, headers=headers, data=data)
    return format_response_text(response.text, "Cancel Request")

def eat_to_access_token(eat_input):
    eat_token = None
    if "http" in eat_input or "?" in eat_input:
        parsed_url = urllib.parse.urlparse(eat_input)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if 'eat' in query_params:
            eat_token = query_params['eat'][0]
    else:
        eat_token = eat_input.strip()
    if not eat_token:
        return False, f"❌ {smallcaps('Could not find an EAT token')} in your input.", None

    api_url = f"https://api-otrss.garena.com/support/callback/?access_token={eat_token}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36"
    }
    try:
        response = requests.get(api_url, headers=headers, allow_redirects=True, timeout=15)
        parsed = urllib.parse.urlparse(response.url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'access_token' in params:
            access_token = params['access_token'][0]
            account_id = params.get('account_id', ['Unknown'])[0]
            nickname = urllib.parse.unquote(params.get('nickname', ['Unknown'])[0])
            region = params.get('region', ['Unknown'])[0]
            msg = (
                f"✅ {smallcaps('Conversion successful')}!\n"
                f"{label_value('Nickname', nickname)}\n"
                f"{label_value('Account ID', account_id)}\n"
                f"{label_value('Region', region)}\n"
                f"{smallcaps('Access Token')}:\n{access_token}"
            )
            return True, msg, access_token
        else:
            return False, f"❌ {smallcaps('Access token not found')}. {smallcaps('Token might be expired or invalid.')}", None
    except Exception as e:
        return False, f"❌ {smallcaps('Error')}: {smallcaps(str(e))}", None

def revoke_access_token(access_token):
    api_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    nickname = "Unknown"
    account_id = "Unknown"
    region = "Unknown"
    is_valid = False
    try:
        res = requests.get(api_url, headers=headers, allow_redirects=True, timeout=15)
        parsed = urllib.parse.urlparse(res.url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'access_token' in params:
            is_valid = True
            nickname = urllib.parse.unquote(params.get('nickname', ['Unknown'])[0])
            account_id = params.get('account_id', ['Unknown'])[0]
            region = params.get('region', ['Unknown'])[0]
    except:
        pass
    if not is_valid:
        return f"❌ {smallcaps('Token is already invalid, expired, or revoked')}!"

    refresh_token = "1380dcb63ab3a077dc05bdf0b25ba4497c403a5b4eae96d7203010eafa6c83a8"
    logout_url = f"https://100067.connect.garena.com/oauth/logout?access_token={access_token}&refresh_token={refresh_token}"
    try:
        logout_res = requests.get(logout_url, headers=headers, timeout=15)
        if logout_res.status_code == 200 and "error" not in logout_res.text:
            return (
                f"✅ {smallcaps('Token revoked successfully')}!\n"
                f"{label_value('Nickname', nickname)}\n"
                f"{label_value('Account ID', account_id)}\n"
                f"{label_value('Region', region)}\n"
                f"{smallcaps('Status')}: {smallcaps('Logged out & revoked')}"
            )
        else:
            return f"❌ {smallcaps('Failed to revoke token')}! {smallcaps('Server responded with an error.')}"
    except Exception as e:
        return f"❌ {smallcaps('Error')}: {smallcaps(str(e))}"

# ------------- Protobuf / Login History functions -------------
AeSkEy = b'Yg&tc%DEuh6%Zc^8'
AeSiV  = b'6oyZDr22E3ychjM%'

PLATFORM_MAP = {
    3: "Facebook", 4: "Guest", 5: "VK",
    6: "Huawei", 8: "Google", 11: "X (Twitter)", 13: "AppleId",
}

def enc(d):
    return AES.new(AeSkEy, AES.MODE_CBC, AeSiV).encrypt(pad(d, 16))

def dec(d):
    return unpad(AES.new(AeSkEy, AES.MODE_CBC, AeSiV).decrypt(d), 16)

def build_majorlogin(tok, open_id, p_type):
    m = mLpB.MajorLogin()
    m.event_time = str(datetime.now())[:-7]
    m.game_name = "free fire"
    m.platform_id = p_type
    m.client_version = "1.120.1"
    m.system_software = "Android OS 9 / API-28"
    m.system_hardware = "Handheld"
    m.telecom_operator = "Verizon"
    m.network_type = "WIFI"
    m.screen_width = 1920
    m.screen_height = 1080
    m.screen_dpi = "280"
    m.processor_details = "ARM64 FP ASIMD AES VMH | 2865 | 4"
    m.memory = 3003
    m.gpu_renderer = "Adreno (TM) 640"
    m.gpu_version = "OpenGL ES 3.1 v1.46"
    m.unique_device_id = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    m.client_ip = "223.191.51.89"
    m.language = "en"
    m.open_id = open_id
    m.open_id_type = str(p_type)
    m.device_type = "Handheld"
    m.access_token = tok
    m.platform_sdk_id = 1
    m.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    m.login_by = 3
    m.channel_type = 3
    m.cpu_type = 2
    m.cpu_architecture = "64"
    m.client_version_code = "2019118695"
    m.login_open_id_type = p_type
    m.origin_platform_type = str(p_type)
    m.primary_platform_type = str(p_type)
    return enc(m.SerializeToString())

def read_varint(data, offset):
    res = 0; shift = 0
    while True:
        if offset >= len(data):
            break
        b = data[offset]; offset += 1
        res |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, offset

def parse_record(data):
    rec = {}; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0:
            val, offset = read_varint(data, offset)
            if f == 1:
                rec['ts'] = val
            elif f == 2:
                rec['ram'] = val
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 3:
                rec['dev'] = val.decode(errors='ignore')
            elif f == 4:
                rec['arch'] = val.decode(errors='ignore')
        else:
            break
    return rec

def parse_history_protobuf(data):
    records = []; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0:
            val, offset = read_varint(data, offset)
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 1:
                records.append(parse_record(val))
        else:
            break
    return records

def get_login_history(token):
    jwt_token = None
    if token.startswith("ey") and "." in token:
        jwt_token = token
    else:
        open_id = None
        try:
            r = requests.get(f"https://100067.connect.garena.com/oauth/token/inspect?token={token}",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
            open_id = r.get("open_id")
        except:
            pass
        if not open_id:
            try:
                uid_headers = {"access-token": token, "user-agent": "Mozilla/5.0"}
                uid_res = requests.get("https://prod-api.reward.ff.garena.com/redemption/api/auth/inspect_token/",
                                       headers=uid_headers, verify=False, timeout=5).json()
                uid = uid_res.get("uid")
                if uid:
                    openid_res = requests.post("https://topup.pk/api/auth/player_id_login",
                                               json={"app_id": 100067, "login_id": str(uid)},
                                               verify=False, timeout=5).json()
                    open_id = openid_res.get("open_id")
            except:
                pass
        if not open_id:
            return f"❌ {smallcaps('Failed to extract Open ID')}. {smallcaps('Token is likely invalid or expired.')}"

        platforms = [8, 3, 4, 6]
        for p_type in platforms:
            pl = build_majorlogin(token, open_id, p_type)
            try:
                headers = {
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; SM-S908E Build/TP1A.220624.014)",
                    "Connection": "Keep-Alive",
                    "Accept-Encoding": "gzip",
                    "Content-Type": "application/octet-stream",
                    "Expect": "100-continue",
                    "X-GA": "v1 1",
                    "X-Unity-Version": "2018.4.11f1",
                    "ReleaseVersion": "OB54"
                }
                x = requests.post("https://loginbp.ggpolarbear.com/MajorLogin", headers=headers,
                                  data=pl, timeout=10, verify=False)
                if x.status_code == 200:
                    res = mLrPb.MajorLoginRes()
                    try:
                        res.ParseFromString(dec(x.content))
                    except:
                        res.ParseFromString(x.content)
                    if res.token:
                        jwt_token = res.token
                        break
            except:
                continue
        if not jwt_token:
            return f"❌ {smallcaps('MajorLogin failed')} across all platforms. {smallcaps('Token might be blocked.')}"

    try:
        payload_b64 = jwt_token.split('.')[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
        name = urllib.parse.unquote(decoded.get("nickname", "Unknown"))
        uid = decoded.get("account_id", "Unknown")
        region = decoded.get("lock_region", "Unknown")
        p_id = decoded.get("external_type", 0)
        platform = PLATFORM_MAP.get(p_id, f"Unknown ({p_id})")
        info_lines = [
            smallcaps("👤 Player Info"),
            label_value("Account Name", name),
            label_value("Account ID", uid),
            label_value("Platform", platform),
            label_value("Region", region)
        ]
    except:
        info_lines = []

    hH = {
        "Expect": "100-continue",
        "Authorization": f"Bearer {jwt_token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB54",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; G011A Build/PI)",
        "Host": "client.ind.freefiremobile.com",
        "Connection": "close"
    }
    try:
        r = requests.post("https://client.ind.freefiremobile.com/GetLoginHistory",
                          headers=hH, data=enc(b""), timeout=15, verify=False)
        if r.status_code != 200:
            return f"❌ {smallcaps('History Request Failed')}: HTTP {r.status_code}"
        try:
            d = dec(r.content)
        except:
            d = r.content
        records = parse_history_protobuf(d)
        history_lines = [smallcaps("📜 Login History")]
        if not records:
            history_lines.append(smallcaps("No login history records found."))
        else:
            for i, rec in enumerate(records, 1):
                ts_raw = rec.get('ts', 0)
                try:
                    date_str = datetime.fromtimestamp(ts_raw).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date_str = "Invalid Format"
                dev = rec.get('dev', 'Unknown Device')
                arch = rec.get('arch', 'Unknown Architecture')
                ram = rec.get('ram', 0)
                history_lines.append(
                    f"{smallcaps(f'Record #{i}')}\n"
                    f"{label_value('Timestamp', ts_raw)}\n"
                    f"{label_value('Last Login', date_str)}\n"
                    f"{label_value('Device', dev)}\n"
                    f"{label_value('Architecture', arch)}\n"
                    f"{label_value('RAM', f'{ram} MB')}"
                )
        return "\n".join(info_lines + [""] + history_lines)
    except Exception as e:
        return f"❌ {smallcaps('Error fetching history')}: {smallcaps(str(e))}"

def check_Bɪɴᴅ_accounts(access_token):
    url = "https://100067.connect.garena.com/bind/app/platform/info/get"
    params = {"access_token": access_token}
    headers = {
        "User-Agent": "GarenaMSDK/4.0.19P9(Redmi Note 5 ;Android 9;en;US;)",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip"
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"❌ {smallcaps('Failed to fetch data')} (HTTP {response.status_code})"
        d = response.json()
        Bɪɴᴅed = d.get("Bɪɴᴅed_accounts", [])
        available = d.get("available_platforms", [])
        PLATFORM_MAP = {
            1: "Garena", 3: "Facebook", 4: "Guest", 5: "VK",
            6: "Huawei", 7: "Apple", 8: "Google", 10: "GameCenter / Line",
            11: "X (Twitter)", 13: "Apple ID", 28: "Line", 35: "TikTok"
        }
        lines = [smallcaps("🔗 Platform Bind Information")]
        lines.append(smallcaps("Bɪɴᴅ Accounts:"))
        if not Bɪɴᴅed:
            lines.append(smallcaps("• No third‑party platforms are currently Bɪɴᴅ."))
        else:
            for p_id in Bɪɴᴅed:
                p_name = PLATFORM_MAP.get(p_id, f"Unknown ({p_id})")
                lines.append(f"• {smallcaps(p_name)}")
        lines.append("")
        lines.append(smallcaps("Available Platforms:"))
        if not available:
            lines.append(smallcaps("• None"))
        else:
            for p_id in available:
                p_name = PLATFORM_MAP.get(p_id, f"Unknown ({p_id})")
                lines.append(f"• {smallcaps(p_name)}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ {smallcaps('Error')}: {smallcaps(str(e))}"

# ----------------------------------------------------------------------
# Telegram Bot Handlers – all prompts and results are small‑caps
# ----------------------------------------------------------------------
(TOKEN_INPUT, EMAIL_INPUT, OTP_INPUT, SECURITY_INPUT,
 CHANGE_METHOD, OLD_CODE, NEW_EMAIL, NEW_OTP,
 UNBIND_METHOD, UNBIND_CODE,
 EAT_INPUT) = range(11)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Build the 2‑column keyboard from the JSON command list
    buttons = []
    for i in range(0, len(COMMANDS), 2):
        row = []
        row.append(InlineKeyboardButton(COMMANDS[i]["text"], callback_data=COMMANDS[i]["callback_data"]))
        if i+1 < len(COMMANDS):
            row.append(InlineKeyboardButton(COMMANDS[i+1]["text"], callback_data=COMMANDS[i+1]["callback_data"]))
        buttons.append(row)
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        smallcaps("🤖 Garena Bind Tool Bot\nChoose an option:"),
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_bind_info":
        await query.edit_message_text(smallcaps("Please send your Access Token:"))
        context.user_data['next_action'] = 'bind_info'
        return TOKEN_INPUT
    elif data == "bind_email":
        await query.edit_message_text(smallcaps("Please send your Access Token:"))
        context.user_data['next_action'] = 'bind_email'
        return TOKEN_INPUT
    elif data == "unbind_email":
        keyboard = [
            [InlineKeyboardButton(smallcaps("🔑 OTP"), callback_data="unbind_otp")],
            [InlineKeyboardButton(smallcaps("🔐 Security Code"), callback_data="unbind_sec")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            smallcaps("Choose unbind method:"),
            reply_markup=reply_markup
        )
        return UNBIND_METHOD
    elif data == "unbind_otp":
        context.user_data['unbind_method'] = 1
        await query.edit_message_text(smallcaps("Send your Access Token:"))
        context.user_data['next_action'] = 'unbind_email'
        return TOKEN_INPUT
    elif data == "unbind_sec":
        context.user_data['unbind_method'] = 2
        await query.edit_message_text(smallcaps("Send your Access Token:"))
        context.user_data['next_action'] = 'unbind_email'
        return TOKEN_INPUT
    elif data == "change_bind_email":
        keyboard = [
            [InlineKeyboardButton(smallcaps("🔑 OTP"), callback_data="change_otp")],
            [InlineKeyboardButton(smallcaps("🔐 Security Code"), callback_data="change_sec")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            smallcaps("Choose change method:"),
            reply_markup=reply_markup
        )
        return CHANGE_METHOD
    elif data == "change_otp":
        context.user_data['change_method'] = 1
        await query.edit_message_text(smallcaps("Send your Access Token:"))
        context.user_data['next_action'] = 'change_bind'
        return TOKEN_INPUT
    elif data == "change_sec":
        context.user_data['change_method'] = 2
        await query.edit_message_text(smallcaps("Send your Access Token:"))
        context.user_data['next_action'] = 'change_bind'
        return TOKEN_INPUT
    elif data == "cancel_bind_request":
        await query.edit_message_text(smallcaps("Send your Access Token to cancel pending bind request:"))
        context.user_data['next_action'] = 'cancel_bind'
        return TOKEN_INPUT
    elif data == "eat_access_token":
        await query.edit_message_text(smallcaps("Send the EAT token (or full EAT URL):"))
        context.user_data['next_action'] = 'eat_to_token'
        return EAT_INPUT
    elif data == "revoke_access_token":
        await query.edit_message_text(smallcaps("Send the Access Token you wish to revoke:"))
        context.user_data['next_action'] = 'revoke_token'
        return TOKEN_INPUT
    elif data == "get_login_history":
        await query.edit_message_text(smallcaps("Send your Access Token (or Game JWT token):"))
        context.user_data['next_action'] = 'login_history'
        return TOKEN_INPUT
    elif data == "check_Bɪɴᴅ_accounts":
        await query.edit_message_text(smallcaps("Send your Access Token:"))
        context.user_data['next_action'] = 'Bɪɴᴅ_accounts'
        return TOKEN_INPUT
    elif data == "owner_details":
        owner_text = (
            "👨‍💻 Dᴇᴠᴇʟᴏᴘᴇʀ\n"
            "\n"
            "├─ 🕷️ Nᴀᴍᴇ : Dɢ Dʀɪғᴛ\n"
            "├─ 📩 Tᴇʟᴇɢʀᴀᴍ : @DG_DRIFT\n"
            "├─ 📢 Cʜᴀɴɴᴇʟ : @DGDRIFT\n"
            "├─ 🛡️ Vᴇʀsɪᴏɴ : v2.0 • Pʀᴇᴍɪᴜᴍ Eᴅɪᴛɪᴏɴ\n"
            "└─ 💬 Sᴜᴘᴘᴏʀᴛ : @DGDRIFT"
        )
        await query.edit_message_text(owner_text)
        return ConversationHandler.END
    else:
        await query.edit_message_text(smallcaps("Unknown option."))
        return ConversationHandler.END

async def token_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = update.message.text.strip()
    if not token:
        await update.message.reply_text(smallcaps("❌ Token cannot be empty. Please try again or /cancel."))
        return TOKEN_INPUT

    action = context.user_data.get('next_action')
    if action == 'bind_info':
        result = check_bind_info(token)
        await update.message.reply_text(result)
        return ConversationHandler.END
    elif action == 'bind_email':
        context.user_data['access_token'] = token
        await update.message.reply_text(smallcaps("Now send the email address you want to bind:"))
        return EMAIL_INPUT
    elif action == 'unbind_email':
        context.user_data['access_token'] = token
        method = context.user_data.get('unbind_method')
        if method == 1:
            await update.message.reply_text(smallcaps("Send the OTP received on your current email:"))
            return UNBIND_CODE
        else:
            await update.message.reply_text(smallcaps("Send your 6‑digit Security Code:"))
            return UNBIND_CODE
    elif action == 'change_bind':
        context.user_data['access_token'] = token
        method = context.user_data.get('change_method')
        if method == 1:
            await update.message.reply_text(smallcaps("Send the OTP received on your current email:"))
            return OLD_CODE
        else:
            await update.message.reply_text(smallcaps("Send your 6‑digit Security Code:"))
            return OLD_CODE
    elif action == 'cancel_bind':
        result = cancel_bind_request(token)
        await update.message.reply_text(result)
        return ConversationHandler.END
    elif action == 'revoke_token':
        result = revoke_access_token(token)
        await update.message.reply_text(result)
        return ConversationHandler.END
    elif action == 'login_history':
        result = get_login_history(token)
        await update.message.reply_text(result)
        return ConversationHandler.END
    elif action == 'Bɪɴᴅ_accounts':
        result = check_Bɪɴᴅ_accounts(token)
        await update.message.reply_text(result)
        return ConversationHandler.END
    elif action == 'eat_to_token':
        await update.message.reply_text(smallcaps("Please use the EAT option from the main menu."))
        return ConversationHandler.END
    else:
        await update.message.reply_text(smallcaps("Unexpected action. Please start over with /start."))
        return ConversationHandler.END

async def email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if not email:
        await update.message.reply_text(smallcaps("Email cannot be empty. Please send a valid email."))
        return EMAIL_INPUT
    context.user_data['email'] = email
    await update.message.reply_text(smallcaps("Now send the OTP received on that email:"))
    return OTP_INPUT

async def otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    if not otp:
        await update.message.reply_text(smallcaps("OTP cannot be empty. Please send the OTP code."))
        return OTP_INPUT
    context.user_data['otp'] = otp
    await update.message.reply_text(smallcaps("Now set a 6‑digit Security Code (for future unbind/change):"))
    return SECURITY_INPUT

async def security_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sec = update.message.text.strip()
    if len(sec) != 6 or not sec.isdigit():
        await update.message.reply_text(smallcaps("Security code must be exactly 6 digits. Please try again."))
        return SECURITY_INPUT
    access_token = context.user_data.get('access_token')
    email = context.user_data.get('email')
    otp = context.user_data.get('otp')
    success, msg = bind_email_flow(access_token, email, otp, sec)
    await update.message.reply_text(msg)
    for key in ['access_token', 'email', 'otp']:
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def unbind_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if not code:
        await update.message.reply_text(smallcaps("Code cannot be empty. Please send the required code."))
        return UNBIND_CODE
    method = context.user_data.get('unbind_method')
    access_token = context.user_data.get('access_token')
    success, msg = unbind_email_flow(access_token, method, code)
    await update.message.reply_text(msg)
    context.user_data.pop('access_token', None)
    context.user_data.pop('unbind_method', None)
    return ConversationHandler.END

async def old_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if not code:
        await update.message.reply_text(smallcaps("Code cannot be empty. Please send the required code."))
        return OLD_CODE
    context.user_data['old_code'] = code
    await update.message.reply_text(smallcaps("Now send the new email address:"))
    return NEW_EMAIL

async def new_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_email = update.message.text.strip()
    if not new_email:
        await update.message.reply_text(smallcaps("Email cannot be empty. Please send a valid email."))
        return NEW_EMAIL
    context.user_data['new_email'] = new_email
    await update.message.reply_text(smallcaps("Now send the OTP received on that new email:"))
    return NEW_OTP

async def new_otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_otp = update.message.text.strip()
    if not new_otp:
        await update.message.reply_text(smallcaps("OTP cannot be empty. Please send the OTP code."))
        return NEW_OTP
    access_token = context.user_data.get('access_token')
    method = context.user_data.get('change_method')
    old_code = context.user_data.get('old_code')
    new_email = context.user_data.get('new_email')
    success, msg = change_bind_flow(access_token, method, old_code, new_email, new_otp)
    await update.message.reply_text(msg)
    for key in ['access_token', 'change_method', 'old_code', 'new_email']:
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def eat_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eat_input_text = update.message.text.strip()
    if not eat_input_text:
        await update.message.reply_text(smallcaps("Input cannot be empty. Please send EAT token or URL."))
        return EAT_INPUT
    success, msg, token = eat_to_access_token(eat_input_text)
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(smallcaps("Operation cancelled. Use /start to begin again."))
    context.user_data.clear()
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        smallcaps("🤖 Garena Bind Tool Bot\nUse /start to see the menu.\nSend /cancel to abort.")
    )

# ----------------------------------------------------------------------
# Main bot setup
# ----------------------------------------------------------------------
def main():
    # The token is already defined at the top as BOT_TOKEN
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler, pattern="^(check_bind_info|bind_email|unbind_email|change_bind_email|cancel_bind_request|eat_access_token|revoke_access_token|get_login_history|check_Bɪɴᴅ_accounts|owner_details|unbind_otp|unbind_sec|change_otp|change_sec)$")
        ],
        states={
            TOKEN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, token_input)],
            EMAIL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_input)],
            OTP_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)],
            SECURITY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, security_input)],
            UNBIND_METHOD: [CallbackQueryHandler(button_handler, pattern="^(unbind_otp|unbind_sec)$")],
            UNBIND_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, unbind_code_input)],
            CHANGE_METHOD: [CallbackQueryHandler(button_handler, pattern="^(change_otp|change_sec)$")],
            OLD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, old_code_input)],
            NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_email_input)],
            NEW_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_otp_input)],
            EAT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, eat_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()