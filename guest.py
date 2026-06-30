import os
import sys
import json
import time
import random
import string
import hashlib
import threading
import subprocess
import base64
import codecs
import re
from datetime import datetime
from urllib.parse import unquote

try:
    from cfonts import render
    CFONTS = True
except:
    CFONTS = False
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-cfonts'])
    from cfonts import render

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ReGiOn = "ID"
NiCkNaMe = "Vaibhav"
PaSsWoRd = "Vaibhav"
ToTaL = 100
ThReAdS = 50
GhOsT = False
AuToAcT = True

aEsKeY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
aEsIv = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])
cLiEnTsEcReT = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

rEgIoNlAnG = {
    "ME": "ar", "IND": "hi", "ID": "id", "VN": "vi", "TH": "th",
    "BD": "bn", "PK": "ur", "TW": "zh", "EUROPE": "fr", "RU": "ru",
    "NA": "na", "SAC": "es", "BR": "pt", "SG": "ms", "US": "us"
}
rEgIoNlIsT = ["IND", "ID", "TH", "ME", "EUROPE", "VN", "BD", "PK", "TW", "RU", "NA", "SAC", "BR", "SG", "US"]

nIcKXoR = b'1e5898ccb8dfdd921f9bdea848768b64a201'

cOnSeCuTiVe = 0
pRiNtLoCk = threading.Lock()
iPlOcK = threading.Lock()

INDIAN_CARRIERS = [
    "Jio", "Airtel", "Vodafone Idea", "BSNL", "MTNL", 
    "Reliance Jio", "Bharti Airtel", "Vi", "Idea Cellular"
]

INDIAN_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", 
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow", 
    "Kanpur", "Nagpur", "Indore", "Bhopal", "Visakhapatnam",
    "Patna", "Vadodara", "Surat", "Rajkot", "Chandigarh"
]

INDIAN_DEVICES = [
    "Asus ASUS_AI2401_A", "Samsung SM-G998B", "OnePlus 9 Pro", 
    "Xiaomi Mi 11", "Google Pixel 6", "Realme GT", "Vivo X70 Pro",
    "Oppo Find X3", "Motorola Edge 20", "Samsung SM-M515F",
    "Samsung SM-A525F", "Redmi Note 10", "OnePlus Nord 2"
]

tor_process = None
IP_ROTATION_INTERVAL = 15
ACCOUNT_COUNTER_FOR_IP_ROTATION = 0

