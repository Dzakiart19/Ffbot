import os
import json
import time
import uuid
import random
import threading
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import requests
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

MONGODB_URI = os.environ.get("MONGODB_URI", "")
JWT_SECRET  = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required but not set")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI environment variable is required but not set")

client      = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
try:
    client.admin.command("ping")
except Exception as e:
    raise RuntimeError(f"Cannot connect to MongoDB: {e}")
db          = client.get_database("kiosgamer")
users_col   = db["users"]
orders_col  = db["orders"]
guests_col  = db["guests"]

users_col.create_index("username", unique=True)
users_col.create_index("email",    unique=True)

# ─── Lazy-import garena module ─────────────────────────────────────────────
try:
    from garena.like_api  import send_like_real
    from garena.guest_gen import bulk_create_guests, create_guest_account
    from garena.token_manager import token_manager
    GARENA_OK = True
except Exception as e:
    print(f"[WARN] Garena module import failed: {e}")
    GARENA_OK = False


# ─── JWT helpers ────────────────────────────────────────────────────────────
def make_token(user_id: str) -> str:
    return jwt.encode(
        {"sub": str(user_id),
         "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
        JWT_SECRET, algorithm="HS256"
    )

def verify_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"]).get("sub")
    except Exception:
        return None

def get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    uid = verify_token(auth[7:])
    return users_col.find_one({"_id": uid}) if uid else None

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(user, *args, **kwargs)
    return wrapper

def require_admin(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        if user.get("role") != "admin":
            return jsonify({"error": "Admin only"}), 403
        return f(user, *args, **kwargs)
    return wrapper


# ─── Progress demo ──────────────────────────────────────────────────────────
_FAKE_NAMES = [
    "RestuJepang","RadenST!!","REBORN丨SRG","JoyyJepang","^PISCES☂️Ra",
    "L.Yamal19","KONAN丨萬多","SKY丨DEVIL","ZeroPoint","DARKSIDE丨FF",
    "NightKiller","ShadowBoss","EliteSniper","GhostRider","StormBreaker"
]

def generate_demo_progress():
    entries = []
    for _ in range(6):
        before  = random.randint(10000, 150000)
        added   = random.randint(500, 5000)
        total   = before + added
        target  = random.randint(total + 1000, total + 30000)
        proses  = random.randint(1000, target - total + 500)
        tersisa = max(0, target - before - proses)
        entries.append({
            "name":    random.choice(_FAKE_NAMES),
            "uid":     str(random.randint(10000000, 999999999)),
            "before":  before,
            "added":   added,
            "total":   total,
            "proses":  proses,
            "target":  target,
            "tersisa": tersisa,
        })
    return entries


# ─── Routes: pages ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ─── Routes: auth ───────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "Username, email, dan password wajib diisi"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username minimal 3 karakter"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password minimal 6 karakter"}), 400

    hashed  = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())

    try:
        users_col.insert_one({
            "_id":              user_id,
            "username":         username,
            "email":            email,
            "password":         hashed,
            "role":             "user",
            "created_at":       datetime.now(timezone.utc).isoformat(),
            "likes_sent":       0,
            "lobbies_created":  0,
        })
    except DuplicateKeyError:
        return jsonify({"error": "Username atau email sudah terdaftar"}), 409

    token = make_token(user_id)
    return jsonify({
        "message": "Registrasi berhasil",
        "token":   token,
        "user":    {"id": user_id, "username": username, "email": email},
    }), 201


@app.route("/api/login", methods=["POST"])
def login():
    data       = request.get_json(silent=True) or {}
    identifier = data.get("username", data.get("email", "")).strip()
    password   = data.get("password", "")

    if not identifier or not password:
        return jsonify({"error": "Username/email dan password wajib diisi"}), 400

    user = users_col.find_one({"$or": [{"username": identifier}, {"email": identifier.lower()}]})
    if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Username/email atau password salah"}), 401

    token = make_token(user["_id"])
    return jsonify({
        "message": "Login berhasil",
        "token":   token,
        "user": {
            "id":               user["_id"],
            "username":         user["username"],
            "email":            user["email"],
            "role":             user.get("role", "user"),
            "likes_sent":       user.get("likes_sent", 0),
            "lobbies_created":  user.get("lobbies_created", 0),
        },
    })


@app.route("/api/me", methods=["GET"])
@require_auth
def me(user):
    return jsonify({
        "id":               user["_id"],
        "username":         user["username"],
        "email":            user["email"],
        "role":             user.get("role", "user"),
        "likes_sent":       user.get("likes_sent", 0),
        "lobbies_created":  user.get("lobbies_created", 0),
        "created_at":       user.get("created_at"),
    })


# ─── Routes: like ───────────────────────────────────────────────────────────
@app.route("/api/like", methods=["POST"])
@require_auth
def send_like(user):
    data   = request.get_json(silent=True) or {}
    uid    = str(data.get("uid", "")).strip()
    region = str(data.get("region", "ID")).strip().upper()

    if not uid or not uid.isdigit():
        return jsonify({"error": "UID harus berupa angka"}), 400
    if region not in ["ID","SG","IND","BR","EU","EUROPE","US"]:
        region = "ID"
    if region == "EU":
        region = "EUROPE"

    if GARENA_OK:
        result = send_like_real(uid, region)
    else:
        result = {
            "success":      True,
            "demo":         True,
            "player_name":  f"Player#{uid[-4:]}",
            "likes_added":  random.randint(50, 200),
            "likes_before": random.randint(10000, 100000),
            "likes_after":  random.randint(10000, 100000),
            "accounts_used": 0,
        }

    if not result.get("success"):
        return jsonify(result), 400

    order_id = str(uuid.uuid4())[:8].upper()
    orders_col.insert_one({
        "_id":         order_id,
        "type":        "like",
        "uid":         uid,
        "region":      region,
        "user_id":     user["_id"],
        "likes_added": result.get("likes_added", 0),
        "likes_before":result.get("likes_before", 0),
        "likes_after": result.get("likes_after", 0),
        "player_name": result.get("player_name",""),
        "demo":        result.get("demo", False),
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "status":      "completed",
    })
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"likes_sent": result.get("likes_added", 0)}})

    return jsonify({
        "success":       result.get("success"),
        "demo":          result.get("demo", False),
        "order_id":      order_id,
        "uid":           uid,
        "region":        region,
        "player_name":   result.get("player_name",""),
        "likes_before":  result.get("likes_before", 0),
        "likes_after":   result.get("likes_after", 0),
        "likes_added":   result.get("likes_added", 0),
        "accounts_used": result.get("accounts_used", 0),
        "message":       "Like berhasil dikirim!" if result.get("success") else result.get("error","Gagal"),
    })


# ─── Routes: lobby ──────────────────────────────────────────────────────────
REGION_BOT_CONFIG = {
    "ID":  "config/id_config.json",
    "SG":  "config/sg_config.json",
    "IND": "config/ind_config.json",
    "BR":  "config/br_config.json",
    "EU":  "config/europe_config.json",
}

def _get_bot_uids(region, limit=4):
    cfg_path = REGION_BOT_CONFIG.get(region, "config/id_config.json")
    try:
        with open(cfg_path) as f:
            accounts = json.load(f)
        return [str(a["uid"]) for a in accounts[:limit] if a.get("uid")]
    except Exception:
        return []

@app.route("/api/lobby", methods=["POST"])
@require_auth
def create_lobby(user):
    data   = request.get_json(silent=True) or {}
    uid    = str(data.get("uid", "")).strip()
    region = str(data.get("region", "ID")).strip().upper()

    if not uid or not uid.isdigit():
        return jsonify({"error": "UID harus berupa angka"}), 400

    bot_uids = _get_bot_uids(region, limit=4)
    if not bot_uids:
        return jsonify({"error": f"Tidak ada bot tersedia untuk region {region}"}), 503

    order_id = str(uuid.uuid4())[:8].upper()
    orders_col.insert_one({
        "_id":        order_id,
        "type":       "lobby",
        "uid":        uid,
        "region":     region,
        "user_id":    user["_id"],
        "bot_uids":   bot_uids,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":     "pending",
    })
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"lobbies_created": 1}})

    return jsonify({
        "success":  True,
        "order_id": order_id,
        "uid":      uid,
        "region":   region,
        "bot_uids": bot_uids,
        "message":  "Tambahkan akun bot ini sebagai teman di FF, lalu masuk ke lobby mereka.",
    })