def start_tor():
    global tor_process
    try:
        subprocess.run(['pkill', '-9', 'tor'], capture_output=True, check=False)
        time.sleep(0.5)
        tor_process = subprocess.Popen(
            ['tor'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        for i in range(10):
            time.sleep(0.5)
            result = subprocess.run(['pgrep', '-x', 'tor'], capture_output=True)
            if result.returncode == 0:
                return True
        return False
    except:
        return False

def renew_tor_ip():
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(('127.0.0.1', 9051))
        s.send(b'AUTHENTICATE ""\r\n')
        s.send(b'SIGNAL NEWNYM\r\n')
        s.send(b'QUIT\r\n')
        s.close()
        time.sleep(1)
        return True
    except:
        return False

def get_proxies():
    return {
        'http': 'socks5h://127.0.0.1:9050',
        'https': 'socks5h://127.0.0.1:9050'
    }

session_pool = []
SESSION_POOL_SIZE = ThReAdS

def init_session_pool():
    global session_pool
    tor_available = subprocess.run(['which', 'tor'], capture_output=True).returncode == 0
    for _ in range(SESSION_POOL_SIZE):
        session = requests.Session()
        if tor_available:
            session.proxies.update(get_proxies())
        session.verify = False
        session.timeout = 10
        session_pool.append(session)

def get_pool_session():
    return random.choice(session_pool)

def FF(value):
    out = []
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)

def GayRena(field_num, value):
    if isinstance(value, int):
        tag = (field_num << 3) | 0
        return FF(tag) + FF(value)
    elif isinstance(value, str):
        data = value.encode('utf-8')
        tag = (field_num << 3) | 2
        return FF(tag) + FF(len(data)) + data
    elif isinstance(value, bytes):
        tag = (field_num << 3) | 2
        return FF(tag) + FF(len(value)) + value
    elif isinstance(value, dict):
        sub_payload = xPro(value)
        tag = (field_num << 3) | 2
        return FF(tag) + FF(len(sub_payload)) + sub_payload
    else:
        raise TypeError(f"Unsupported type for field {field_num}: {type(value)}")

def xPro(fields_dict):
    payload = b''
    for key, value in fields_dict.items():
        field_num = int(key)
        if isinstance(value, list):
            if value and all(isinstance(v, int) for v in value):
                packed = b''.join(FF(v) for v in value)
                tag = (field_num << 3) | 2
                payload += FF(tag) + FF(len(packed)) + packed
            else:
                for elem in value:
                    payload += GayRena(field_num, elem)
        else:
            payload += GayRena(field_num, value)
    return payload

def Noob(packet):
    cipher = AES.new(aEsKeY, AES.MODE_CBC, aEsIv)
    pad_len = 16 - (len(packet) % 16)
    if pad_len == 0:
        pad_len = 16
    plaintext_padded = packet + bytes([pad_len]) * pad_len
    return cipher.encrypt(plaintext_padded)

def Pro(data):
    from google.protobuf.internal.decoder import _DecodeVarint, _DecodeVarint32
    pos = 0
    length = len(data)
    fields = {}
    while pos < length:
        key, pos = _DecodeVarint(data, pos)
        field_num = key >> 3
        wire_type = key & 7
        if wire_type == 0:
            value, pos = _DecodeVarint(data, pos)
        elif wire_type == 2:
            size, pos = _DecodeVarint32(data, pos)
            raw = data[pos:pos+size]
            pos += size
            try:
                value = Pro(raw)
            except:
                try:
                    value = raw.decode('utf-8')
                except:
                    value = raw.hex()
        elif wire_type == 5:
            value = int.from_bytes(data[pos:pos+4], "little")
            pos += 4
        elif wire_type == 1:
            value = int.from_bytes(data[pos:pos+8], "little")
            pos += 8
        else:
            raise Exception(f"Unsupported wire type: {wire_type}")
        if field_num in fields:
            if not isinstance(fields[field_num], list):
                fields[field_num] = [fields[field_num]]
            fields[field_num].append(value)
        else:
            fields[field_num] = value
    return fields

def RoFl(session, password):
    url = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
    payload = {"app_id": 100067, "client_type": 2, "password": password, "source": 2}
    json_body = json.dumps(payload, separators=(',', ':'))
    data_to_sign = cLiEnTsEcReT + json_body
    signature = hashlib.sha256(data_to_sign.encode()).hexdigest()
    headers = {
        "User-Agent": "GarenaMSDK/4.0.39(FRL-AN00a ;Android 10;nu;HK;)",
        "Authorization": f"Signature {signature}",
        "Content-Type": "application/json; charset=utf-8"
    }
    resp = session.post(url, data=json_body, headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("code") == 0:
            return str(data["data"]["uid"])
        else:
            raise Exception(f"Register failed: {data}")
    else:
        resp.raise_for_status()
        raise Exception(f"Unexpected response: {resp.text}")

def yEet(length=6, chars=string.ascii_uppercase + string.digits + "-_."):
    return ''.join(random.choice(chars) for _ in range(length))

def pWe():
    try:
        return requests.get('https://api.ipify.org', timeout=3).text
    except:
        return "0.0.0.0"

def sUs():
    return "GarenaMSDK/4.0.39(FRL-AN00a ;Android 10;nu;HK;)"

def bRuH():
    return "okhttp/3.12.1"

def fInE(original):
    keystream = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,
                 0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30]
    encoded = ""
    for i in range(len(original)):
        orig_byte = ord(original[i])
        key_byte = keystream[i % len(keystream)]
        result_byte = orig_byte ^ key_byte
        encoded += chr(result_byte)
    return encoded

def yAy(s):
    return ''.join(c if 32 <= ord(c) <= 126 else f'\\u{ord(c):04x}' for c in s)

def nOp(nick_b64):
    if not nick_b64:
        return ""
    try:
        decoded_bytes = base64.b64decode(nick_b64)
        key_len = len(nIcKXoR)
        xored = bytes([decoded_bytes[i] ^ nIcKXoR[i % key_len] for i in range(len(decoded_bytes))])
        return xored.decode('utf-8', errors='ignore')
    except:
        return nick_b64

def wOw(func, session, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(session, *args, **kwargs)
        except:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5)
    return None

def hAhA(session, password):
    return RoFl(session, password)

def lMaO(session, uid, password):
    url = "https://100067.connect.garena.com/api/v2/oauth/guest/token:grant"
    payload = {
        "client_id":100067, "client_secret":cLiEnTsEcReT, "client_type":2,
        "password":password, "response_type":"token", "uid":uid
    }
    headers = {"User-Agent": sUs(), "Content-Type": "application/json"}
    resp = session.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"Token grant failed: {data}")
    return data["data"]["access_token"], data["data"]["open_id"]

def gG(session, name, access_token, open_id, region, is_ghost=False):
    global cOnSeCuTiVe
    url = "https://loginbp.ggpolarbear.com/MajorRegister"
    host = "loginbp.ggpolarbear.com"
    exp_digits = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    num = random.randint(1,99999)
    exp = ''.join(exp_digits[d] for d in f"{num:05d}")
    name = name[:7] + exp
    lang_code = "pt" if is_ghost else rEgIoNlAnG.get(region.upper(), "en")
    encoded_result = fInE(open_id)
    field_unicode = yAy(encoded_result)
    field_bytes = codecs.decode(field_unicode, 'unicode_escape').encode('latin1')
    fields_dict = {
        "1": name, "2": access_token, "3": open_id,
        "5": 102000007, "6": 4, "7": 1, "13": 1,
        "14": field_bytes, "15": lang_code, "16": 2
    }
    plaintext = xPro(fields_dict)
    encrypted_payload = Noob(plaintext)
    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer", "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded", "Expect": "100-continue",
        "Host": host, "ReleaseVersion": "OB54",
        "User-Agent": bRuH(), "X-GA": "v1 1", "X-Unity-Version": "2018.4."
    }
    try:
        resp = session.post(url, headers=headers, data=encrypted_payload, timeout=15)
        resp.raise_for_status()
        with iPlOcK:
            cOnSeCuTiVe = 0
        return Pro(resp.content)
    except Exception as e:
        with iPlOcK:
            cOnSeCuTiVe += 1
            if cOnSeCuTiVe >= 10:
                renew_tor_ip()
                time.sleep(1)
                cOnSeCuTiVe = 0
        raise

def nIcE(session, access_token, open_id, region, lang_code):
    url = "https://loginbp.ggpolarbear.com/MajorLogin"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = pWe()
    if region.upper() == "IND":
        device_model = random.choice(INDIAN_DEVICES)
        carrier = random.choice(INDIAN_CARRIERS)
        city = random.choice(INDIAN_CITIES)
    else:
        device_model = "Asus ASUS_AI2401_A"
        carrier = "GrameenPhone"
        city = "Dhaka"
    gpu = "Adreno (TM) 640"

    def qT(n):
        out = []
        while True:
            b = n & 0x7F
            n >>= 7
            if n: b |= 0x80
            out.append(b)
            if not n: break
        return bytes(out)

    def zZ(f, v):
        return qT((f << 3) | 0) + qT(v)

    def xX(f, v):
        data = v.encode() if isinstance(v, str) else v
        return qT((f << 3) | 2) + qT(len(data)) + data

    fields = {
        3: now_str,
        4: "free fire",
        5: 1,
        7: "1.126.5",
        8: "Android OS 5.1.1 / API-22 (LMY48Z/rel.se.infra.20220128.171448)",
        9: "Handheld",
        10: carrier,
        11: "WIFI",
        17: gpu,
        18: "OpenGL ES 3.0",
        19: "Google|4645e530-e790-4be2-ae7c-6f64d1259603",
        20: ip,
        21: lang_code,
        22: open_id,
        23: 4,
        24: "Handheld",
        25: device_model,
        26: region.upper(),
        29: access_token,
        33: carrier,
        34: "WIFI",
        37: "7428b253defc164018c604a1ebbfebdf",
        73: "/data/app/com.dts.freefireth-1/lib/arm",
        75: "H4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-1/base.apk",
        76: 2,
        78: 2,
        79: 2,
        83: "OpenGLES2",
        85: city,
        87: "android",
        88: "KqsHTywQqGHMgPbDY9P2mhkxXj/beObk/TFNpmgaucQwxyLu9hA478WEQCV0Mgaz9UivYUPpKNwPzgZhvDhSsUDMAFY=",
        90: '{"cur_rate":null,"support_etc2":false}',
        97: 1,
        98: 1,
        99: "4",
        100: "4"
    }

    packet = b''
    for f, v in fields.items():
        if isinstance(v, int): 
            packet += zZ(f, v)
        elif isinstance(v, str): 
            packet += xX(f, v)
        elif isinstance(v, bytes): 
            packet += xX(f, v)

    encrypted = Noob(packet)
    headers = {
        "Accept-Encoding": "gzip", 
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded", 
        "Expect": "100-continue",
        "ReleaseVersion": "OB54", 
        "User-Agent": bRuH(),
        "X-GA": "v1 1", 
        "X-Unity-Version": "2018.4."
    }
    resp = session.post(url, headers=headers, data=encrypted, timeout=15)
    resp.raise_for_status()
    decoded = Pro(resp.content)
    jwt_token = decoded.get(8)
    if isinstance(jwt_token, list):
        jwt_token = jwt_token[0] if jwt_token else None
    return decoded, jwt_token