@app.route("/api/lobby/confirm", methods=["POST"])
@require_auth
def confirm_lobby(user):
    data     = request.get_json(silent=True) or {}
    order_id = str(data.get("order_id", "")).strip().upper()
    if not order_id:
        return jsonify({"error": "order_id diperlukan"}), 400

    order = orders_col.find_one({"_id": order_id, "user_id": user["_id"], "type": "lobby"})
    if not order:
        return jsonify({"error": "Order tidak ditemukan"}), 404

    orders_col.update_one(
        {"_id": order_id},
        {"$set": {"status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()}}
    )
    return jsonify({"success": True, "message": "Konfirmasi diterima! Bot akan segera mengundang kamu ke lobby."})


# ─── Routes: bio ────────────────────────────────────────────────────────────
@app.route("/api/bio", methods=["POST"])
@require_auth
def update_bio(user):
    data   = request.get_json(silent=True) or {}
    uid    = str(data.get("uid", "")).strip()
    bio    = str(data.get("bio", "")).strip()
    region = str(data.get("region", "ID")).strip().upper()

    if not uid or not uid.isdigit():
        return jsonify({"error": "UID harus berupa angka"}), 400
    if not bio:
        return jsonify({"error": "Bio tidak boleh kosong"}), 400
    if len(bio) > 60:
        return jsonify({"error": "Bio maksimal 60 karakter"}), 400

    if not GARENA_OK:
        return jsonify({"error": "Garena module tidak tersedia. Fitur Update Bio membutuhkan koneksi ke server Garena."}), 503

    return jsonify({
        "success": False,
        "error":   "Fitur Update Bio belum tersedia — endpoint Garena untuk bio update masih dalam pengembangan.",
    }), 501


# ─── Routes: progress ───────────────────────────────────────────────────────
def _build_live_entries(db_orders):
    entries = []
    for o in db_orders:
        before  = o.get("likes_before", 0)
        added   = o.get("likes_added", 0)
        after   = o.get("likes_after", before + added)
        target  = after + random.randint(500, 5000)
        proses  = added
        tersisa = max(0, target - after)
        entries.append({
            "name":    o.get("player_name") or f"User#{str(o['uid'])[-4:]}",
            "uid":     o["uid"],
            "before":  before,
            "added":   added,
            "total":   after,
            "proses":  proses,
            "target":  target,
            "tersisa": tersisa,
        })
    return entries


@app.route("/api/progress", methods=["GET"])
def get_progress():
    db_orders = list(orders_col.find(
        {"type": "like", "status": "completed"},
        limit=10,
        sort=[("created_at", -1)]
    ))

    if db_orders:
        return jsonify({"entries": _build_live_entries(db_orders), "source": "live"})

    return jsonify({"entries": generate_demo_progress(), "source": "demo"})


@app.route("/api/progress/stream")
def progress_stream():
    def generate():
        while True:
            db_orders = list(orders_col.find(
                {"type": "like", "status": "completed"},
                limit=10,
                sort=[("created_at", -1)]
            ))
            if db_orders:
                entries = _build_live_entries(db_orders)
                source  = "live"
            else:
                entries = generate_demo_progress()
                source  = "demo"
            yield f"data: {json.dumps({'entries': entries, 'source': source, 'ts': int(time.time())})}\n\n"
            time.sleep(5)
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ─── Routes: stats ──────────────────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def stats():
    accounts_info = {}
    if GARENA_OK:
        for reg in ["ID","SG","IND","BR","EUROPE"]:
            accounts_info[reg] = token_manager.count_accounts(reg)

    return jsonify({
        "total_users":    users_col.count_documents({}),
        "total_orders":   orders_col.count_documents({}),
        "total_likes":    orders_col.count_documents({"type": "like"}),
        "total_lobbies":  orders_col.count_documents({"type": "lobby"}),
        "guest_accounts": accounts_info,
        "garena_module":  GARENA_OK,
    })


# ─── Routes: admin – guest account management ───────────────────────────────
@app.route("/api/admin/add-account", methods=["POST"])
@require_admin
def admin_add_account(user):
    data     = request.get_json(silent=True) or {}
    region   = data.get("region", "ID").upper()
    acc_uid  = str(data.get("uid", "")).strip()
    password = str(data.get("password", "")).strip()

    if not acc_uid or not password:
        return jsonify({"error": "uid dan password wajib diisi"}), 400

    if not GARENA_OK:
        return jsonify({"error": "Garena module tidak tersedia"}), 500

    saved = token_manager.add_account(region, acc_uid, password)
    return jsonify({
        "success": saved,
        "message": f"Akun {acc_uid} ditambahkan ke region {region}" if saved else "UID sudah ada",
    })


@app.route("/api/admin/auto-generate", methods=["POST"])
@require_admin
def admin_auto_generate(user):
    data   = request.get_json(silent=True) or {}
    region = data.get("region", "ID").upper()
    try:
        count = min(int(data.get("count", 5)), 20)
    except (ValueError, TypeError):
        return jsonify({"error": "count harus berupa angka"}), 400

    if not GARENA_OK:
        return jsonify({"error": "Garena module tidak tersedia"}), 500

    def run_bg():
        bulk_create_guests(region, count)

    threading.Thread(target=run_bg, daemon=True).start()

    return jsonify({
        "message": f"Generating {count} guest accounts untuk region {region} di background...",
        "note":    "Cek /api/stats setelah beberapa menit untuk melihat hasilnya",
    })


@app.route("/api/admin/accounts", methods=["GET"])
@require_admin
def admin_accounts(user):
    if not GARENA_OK:
        return jsonify({"error": "Garena module tidak tersedia"}), 500

    result = {}
    for reg in ["ID","SG","IND","BR","EUROPE"]:
        result[reg] = token_manager.count_accounts(reg)

    return jsonify({"accounts": result})


@app.route("/api/admin/make-admin", methods=["POST"])
@require_admin
def make_admin(user):
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    target   = users_col.find_one({"username": username})
    if not target:
        return jsonify({"error": "User tidak ditemukan"}), 404
    users_col.update_one({"username": username}, {"$set": {"role": "admin"}})
    return jsonify({"message": f"{username} sekarang admin"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