def dUdE(session, region_code, jwt_token):
    url = "https://loginbp.ggpolarbear.com/ChooseRegion"
    if region_code.upper() == "CIS":
        region_code = "ru"
    else:
        region_code = region_code.upper()
    fields_dict = {"1": region_code}
    plaintext = xPro(fields_dict)
    encrypted_payload = Noob(plaintext)
    headers = {
        "Accept-Encoding": "gzip", "Authorization": f"Bearer {jwt_token}",
        "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue", "ReleaseVersion": "OB54",
        "User-Agent": bRuH(), "X-GA": "v1 1", "X-Unity-Version": "2018.4."
    }
    resp = session.post(url, headers=headers, data=encrypted_payload, timeout=10)
    return resp.status_code == 200

def bYe(session, jwt_token, client_url):
    url = f"https://{client_url}/GetLoginData"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = pWe()
    device_model = random.choice(INDIAN_DEVICES)
    carrier = random.choice(INDIAN_CARRIERS)
    city = random.choice(INDIAN_CITIES)
    gpu = "Adreno (TM) 640"
    open_id = "24adf2d6806cf61bd95d4cd3b57a0bd9"

    def qT(n):
        out = []
        while True:
            b = n & 0x7F
            n >>= 7
            if n: b |= 0x80
            out.append(b)
            if not n: break
        return bytes(out)

    def zZ(f, v):
        return qT((f << 3) | 0) + qT(v)

    def xX(f, v):
        data = v.encode() if isinstance(v, str) else v
        return qT((f << 3) | 2) + qT(len(data)) + data

    fields = {
        3: now_str,
        4: "free fire",
        5: 1,
        7: "1.126.5",
        8: "Android OS 5.1.1 / API-22 (LMY48Z/rel.se.infra.20220128.171448)",
        9: "Handheld",
        10: carrier,
        11: "WIFI",
        17: gpu,
        18: "OpenGL ES 3.0",
        19: "Google|4645e530-e790-4be2-ae7c-6f64d1259603",
        20: ip,
        21: "en",
        22: open_id,
        23: 4,
        24: "Handheld",
        25: device_model,
        26: "IND",
        29: jwt_token,
        33: carrier,
        34: "WIFI",
        37: "7428b253defc164018c604a1ebbfebdf",
        73: "/data/app/com.dts.freefireth-1/lib/arm",
        75: "H4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-1/base.apk",
        83: "OpenGLES2",
        85: city,
        87: "android",
        88: "KqsHT8nWdkA7u/m7k8vg2H5FgrCGa4lfww3nHBGRHRPwDFV4LyCj8sT23O/P6K06qC3MOLZRThwWwul+g2goHwtQJy8=",
        90: '{"cur_rate":null,"support_etc2":false}'
    }

    packet = b''
    for f, v in fields.items():
        if isinstance(v, int): 
            packet += zZ(f, v)
        elif isinstance(v, str): 
            packet += xX(f, v)
        elif isinstance(v, bytes): 
            packet += xX(f, v)

    encrypted_payload = Noob(packet)

    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 12)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/x-www-form-urlencoded",
        'Authorization': f"Bearer {jwt_token}",
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB54"
    }

    try:
        resp = session.post(url, headers=headers, data=encrypted_payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

def hElLo(jwt_token):
    try:
        parts = jwt_token.split('.')
        if len(parts) != 3:
            return None, None
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        lock_region = data.get("lock_region") or data.get("noti_region")
        raw_nick = data.get("nickname")
        if raw_nick:
            nickname = nOp(raw_nick)
        else:
            nickname = ""
        return lock_region, nickname
    except:
        return None, None

class AcCoUnTcReAtOr:
    def __init__(self, region, nickname_prefix, password_prefix, password_mode, auto_activate, total_target, ghost=False):
        self.region = region
        self.nickname_prefix = nickname_prefix[:7]
        self.password_prefix = password_prefix.upper()
        self.password_mode = password_mode
        self.auto_activate = auto_activate
        self.total_target = total_target
        self.ghost = ghost
        self.results = []
        self.lock = threading.Lock()
        self.created_count = 0
        self.fail_counter = 0
        self.ip_blocked = False
        self.stop = False
        self.results_lock = threading.Lock()
        self.saved_uids = set()
        self.file_lock = threading.Lock()

    def load_existing_uids(self):
        if self.ghost:
            folder = "GEN/GHOST"
        else:
            folder = f"GEN/{self.region}"
        txt_path = os.path.join(folder, f"Accounts-{self.region}.txt")
        try:
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = re.search(r'UiD = (\d+)', line)
                        if match:
                            self.saved_uids.add(match.group(1))
        except:
            pass

    def gEnPaSs(self):
        r1 = yEet(6)
        r2 = yEet(6)
        plain = f"{self.password_prefix}_{r1}-VAIBHAV{r2}"
        return plain, plain

    def save_single_account(self, acc):
        if self.ghost:
            folder = "GEN/GHOST"
        else:
            folder = f"GEN/{self.region}"
        try:
            os.makedirs(folder, exist_ok=True)
        except:
            folder = "."
        txt_path = os.path.join(folder, f"Accounts-{self.region}.txt")

        with self.file_lock:
            try:
                uid = acc.get('uid', '')
                existing_uids = set()
                if os.path.exists(txt_path):
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            match = re.search(r'UiD = (\d+)', line)
                            if match:
                                existing_uids.add(match.group(1))

                if uid not in existing_uids:
                    with open(txt_path, 'a', encoding='utf-8') as f:
                        line = f"BOT = {acc.get('game_uid', '')} | UiD = {uid} | PassWord = {acc.get('password', '')} | NamE = {acc.get('nickname', '')} | ReGioN = {acc.get('region', '')}\n"
                        f.write(line)
                    with self.results_lock:
                        self.saved_uids.add(uid)
                    return True
            except:
                pass
        return False

    def cReAtE(self, thread_id):
        if self.stop or self.ip_blocked:
            return None
        session = get_pool_session()
        try:
            store_pass, api_pass = self.gEnPaSs()
            uid = wOw(hAhA, session, api_pass)

            with self.results_lock:
                if uid in self.saved_uids:
                    return None

            access_token, open_id = wOw(lMaO, session, uid, api_pass)
            reg_resp = wOw(gG, session, self.nickname_prefix, access_token, open_id, self.region, self.ghost)
            account_id = reg_resp.get(3)
            if not account_id:
                raise Exception("No account_id")
            account_id = str(account_id)
            lang_code = rEgIoNlAnG.get(self.region, "en") if not self.ghost else "pt"
            login_resp, jwt_token = wOw(nIcE, session, access_token, open_id, self.region, lang_code)
            if not jwt_token:
                raise Exception("No JWT")
            lock_region, nickname = hElLo(jwt_token)
            if not nickname:
                nickname = self.nickname_prefix
            need_lock = False
            final_jwt = jwt_token
            client_url = None
            if not self.ghost:
                if lock_region and lock_region not in (None, 'None', '..', ''):
                    if lock_region != self.region.upper():
                        need_lock = True
                else:
                    need_lock = True
                if need_lock:
                    dUdE(session, self.region, jwt_token)
                    login_resp2, jwt_token2 = wOw(nIcE, session, access_token, open_id, self.region, lang_code)
                    if jwt_token2:
                        final_jwt = jwt_token2
                        lock_region2, nickname2 = hElLo(jwt_token2)
                        if nickname2:
                            nickname = nickname2
                        lock_region = lock_region2
                    else:
                        lock_region = None
                last_resp = login_resp2 if need_lock and 'login_resp2' in locals() else login_resp
                client_url_raw = last_resp.get(10)
                if isinstance(client_url_raw, str):
                    client_url = client_url_raw
                elif isinstance(client_url_raw, list):
                    client_url = client_url_raw[0] if client_url_raw else None
                if client_url and client_url.startswith("https://"):
                    client_url = client_url[8:]
                if not client_url:
                    if self.region.upper() == "IND":
                        client_url = "client.ind.freefiremobile.com"
                    elif self.region.upper() in ["BR","US","NA","SAC"]:
                        client_url = "client.us.freefiremobile.com"
                    else:
                        client_url = "clientbp.ggpolarbear.com"
            else:
                client_url = "clientbp.ggpolarbear.com"
                lock_region = "GHOST"
            activated = False
            if self.auto_activate and final_jwt and client_url and not self.ghost:
                activated = wOw(bYe, session, final_jwt, client_url)
            final_region = lock_region if lock_region and not self.ghost else "GHOST"
            stored_password = store_pass

            acc = {
                "nickname": nickname,
                "game_uid": account_id,
                "region": final_region,
                "uid": str(uid),
                "password": stored_password,
                "activated": activated
            }

            with self.results_lock:
                self.saved_uids.add(uid)

            return acc
        except:
            return None

    def wOrKeR(self, thread_id):
        global ACCOUNT_COUNTER_FOR_IP_ROTATION
        threading.current_thread().name = f"T{thread_id}"
        while not self.stop:
            if self.created_count >= self.total_target:
                break
            with iPlOcK:
                ACCOUNT_COUNTER_FOR_IP_ROTATION += 1
                if ACCOUNT_COUNTER_FOR_IP_ROTATION >= IP_ROTATION_INTERVAL:
                    ACCOUNT_COUNTER_FOR_IP_ROTATION = 0
                    renew_tor_ip()
                    time.sleep(0.5)
            acc = self.cReAtE(thread_id)
            if acc:
                with self.lock:
                    self.created_count += 1
                self.save_single_account(acc)
                # ── Simpan juga ke config/ supaya like_api bisa pakai ──
                self._save_to_config(acc)
                output_line = f"BOT = {acc.get('game_uid', '')} | UiD = {acc.get('uid', '')} | PassWord = {acc.get('password', '')} | NamE = {acc.get('nickname', '')} | ReGioN = {acc.get('region', '')}"
                print(output_line)
            else:
                time.sleep(0.1)
        if self.created_count >= self.total_target:
            self.stop = True

    def _save_to_config(self, acc):
        """Simpan akun ke config/{region}_config.json untuk like_api (thread-safe)."""
        import json
        region = str(acc.get("region", self.region)).upper()
        config_map = {
            "ID": "config/id_config.json", "IND": "config/ind_config.json",
            "SG": "config/sg_config.json", "EUROPE": "config/europe_config.json",
            "BR": "config/br_config.json", "US": "config/br_config.json",
        }
        cfg_path = config_map.get(region, f"config/{region.lower()}_config.json")

        # Gunakan file_lock (per-instance) supaya worker paralel tidak corrupt JSON
        with self.file_lock:
            try:
                accounts = []
                if os.path.exists(cfg_path):
                    with open(cfg_path) as f:
                        accounts = json.load(f)
                uid = str(acc.get("uid", ""))
                if not any(str(a.get("uid")) == uid for a in accounts):
                    accounts.append({
                        "uid":         uid,
                        "password":    acc.get("password", ""),
                        "game_uid":    acc.get("game_uid", ""),
                        "lock_region": region,
                    })
                    os.makedirs("config", exist_ok=True)
                    with open(cfg_path, 'w') as f:
                        json.dump(accounts, f, indent=2)
            except Exception:
                pass  # silent — jangan interrupt generate loop

    def rUn(self):
        self.load_existing_uids()
        tor_available = subprocess.run(['which', 'tor'], capture_output=True).returncode == 0
        if tor_available:
            start_tor()
            time.sleep(1)
        else:
            print("[INFO] Tor tidak tersedia, menggunakan koneksi langsung.")
        init_session_pool()

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=ThReAdS) as executor:
            futures = []
            for i in range(ThReAdS):
                futures.append(executor.submit(self.wOrKeR, i+1))

            while self.created_count < self.total_target and not self.stop:
                time.sleep(0.5)

            self.stop = True
            for future in futures:
                try:
                    future.cancel()
                except:
                    pass

        # ── Aktivasi massal semua akun yang baru dibuat ─────────────────────
        self._activate_all_accounts()

    def _activate_all_accounts(self):
        """Aktivasi massal semua akun dari GEN file secara paralel."""
        import json
        from concurrent.futures import ThreadPoolExecutor

        folder = "GEN/GHOST" if self.ghost else f"GEN/{self.region}"
        txt_path = os.path.join(folder, f"Accounts-{self.region}.txt")
        if not os.path.exists(txt_path):
            return

        import re
        accounts = []
        with open(txt_path) as f:
            for line in f:
                uid_m = re.search(r'UiD = (\d+)', line)
                pw_m  = re.search(r'PassWord = (\S+)', line)
                if uid_m and pw_m:
                    accounts.append({"uid": uid_m.group(1), "password": pw_m.group(1)})

        if not accounts:
            return

        print(f"\n[AKTIVASI] Memulai aktivasi massal {len(accounts)} akun region {self.region}...")

        region    = self.region
        activated = {"ok": 0, "fail": 0}
        lock      = threading.Lock()

        def _activate_one(acc):
            uid = acc["uid"]
            pwd = acc["password"]
            try:
                # Import get_jwt untuk ambil JWT fresh
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    from garena.get_jwt import create_jwt
                    jwt, lock_reg, _ = loop.run_until_complete(
                        create_jwt(uid, pwd, region=region)
                    )
                finally:
                    loop.close()

                if not jwt:
                    with lock: activated["fail"] += 1
                    return False

                effective = lock_reg if lock_reg and lock_reg not in ("0","None","") else region
                from garena.guest_gen import _get_login_data, _new_session
                session = _new_session()
                ok = False
                for _ in range(3):  # 3 rounds keepalive
                    if _get_login_data(session, jwt, effective):
                        ok = True
                    time.sleep(1)

                with lock:
                    if ok: activated["ok"] += 1
                    else:  activated["fail"] += 1
                print(f"  [ACT] {uid} → {'✓' if ok else '✗'}")
                return ok
            except Exception as e:
                with lock: activated["fail"] += 1
                return False

        workers = min(ThReAdS, len(accounts))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_activate_one, accounts))

        print(f"[AKTIVASI] Selesai: {activated['ok']} berhasil, {activated['fail']} gagal")

def bAnNeR():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" * 1)
    print("""
   ██╗   ██╗ █████╗ ██╗██████╗ ██╗  ██╗ █████╗ ██╗   ██╗
   ██║   ██║██╔══██╗██║██╔══██╗██║  ██║██╔══██╗██║   ██║
   ██║   ██║███████║██║██████╔╝███████║███████║██║   ██║
   ╚██╗ ██╔╝██╔══██║██║██╔══██╗██╔══██║██╔══██║██║   ██║
    ╚████╔╝ ██║  ██║██║██████╔╝██║  ██║██║  ██║╚██████╔╝
     ╚═══╝  ╚═╝  ╚═╝╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝
    """)

def mAiN():
    bAnNeR()
    creator = AcCoUnTcReAtOr(ReGiOn, NiCkNaMe, PaSsWoRd, "plain", AuToAcT, ToTaL, GhOsT)
    creator.rUn()
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    mAiN()