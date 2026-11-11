# ═══════════════════════════════════════════════════════════════════
#   👑 M1NX PREMIUM SYSTEM — FULL WORKING CODE
#   Owner    : M1NXGAMINGVIP
#   Telegram : @M1NXGAMINGVIP
#   Bio      : @M1NXGAMINGVIP
#   Prefix   : M1NX_
# ═══════════════════════════════════════════════════════════════════

import os, sys, json, time, uuid, random, string, hashlib, hmac, socket, threading, asyncio, sqlite3
from datetime import datetime, timezone
from functools import wraps

# ═══════════════════════════ CONFIG ═══════════════════════════
OWNER_NAME        = "M1NXGAMINGVIP"
OWNER_TG          = "@M1NXGAMINGVIP"
BRAND_NAME        = "M1NX PREMIUM"
CUSTOM_PREFIX     = "M1NX_"
CUSTOM_BIO        = "[b][c][FFD700]TELEGRAM DM : @M1NXGAMINGVIP"

ADMIN_USER        = os.environ.get("ADMIN_USER", "m1nx")
ADMIN_PASS        = os.environ.get("ADMIN_PASS", "m1nx123")
SECRET_KEY        = os.environ.get("SECRET_KEY", "m1nx-premium-secret-2024")
TG_BOT_TOKEN      = os.environ.get("TG_BOT_TOKEN", "")     # Render env এ বসাবেন
TG_ADMIN_ID       = os.environ.get("TG_ADMIN_ID", "")      # আপনার Telegram numeric ID

DB_PATH           = os.environ.get("DB_PATH", "data/m1nx.db")
DOWNLOAD_DIR      = os.environ.get("DOWNLOAD_DIR", "data/downloads")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════ DNS FIX (GARENA) ═══════════════════════
_ORIG_GETADDRINFO = socket.getaddrinfo
def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "100067.connect.garena.com":
        ip = random.choice(["43.205.19.48", "34.124.234.158"])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    return _ORIG_GETADDRINFO(host, port, family, type, proto, flags)
socket.getaddrinfo = _patched_getaddrinfo

import requests, urllib3
urllib3.disable_warnings()
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from flask import Flask, request, jsonify, render_template_string, redirect, session, send_from_directory, flash
from flask_socketio import SocketIO

app = Flask(__name__)
app.secret_key = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ═══════════════════════════ DATABASE ═══════════════════════════
class DB:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self._init()
    def _conn(self):
        c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c
    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS devices(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT UNIQUE, name TEXT, platform TEXT,
                    ip TEXT, ua TEXT, first_seen TEXT, last_seen TEXT,
                    total_generated INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ACTIVE',
                    current_action TEXT DEFAULT 'Idle',
                    region TEXT DEFAULT 'BD'
                );
                CREATE TABLE IF NOT EXISTS accounts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT, uid TEXT, password TEXT, account_id TEXT,
                    name TEXT, open_id TEXT, access_token TEXT, region TEXT,
                    online_status TEXT, bio_status TEXT, created_at TEXT, credit TEXT
                );
                CREATE TABLE IF NOT EXISTS logs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT, level TEXT, message TEXT, ts TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT, region TEXT, target INTEGER,
                    success INTEGER DEFAULT 0, fail INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'RUNNING', started TEXT, finished TEXT
                );
            """)
    def now(self): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def reg_device(self, did, name, plat, ip, ua):
        with self.lock, self._conn() as c:
            if c.execute("SELECT id FROM devices WHERE device_id=?", (did,)).fetchone():
                c.execute("UPDATE devices SET last_seen=?,ip=?,ua=? WHERE device_id=?", (self.now(), ip, ua, did))
            else:
                c.execute("INSERT INTO devices(device_id,name,platform,ip,ua,first_seen,last_seen) VALUES(?,?,?,?,?,?,?)",
                          (did, name, plat, ip, ua, self.now(), self.now()))
    def update_device_action(self, did, action, region=None):
        with self.lock, self._conn() as c:
            if region:
                c.execute("UPDATE devices SET current_action=?,region=?,last_seen=? WHERE device_id=?",
                          (action, region, self.now(), did))
            else:
                c.execute("UPDATE devices SET current_action=?,last_seen=? WHERE device_id=?", (action, self.now(), did))
    def devices(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()]
    def device(self, did):
        with self._conn() as c:
            r = c.execute("SELECT * FROM devices WHERE device_id=?", (did,)).fetchone()
            return dict(r) if r else None
    def inc_gen(self, did):
        with self.lock, self._conn() as c:
            c.execute("UPDATE devices SET total_generated=total_generated+1 WHERE device_id=?", (did,))
    def save_acc(self, a):
        with self.lock, self._conn() as c:
            c.execute("""INSERT INTO accounts(device_id,uid,password,account_id,name,open_id,access_token,region,online_status,bio_status,created_at,credit)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (a.get("device_id"), a.get("uid"), a.get("password"), a.get("account_id"),
                       a.get("name"), a.get("open_id"), a.get("access_token"), a.get("region"),
                       a.get("online_status"), a.get("bio_status"), a.get("created_at"), a.get("credit")))
    def accounts(self, did=None, limit=500, region=None):
        with self._conn() as c:
            q = "SELECT * FROM accounts WHERE 1=1"; p = []
            if did: q += " AND device_id=?"; p.append(did)
            if region: q += " AND region=?"; p.append(region)
            q += " ORDER BY id DESC LIMIT ?"; p.append(limit)
            return [dict(r) for r in c.execute(q, p).fetchall()]
    def add_log(self, did, lvl, msg):
        with self.lock, self._conn() as c:
            c.execute("INSERT INTO logs(device_id,level,message,ts) VALUES(?,?,?,?)", (did, lvl, msg, self.now()))
    def logs(self, did=None, limit=300):
        with self._conn() as c:
            if did:
                rows = c.execute("SELECT * FROM logs WHERE device_id=? ORDER BY id DESC LIMIT ?", (did, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
    def create_job(self, did, region, target):
        with self.lock, self._conn() as c:
            cur = c.execute("INSERT INTO jobs(device_id,region,target,started) VALUES(?,?,?,?)",
                            (did, region, target, self.now()))
            return cur.lastrowid
    def update_job(self, jid, success=None, fail=None, status=None):
        with self.lock, self._conn() as c:
            if success is not None: c.execute("UPDATE jobs SET success=? WHERE id=?", (success, jid))
            if fail is not None: c.execute("UPDATE jobs SET fail=? WHERE id=?", (fail, jid))
            if status: c.execute("UPDATE jobs SET status=?,finished=? WHERE id=?", (status, self.now(), jid))
    def jobs(self, did=None, limit=30):
        with self._conn() as c:
            if did:
                rows = c.execute("SELECT * FROM jobs WHERE device_id=? ORDER BY id DESC LIMIT ?", (did, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
db = DB(DB_PATH)

# ═══════════════════════ DEVICE IDENTIFIER ═══════════════════════
def identify_device(req):
    ua = req.headers.get("User-Agent", "Unknown")
    ip = req.headers.get("X-Forwarded-For", req.remote_addr or "0.0.0.0").split(",")[0].strip()
    fp = hashlib.sha256(f"{ua}|{ip}".encode()).hexdigest()[:16]
    did = f"M1NX-{fp.upper()[:10]}"
    plat = ("Android" if "android" in ua.lower() else
            "iOS" if "iphone" in ua.lower() or "ipad" in ua.lower() else
            "Windows" if "windows" in ua.lower() else
            "macOS" if "mac" in ua.lower() else
            "Linux" if "linux" in ua.lower() else "Unknown")
    name = f"{plat}-{fp[:4].upper()}"
    db.reg_device(did, name, plat, ip, ua)
    return {"device_id": did, "name": name, "platform": plat, "ip": ip, "ua": ua}

# ═══════════════════════ TELEGRAM BOT ═══════════════════════
_tg_last_update = 0
_tg_lock = threading.Lock()

def tg_api(method, **params):
    if not TG_BOT_TOKEN: return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}",
                          json=params, timeout=15)
        return r.json()
    except Exception:
        return None

def tg_send(chat_id, text, markdown=True):
    params = {"chat_id": chat_id, "text": text}
    if markdown: params["parse_mode"] = "Markdown"
    return tg_api("sendMessage", **params)

def tg_send_doc(chat_id, filepath, caption=""):
    if not TG_BOT_TOKEN or not os.path.exists(filepath): return None
    try:
        with open(filepath, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendDocument",
                              data={"chat_id": chat_id, "caption": caption},
                              files={"document": f}, timeout=60)
        return r.json()
    except Exception:
        return None

def tg_help_text():
    return (
        f"*{BRAND_NAME}*\n"
        f"Owner: {OWNER_NAME}\n\n"
        "*Available Commands:*\n"
        "/start - Welcome message\n"
        "/help - Show commands\n"
        "/stats - System statistics\n"
        "/devices - List all devices\n"
        "/accounts - Recent accounts\n"
        "/generate <count> <BD|IND> - Generate accounts\n"
        "/files - Download account files\n"
        "/status - System status\n"
    )

def tg_handle_update(upd):
    try:
        msg = upd.get("message") or upd.get("edited_message")
        if not msg: return
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        user = msg.get("from", {}).get("first_name", "User")
        if not text.startswith("/"): return
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]

        if cmd == "/start":
            tg_send(chat_id,
                f"*Welcome to {BRAND_NAME}*\n\n"
                f"Hello {user}!\n"
                f"Owner: {OWNER_NAME}\n"
                f"Telegram: {OWNER_TG}\n\n"
                f"Use /help to see commands."
            )
        elif cmd == "/help":
            tg_send(chat_id, tg_help_text())
        elif cmd == "/stats":
            devs = db.devices()
            accs = db.accounts(limit=99999)
            txt = (f"*{BRAND_NAME} STATS*\n\n"
                   f"Devices: {len(devs)}\n"
                   f"Accounts: {len(accs)}\n"
                   f"Total Generated: {sum(d['total_generated'] for d in devs)}\n\n"
                   f"Owner: {OWNER_NAME}")
            tg_send(chat_id, txt)
        elif cmd == "/devices":
            devs = db.devices()
            if not devs:
                tg_send(chat_id, "No devices registered yet.")
                return
            txt = f"*Devices ({len(devs)})*\n\n"
            for d in devs[:15]:
                txt += (f"ID: `{d['device_id']}`\n"
                        f"Name: {d['name']} | {d['platform']}\n"
                        f"Action: {d['current_action']}\n"
                        f"Generated: {d['total_generated']}\n"
                        f"Last Seen: {d['last_seen']}\n\n")
            tg_send(chat_id, txt)
        elif cmd == "/accounts":
            accs = db.accounts(limit=10)
            if not accs:
                tg_send(chat_id, "No accounts yet.")
                return
            txt = f"*Recent Accounts (10)*\n\n"
            for a in accs:
                txt += (f"`{a['account_id']}` | {a['name']}\n"
                        f"UID: `{a['uid']}` | {a['region']}\n"
                        f"Device: {a['device_id']}\n\n")
            tg_send(chat_id, txt)
        elif cmd == "/status":
            tg_send(chat_id,
                f"*{BRAND_NAME} STATUS*\n\n"
                f"System: ONLINE\n"
                f"Owner: {OWNER_NAME}\n"
                f"Telegram: {OWNER_TG}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        elif cmd == "/files":
            # Generate files and send
            all_accs = db.accounts(limit=99999)
            if not all_accs:
                tg_send(chat_id, "No accounts to export.")
                return
            path = os.path.join(DOWNLOAD_DIR, "m1nx_all_accounts.txt")
            with open(path, "w", encoding="utf-8") as f:
                for a in all_accs:
                    f.write(f"[{a['region']}] UID:{a['uid']} | ACC:{a['account_id']} | NAME:{a['name']} | PASS:{a['password']} | DEV:{a['device_id']} | {a['created_at']}\n")
            tg_send_doc(chat_id, path, caption=f"All accounts ({len(all_accs)})")
        elif cmd == "/generate":
            if len(parts) < 2:
                tg_send(chat_id, "Usage: /generate <count> <BD|IND>\nExample: /generate 5 BD")
                return
            try:
                count = int(parts[1])
                region = (parts[2] if len(parts) > 2 else "BD").upper()
                if region not in ("BD", "IND"): region = "BD"
                if count <= 0 or count > 50:
                    tg_send(chat_id, "Count must be 1-50")
                    return
            except ValueError:
                tg_send(chat_id, "Invalid count")
                return
            did = f"M1NX-TG-{chat_id}"
            db.reg_device(did, f"Telegram-{user}", "Telegram", "0.0.0.0", "TelegramBot")
            threading.Thread(target=run_generation, args=(did, region, count, chat_id), daemon=True).start()
            tg_send(chat_id, f"Generation started: {count} x {region}\nJob running on device `{did}`\n\nYou will get updates here.")
        else:
            tg_send(chat_id, f"Unknown command. Use /help")
    except Exception as e:
        print(f"[TG] Handle error: {e}")

def tg_poll_loop():
    global _tg_last_update
    if not TG_BOT_TOKEN:
        print("[TG] Bot token not set, skipping Telegram bot")
        return
    print("[TG] Bot polling started")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates",
                             params={"offset": _tg_last_update + 1, "timeout": 30}, timeout=40)
            data = r.json()
            if data.get("ok"):
                for u in data["result"]:
                    _tg_last_update = u["update_id"]
                    tg_handle_update(u)
        except Exception:
            time.sleep(5)

# ═══════════════════════ GARENA ENGINE ═══════════════════════
MSDK_UA = "GarenaMSDK/4.0.42(NX809J ;Android 9;en;US;app 1.134.14 2024010012;)"
HKEY    = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
xK      = b'Yg&tc%DEuh6%Zc^8'
xV      = b'6oyZDr22E3ychjM%'

LOGIN_HOST         = "loginbp.ppmainecoonghj.com"
MAJOR_LOGIN_URL    = f"https://{LOGIN_HOST}/MajorLogin"
BIO_URL            = "https://clientbp.ppmainecoonghj.com/UpdateSocialBasicInfo"
DEFAULT_CLIENT_URL = "https://clientbp.ppmainecoonghj.com"
RELEASE_VERSION    = "OB55"
UNITY_VERSION      = "2018.4.12f1"
CLIENT_VERSION     = "1.134.14"

_PW_STASH = {}
_PROXY_POOL = []
_PROXY_LOCK = threading.Lock()

def fetch_proxies():
    global _PROXY_POOL
    try:
        srcs = ["https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"]
        got = []
        for s in srcs:
            try:
                r = requests.get(s, timeout=3)
                got += [p.strip() for p in r.text.split("\n") if p.strip() and ":" in p]
                if len(got) >= 50: break
            except Exception: pass
        if got:
            with _PROXY_LOCK: _PROXY_POOL = got[:200]
    except Exception: pass

def next_proxy():
    with _PROXY_LOCK:
        if not _PROXY_POOL: return None
        return random.choice(_PROXY_POOL)

_SESS = requests.Session()
_SESS.verify = False
_ad = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
_SESS.mount("https://", _ad); _SESS.mount("http://", _ad)

def _sig(body): return hmac.new(HKEY.encode(), body.encode(), hashlib.sha256).hexdigest()
def _enc(data): return AES.new(xK, AES.MODE_CBC, xV).encrypt(pad(data, 16))

def _varint(n):
    d = []
    while True:
        b = n & 0x7F; n >>= 7
        if n: b |= 0x80
        d.append(b)
        if not n: break
    return bytes(d)

def _proto(fields):
    out = bytearray()
    for f, v in fields.items():
        if isinstance(v, bool):
            out += _varint((f<<3)|0) + _varint(1 if v else 0)
        elif isinstance(v, int):
            out += _varint((f<<3)|0) + _varint(v)
        elif isinstance(v, str):
            b = v.encode(); out += _varint((f<<3)|2) + _varint(len(b)) + b
        elif isinstance(v, bytes):
            out += _varint((f<<3)|2) + _varint(len(v)) + v
        elif isinstance(v, dict):
            n = _proto(v); out += _varint((f<<3)|2) + _varint(len(n)) + n
    return bytes(out)

def _first_varint(data, want):
    off = 0
    while off < len(data):
        key = shift = 0
        while True:
            b = data[off]; off += 1
            key |= (b & 0x7F) << shift
            if not (b & 0x80): break
            shift += 7
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v = shift = 0
            while True:
                b = data[off]; off += 1
                v |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            if fn == want: return v
        elif wt == 2:
            ln = shift = 0
            while True:
                b = data[off]; off += 1
                ln |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            off += ln
        elif wt == 1: off += 8
        elif wt == 5: off += 4
        else: break
    return None

def gen_pw():  return "M1NX-" + "".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=26))
def gen_nick(): return CUSTOM_PREFIX + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def srv_time():
    try:
        r = requests.head("https://www.google.com", timeout=4)
        d = r.headers.get("Date")
        if d:
            dt = datetime.strptime(d, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
            return int(dt.timestamp()), dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception: pass
    return int(time.time()), time.strftime("%Y-%m-%d %H:%M:%S")

def guest_reg(retries=15):
    for i in range(retries):
        try:
            pw = gen_pw()
            body = json.dumps({"app_id":100067,"client_type":2,"password":pw,"source":2}, separators=(',',':'))
            h = {"User-Agent":MSDK_UA,"Authorization":f"Signature {_sig(body)}",
                 "Accept":"application/json","Content-Type":"application/json; charset=utf-8",
                 "Host":"100067.connect.garena.com","Connection":"Keep-Alive"}
            px = None
            if i > 0:
                p = next_proxy()
                if p: px = {"http": f"http://{p}", "https": f"http://{p}"}
            r = requests.post("https://100067.connect.garena.com/api/v2/oauth/guest:register",
                              headers=h, data=body, timeout=4, proxies=px, verify=False)
            if r.status_code == 200:
                j = r.json()
                if j.get("data", {}).get("uid"):
                    uid = str(j["data"]["uid"]); _PW_STASH[uid] = pw
                    return uid, pw
            time.sleep(0.3)
        except Exception: time.sleep(0.2)
    return None, None

def guest_tok(uid, retries=8):
    pw = _PW_STASH.get(str(uid))
    if not pw: return None
    for i in range(retries):
        try:
            body = json.dumps({"client_id":100067,"client_secret":HKEY,"client_type":2,
                               "password":pw,"response_type":"token","uid":int(uid)}, separators=(',',':'))
            h = {"User-Agent":MSDK_UA,"Accept":"application/json",
                 "Content-Type":"application/json; charset=utf-8",
                 "Host":"100067.connect.garena.com","Connection":"Keep-Alive"}
            px = None
            if i > 0:
                p = next_proxy()
                if p: px = {"http": f"http://{p}", "https": f"http://{p}"}
            r = requests.post("https://100067.connect.garena.com/api/v2/oauth/guest/token:grant",
                              headers=h, data=body, timeout=4, proxies=px, verify=False)
            if r.status_code == 200:
                j = r.json().get("data", {})
                if j.get("access_token"):
                    return {"access_token": j["access_token"], "open_id": j.get("open_id","")}
            time.sleep(0.3)
        except Exception: time.sleep(0.2)
    return None

def payload_login(tok, oid, ts_str, region="BD"):
    if region == "IND":
        P = {3:ts_str,4:"free fire",5:1,7:"1.134.14",
             8:"Android OS 14 / API-34",9:"Handheld",10:"airtel",11:"CarrierDataNetwork",
             12:2340,13:1080,14:"295",15:"ARM64 | 2200 | 8",16:5586,17:"Mali-G57 MC2",
             18:"OpenGL ES 3.2",19:"Google|m1nx-ind",20:"27.61.46.111",21:"en",
             22:oid,23:"4",24:"Handheld",25:"samsung SM-A155F",26:"IND",
             29:tok,30:1,41:"airtel",42:"4G",57:"7428b253defc164018c604a1ebbfebdf",
             60:108009,61:3859,62:5023,64:3987,65:108009,66:3987,67:108009,
             70:4,73:3,74:"/data/app/m1nx/lib/arm64",76:3,77:"m1nx|/data/app/m1nx/base.apk",
             78:3,79:2,81:"64",83:"2019121269",85:3,86:"OpenGLES2",
             87:8191,88:4,90:"Coimbatore",91:"TN",92:9570,93:"android",
             94:"KqsHT4XbSZhqerDNUhjbS3DxG/4+I62zQU2tZFJN91kBUICAlZ5yujshLKvjlk/KiShfKfis8EeB1PMhFHIodWPncZC4fCHYF3TcTwNj95aWY/S3",
             95:111207,96:'{"cur_rate":null,"support_etc2":false}',97:1,98:1,99:"4",100:"4",
             104:11921,105:1,
             106:"https://dl-tata.freefireind.in/live/ABHotUpdates/|dff941d41e6e3a9e76f05ed71fdc8d87",
             107:"1.6168622e0868ddbd"}
    else:
        P = {3:ts_str,4:"free fire",5:1,7:"1.134.14",
             8:"Android OS 14 / API-34",9:"Handheld",10:"Grameenphone",11:"CarrierDataNetwork",
             12:1666,13:750,14:"352",15:"ARM64 | 2400 | 8",16:5563,17:"Mali-G57 MC2",
             18:"OpenGL ES 3.2",19:"Google|m1nx-bd",20:"59.152.5.188",21:"en",
             22:oid,23:"8",24:"Handheld",25:"Xiaomi 2312DRAABI",26:"BD",
             29:tok,30:1,41:"Grameenphone",42:"Cellular",57:"7428b253defc164018c604a1ebbfebdf",
             60:109685,61:58294,62:797,63:18000,64:58818,65:109685,66:58818,67:109685,73:2,
             74:"/data/app/m1nx/lib/arm64",76:1,77:"m1nx|/data/app/m1nx/base.apk",
             78:3,79:2,81:"64",83:"2019121229",85:3,86:"OpenGLES2",
             87:4095,88:8,90:"Dhaka",91:"C",92:8043,93:"android",
             94:"KqsHT4XbSZhqerDNUhjbS3DxG/4+I62zQU2tZFJN91kBUICAlZ5yujshLKvjlk/KiShfKfis8EeB1PMhFHIodWPncZC4fCHYF3TcTwNj95aWY/S3",
             95:111207,96:'{"cur_rate":[60,90,120],"support_etc2":false}',97:1,98:1,99:"4",100:"4",
             102:"GQ] e",103:1,104:45174,105:1,
             106:"https://dl-bs.ggpolarbear.com/live/ABHotUpdates/|a4332cb1c1a84e51dd77441e4856ed5a",
             107:"1.9393e7b8e53e8aeb"}
    return _enc(_proto(P))

def major_login(payload, ts, retries=8):
    h = {"User-Agent":"UnityPlayer/2018.4.12f1","Accept":"*/*","Accept-Encoding":"deflate, gzip",
         "X-GA-SV":str(ts),"Authorization":"Bearer ","X-GA":"v1 1",
         "ReleaseVersion":RELEASE_VERSION,
         "Content-Type":"application/x-www-form-urlencoded","X-Unity-Version":"2018.4.12f1"}
    for i in range(retries):
        try:
            px = None
            if i > 0:
                p = next_proxy()
                if p: px = {"http": f"http://{p}", "https": f"http://{p}"}
            r = requests.post(MAJOR_LOGIN_URL, headers=h, data=payload, timeout=5, proxies=px, verify=False)
            if r.status_code in (200, 201) and r.content and len(r.content) > 64:
                return r.content
            time.sleep(0.3)
        except Exception: time.sleep(0.2)
    return None

def parse_login(ml):
    if not ml or len(ml) <= 64: return None
    body = ml[64:] if ml[0] != 0x0a else ml
    f = {}; pos = 0
    while pos < len(body):
        try:
            key = shift = 0
            while True:
                b = body[pos]; pos += 1
                key |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            fn, wt = key >> 3, key & 7
            if wt == 0:
                val = shift = 0
                while True:
                    b = body[pos]; pos += 1
                    val |= (b & 0x7F) << shift
                    if not (b & 0x80): break
                    shift += 7
            elif wt == 2:
                ln = shift = 0
                while True:
                    b = body[pos]; pos += 1
                    ln |= (b & 0x7F) << shift
                    if not (b & 0x80): break
                    shift += 7
                val = body[pos:pos + ln]; pos += ln
            elif wt == 5: val = body[pos:pos+4]; pos += 4
            elif wt == 1: val = body[pos:pos+8]; pos += 8
            else: break
            f.setdefault(fn, []).append(val)
        except Exception: break
    jwt = f.get(8,[None])[0]; url = f.get(10,[None])[0]
    kb = f.get(22,[None])[0]; ivb = f.get(23,[None])[0]
    if not jwt or not isinstance(kb, bytes) or not isinstance(ivb, bytes): return None
    return {"jwt":jwt.decode(), "url":url.decode() if url else DEFAULT_CLIENT_URL, "key":kb, "iv":ivb}

def major_register(oid, tok, nick, ts, retries=8):
    if not nick.startswith(CUSTOM_PREFIX): nick = gen_nick()
    fields = {1:nick,2:tok,3:oid,5:102000007,6:4,7:1,8:4,13:1,14:oid.encode('latin1',errors='ignore'),
              15:"en",16:1,20:CLIENT_VERSION,21:1,22:bytes.fromhex("4747524501010100")}
    body = _enc(_proto(fields))
    h = {"User-Agent":"UnityPlayer/2018.4.12f1","Accept":"*/*","X-GA-SV":str(ts),
         "Authorization":"Bearer","X-GA":"v1 1","ReleaseVersion":RELEASE_VERSION,
         "Content-Type":"application/x-www-form-urlencoded","X-Unity-Version":UNITY_VERSION,
         "Host":LOGIN_HOST,"Connection":"Keep-Alive"}
    for i in range(retries):
        try:
            px = None
            if i > 0:
                p = next_proxy()
                if p: px = {"http": f"http://{p}", "https": f"http://{p}"}
            r = requests.post(f"https://{LOGIN_HOST}/MajorRegister", data=body, headers=h,
                              timeout=4, proxies=px, verify=False)
            if r.status_code == 200:
                aid = _first_varint(r.content, 3)
                if aid: return str(aid)
            time.sleep(0.3)
        except Exception: time.sleep(0.2)
    return None

def upload_bio(jwt, url, retries=3):
    h = {"Expect":"100-continue","X-Unity-Version":"2018.4.11f1","X-GA":"v1 1",
         "ReleaseVersion":RELEASE_VERSION,
         "Content-Type":"application/x-www-form-urlencoded",
         "User-Agent":"Dalvik/2.1.0 (Linux; U; Android 11)",
         "Connection":"Keep-Alive","Accept-Encoding":"gzip",
         "Authorization":f"Bearer {jwt}"}
    body = _enc(_proto({2:17,5:{},6:{},8:CUSTOM_BIO,9:1,11:{},12:{}}))
    for i in range(retries):
        try:
            r = requests.post(f"{url}/UpdateSocialBasicInfo", headers=h, data=body, timeout=10, verify=False)
            if r.status_code == 200: return True
            time.sleep(0.5)
        except Exception: time.sleep(0.3)
    return False

def generate_account(device_id, region="BD"):
    """একটা একাউন্ট তৈরি করে। ব্যর্থ হলে None ফেরত দেয়।"""
    ts, ts_str = srv_time()
    uid, pw = guest_reg()
    if not uid: return None
    tk = guest_tok(uid)
    if not tk: return None
    nick = gen_nick()
    aid = major_register(tk["open_id"], tk["access_token"], nick, ts)
    if not aid: return None
    lp = payload_login(tk["access_token"], tk["open_id"], ts_str, region)
    ml = major_login(lp, ts)
    if not ml: return None
    ad = parse_login(ml)
    if not ad: return None
    url = ad["url"] or DEFAULT_CLIENT_URL
    threading.Thread(target=upload_bio, args=(ad["jwt"], url), daemon=True).start()
    acc = {"device_id":device_id,"uid":uid,"password":pw,"account_id":aid,
           "name":nick,"open_id":tk["open_id"],"access_token":tk["access_token"],
           "region":region,"online_status":"ONLINE",
           "bio_status":"SUCCESS",
           "created_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "credit":"M1NX PREMIUM"}
    db.save_acc(acc)
    db.inc_gen(device_id)
    return acc

def run_generation(device_id, region, count, tg_chat=None):
    """Background generation job — keeps retrying failed accounts."""
    jid = db.create_job(device_id, region, count)
    db.add_log(device_id, "INFO", f"Job #{jid} started: {count} x {region}")
    db.update_device_action(device_id, f"Generating {count} x {region}", region)
    if tg_chat: tg_send(tg_chat, f"Job #{jid} started: {count} x {region}")

    success = 0
    fail = 0
    attempts = 0
    max_attempts = count * 3  # 3x retry budget

    while success < count and attempts < max_attempts:
        attempts += 1
        try:
            db.update_device_action(device_id, f"Creating {success+1}/{count} (attempt {attempts})", region)
            acc = generate_account(device_id, region)
            if acc:
                success += 1
                msg = f"OK {acc['account_id']} | {acc['name']}"
                db.add_log(device_id, "SUCCESS", msg)
                socketio.emit("log", {"level":"SUCCESS","message":msg,"device":device_id,"ts":db.now()})
                socketio.emit("account_created", acc)
                db.update_job(jid, success=success, fail=fail)
                if tg_chat and (success % 3 == 0 or success == count):
                    tg_send(tg_chat, f"Progress: {success}/{count} done")
            else:
                fail += 1
                msg = f"Attempt {attempts} failed (retrying)"
                db.add_log(device_id, "FAIL", msg)
                socketio.emit("log", {"level":"FAIL","message":msg,"device":device_id,"ts":db.now()})
                db.update_job(jid, success=success, fail=fail)
                time.sleep(0.5)
        except Exception as e:
            fail += 1
            db.add_log(device_id, "FAIL", f"Error: {e}")

    status = "COMPLETED" if success >= count else "PARTIAL"
    db.update_job(jid, status=status)
    db.update_device_action(device_id, "Idle", region)
    db.add_log(device_id, "INFO", f"Job #{jid} {status}: {success}/{count} success, {fail} fails")
    _refresh_download_files()
    if tg_chat:
        tg_send(tg_chat, f"Job #{jid} {status}\nSuccess: {success}/{count}\nFailed attempts: {fail}")
        if success > 0:
            path = os.path.join(DOWNLOAD_DIR, f"{device_id}.txt")
            if os.path.exists(path):
                tg_send_doc(tg_chat, path, caption=f"{device_id} accounts ({success})")

def _refresh_download_files():
    """সব ফাইল রিফ্রেশ করে (auto download system)"""
    all_accs = db.accounts(limit=99999)
    # Combined JSON
    with open(os.path.join(DOWNLOAD_DIR, "m1nx_all_accounts.json"), "w", encoding="utf-8") as f:
        json.dump(all_accs, f, indent=2, ensure_ascii=False)
    # Combined TXT
    with open(os.path.join(DOWNLOAD_DIR, "m1nx_all_accounts.txt"), "w", encoding="utf-8") as f:
        for a in all_accs:
            f.write(f"[{a['region']}] UID:{a['uid']} | ACC:{a['account_id']} | NAME:{a['name']} | PASS:{a['password']} | DEV:{a['device_id']} | {a['created_at']}\n")
    # Per device
    for d in db.devices():
        dev_accs = db.accounts(d["device_id"], limit=99999)
        if dev_accs:
            with open(os.path.join(DOWNLOAD_DIR, f"{d['device_id']}.txt"), "w", encoding="utf-8") as f:
                for a in dev_accs:
                    f.write(f"[{a['region']}] UID:{a['uid']} | ACC:{a['account_id']} | NAME:{a['name']} | PASS:{a['password']} | {a['created_at']}\n")

# ═══════════════════════ HTML TEMPLATES ═══════════════════════
BASE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - M1NX PREMIUM</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:radial-gradient(circle at top,#141B3C 0%,#0A0E27 60%);color:#E8EAF6;min-height:100vh;line-height:1.6}
.nav{background:rgba(10,14,39,0.95);backdrop-filter:blur(12px);border-bottom:2px solid #FFD700;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 4px 30px rgba(0,0,0,0.4)}
.brand{display:flex;align-items:center;gap:10px;font-family:'Orbitron',sans-serif;font-weight:900;font-size:20px;color:#FFD700}
.brand-logo{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#FFD700,#FF6B6B);display:flex;align-items:center;justify-content:center;font-weight:900;color:#0A0E27;font-size:18px;box-shadow:0 0 20px rgba(255,215,0,0.5)}
.brand-text{display:flex;flex-direction:column;line-height:1.1}
.brand-text small{font-size:10px;color:#00D9FF;font-family:'Inter',sans-serif;font-weight:600;letter-spacing:1px}
.nav-links{display:flex;gap:6px;flex-wrap:wrap}
.nav-links a{color:#8B92B8;text-decoration:none;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;transition:all 0.25s;display:flex;align-items:center;gap:6px}
.nav-links a:hover,.nav-links a.active{color:#FFD700;background:rgba(255,215,0,0.1);border:1px solid rgba(255,215,0,0.3)}
.dot{width:6px;height:6px;border-radius:50%;background:#00D9FF;display:inline-block}
.container{max-width:1400px;margin:0 auto;padding:24px}
.card{background:linear-gradient(135deg,rgba(20,27,60,0.85),rgba(30,40,80,0.85));border:1px solid rgba(255,215,0,0.2);border-radius:16px;padding:22px;margin-bottom:20px;box-shadow:0 8px 32px rgba(0,0,0,0.3)}
.card-title{font-family:'Orbitron',sans-serif;color:#FFD700;font-size:16px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:10px;letter-spacing:1px}
.card-title::before{content:'';width:4px;height:18px;background:linear-gradient(180deg,#FFD700,#FF6B6B);border-radius:2px}
.grid-3{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px}
.stat{background:linear-gradient(135deg,rgba(255,215,0,0.08),rgba(255,107,107,0.08));border:1px solid rgba(255,215,0,0.25);border-radius:12px;padding:18px;position:relative;overflow:hidden}
.stat::after{content:'';position:absolute;top:-30px;right:-30px;width:100px;height:100px;background:radial-gradient(circle,rgba(255,215,0,0.15),transparent);border-radius:50%}
.stat-label{color:#8B92B8;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;display:flex;align-items:center;gap:6px}
.stat-value{font-family:'Orbitron',sans-serif;color:#FFD700;font-size:28px;font-weight:900;margin-top:6px}
.stat-value-sm{font-size:16px;color:#00D9FF}
.btn{background:linear-gradient(135deg,#FFD700,#FFA000);color:#0A0E27;border:none;padding:10px 20px;border-radius:8px;font-family:'Orbitron',sans-serif;font-weight:700;cursor:pointer;font-size:12px;letter-spacing:1px;text-decoration:none;display:inline-flex;align-items:center;gap:6px;transition:all 0.25s}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(255,215,0,0.35)}
.btn-success{background:linear-gradient(135deg,#00E676,#00C853)}
.btn-danger{background:linear-gradient(135deg,#FF5252,#D32F2F);color:#fff}
.btn-sm{padding:6px 12px;font-size:11px}
.input,select{background:rgba(10,14,39,0.9);border:1px solid rgba(255,215,0,0.25);border-radius:8px;padding:11px 14px;color:#E8EAF6;width:100%;font-size:14px;font-family:'Inter',sans-serif;transition:all 0.25s}
.input:focus,select:focus{outline:none;border-color:#FFD700;box-shadow:0 0 0 3px rgba(255,215,0,0.1)}
label{color:#8B92B8;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;display:block;margin-bottom:6px;font-weight:600}
.table{width:100%;border-collapse:collapse;font-size:13px}
.table th{background:rgba(255,215,0,0.08);color:#FFD700;padding:11px;text-align:left;font-family:'Orbitron',sans-serif;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;border-bottom:2px solid rgba(255,215,0,0.25)}
.table td{padding:11px;border-bottom:1px solid rgba(255,215,0,0.08);color:#E8EAF6}
.table tr:hover{background:rgba(255,215,0,0.04)}
.badge{padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;display:inline-block}
.badge-success{background:rgba(0,230,118,0.2);color:#00E676;border:1px solid rgba(0,230,118,0.4)}
.badge-danger{background:rgba(255,82,82,0.2);color:#FF5252;border:1px solid rgba(255,82,82,0.4)}
.badge-warning{background:rgba(255,179,0,0.2);color:#FFB300;border:1px solid rgba(255,179,0,0.4)}
.badge-info{background:rgba(0,217,255,0.2);color:#00D9FF;border:1px solid rgba(0,217,255,0.4)}
.hero{text-align:center;padding:40px 20px}
.hero-logo{width:90px;height:90px;margin:0 auto 20px;border-radius:24px;background:linear-gradient(135deg,#FFD700,#FF6B6B);display:flex;align-items:center;justify-content:center;font-family:'Orbitron',sans-serif;font-size:42px;font-weight:900;color:#0A0E27;box-shadow:0 0 60px rgba(255,215,0,0.5);animation:pulse 2.5s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
.hero h1{font-family:'Orbitron',sans-serif;font-size:36px;color:#FFD700;letter-spacing:2px;margin-bottom:8px}
.hero p{color:#8B92B8;font-size:14px;margin-bottom:16px}
.tg-link{color:#00D9FF;text-decoration:none;border-bottom:1px solid #00D9FF;font-weight:600}
.flash{padding:12px 18px;border-radius:10px;margin-bottom:16px;font-weight:600;font-size:13px;display:flex;align-items:center;gap:8px}
.flash.success{background:rgba(0,230,118,0.12);border:1px solid #00E676;color:#00E676}
.flash.error{background:rgba(255,82,82,0.12);border:1px solid #FF5252;color:#FF5252}
.footer{text-align:center;padding:30px 20px;color:#8B92B8;font-size:12px;border-top:1px solid rgba(255,215,0,0.1);margin-top:40px}
.footer strong{color:#FFD700;font-family:'Orbitron',sans-serif;font-size:14px}
.footer a{color:#00D9FF;text-decoration:none}
.log-box{background:#05080F;border:1px solid rgba(255,215,0,0.25);border-radius:10px;padding:14px;font-family:'Consolas',monospace;font-size:12px;max-height:500px;overflow-y:auto;line-height:1.7}
.log-line{padding:4px 0;border-bottom:1px solid rgba(255,215,0,0.05);color:#8B92B8}
.log-line .ts{color:#666;margin-right:8px}
.log-line .dev{color:#00D9FF;margin-right:8px}
.log-line.SUCCESS{color:#00E676}
.log-line.FAIL{color:#FF5252}
.log-line.INFO{color:#FFD700}
.log-line.WARN{color:#FFB300}
.action-row{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
@media(max-width:700px){.nav{flex-direction:column;gap:10px}.nav-links{width:100%;justify-content:center}.brand{font-size:16px}}
</style>
</head>
<body>
<nav class="nav">
  <div class="brand">
    <div class="brand-logo">M</div>
    <div class="brand-text">M1NX PREMIUM<small>OWNER : M1NXGAMINGVIP</small></div>
  </div>
  <div class="nav-links">
    <a href="/" class="{{ 'active' if page=='dash' }}">Dashboard</a>
    <a href="/devices" class="{{ 'active' if page=='dev' }}">Devices</a>
    <a href="/accounts" class="{{ 'active' if page=='acc' }}">Accounts</a>
    <a href="/generate" class="{{ 'active' if page=='gen' }}">Generate</a>
    <a href="/logs" class="{{ 'active' if page=='log' }}">Logs</a>
    <a href="/download" class="{{ 'active' if page=='dl' }}">Download</a>
    <a href="/logout" style="color:#FF5252">Logout</a>
  </div>
</nav>
<div class="container">
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in msgs %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}
  {% endwith %}
  {{ content|safe }}
</div>
<footer class="footer">
  <strong>M1NX PREMIUM</strong> &nbsp;|&nbsp; Owner : M1NXGAMINGVIP &nbsp;|&nbsp;
  Telegram : <a href="https://t.me/M1NXGAMINGVIP">@M1NXGAMINGVIP</a>
  <div style="margin-top:8px;font-size:11px;color:#666">All Rights Reserved &copy; {{year}}</div>
</footer>
</body></html>
"""

LOGIN_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>M1NX PREMIUM - Login</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:radial-gradient(circle at center,#141B3C 0%,#0A0E27 70%);min-height:100vh;display:flex;align-items:center;justify-content:center;color:#E8EAF6}
.box{background:linear-gradient(135deg,rgba(20,27,60,0.95),rgba(30,40,80,0.95));border:1px solid rgba(255,215,0,0.3);border-radius:20px;padding:44px 36px;width:100%;max-width:420px;box-shadow:0 25px 60px rgba(0,0,0,0.6)}
.logo{width:76px;height:76px;margin:0 auto 18px;border-radius:20px;background:linear-gradient(135deg,#FFD700,#FF6B6B);display:flex;align-items:center;justify-content:center;font-family:'Orbitron',sans-serif;font-size:36px;font-weight:900;color:#0A0E27;box-shadow:0 0 40px rgba(255,215,0,0.5)}
h1{font-family:'Orbitron',sans-serif;color:#FFD700;text-align:center;font-size:22px;margin-bottom:4px;letter-spacing:1px}
.sub{text-align:center;color:#8B92B8;font-size:12px;margin-bottom:26px}
label{color:#8B92B8;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px;display:block;font-weight:600}
input{width:100%;background:rgba(10,14,39,0.9);border:1px solid rgba(255,215,0,0.3);border-radius:8px;padding:12px 14px;color:#E8EAF6;font-size:14px;margin-bottom:14px;font-family:'Inter',sans-serif}
input:focus{outline:none;border-color:#FFD700;box-shadow:0 0 0 3px rgba(255,215,0,0.1)}
button{width:100%;background:linear-gradient(135deg,#FFD700,#FFA000);color:#0A0E27;border:none;padding:13px;border-radius:8px;font-family:'Orbitron',sans-serif;font-weight:900;font-size:14px;cursor:pointer;letter-spacing:1.5px;margin-top:8px;transition:all 0.25s}
button:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(255,215,0,0.4)}
.err{background:rgba(255,82,82,0.15);border:1px solid #FF5252;color:#FF5252;padding:10px;border-radius:8px;margin-bottom:14px;text-align:center;font-size:12px}
.tg{text-align:center;margin-top:20px;color:#8B92B8;font-size:11px;border-top:1px solid rgba(255,215,0,0.1);padding-top:16px}
.tg a{color:#00D9FF;text-decoration:none;font-weight:600}
</style></head>
<body>
<div class="box">
  <div class="logo">M</div>
  <h1>M1NX PREMIUM</h1>
  <div class="sub">Owner : M1NXGAMINGVIP</div>
  {% if error %}<div class="err">{{error}}</div>{% endif %}
  <form method="POST">
    <label>Username</label>
    <input name="username" required autofocus placeholder="m1nx">
    <label>Password</label>
    <input name="password" type="password" required placeholder="Enter password">
    <button type="submit">LOGIN</button>
  </form>
  <div class="tg">Support : <a href="https://t.me/M1NXGAMINGVIP">@M1NXGAMINGVIP</a></div>
</div>
</body></html>
"""

def render(title, page, content):
    html = BASE_HTML.replace("{{ title }}", title).replace("{{ content|safe }}", content)
    html = html.replace("{{ 'active' if page=='" + page + "' }}", "active")
    # Remove any other page=... replacements
    for p in ["dash","dev","acc","gen","log","dl"]:
        if p != page:
            html = html.replace("{{ 'active' if page=='" + p + "' }}", "")
    html = html.replace("{{year}}", str(datetime.now().year))
    return html

def require_login(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("user"): return redirect("/login")
        return f(*a, **k)
    return w

# ═══════════════════════ ROUTES ═══════════════════════
@app.route("/login", methods=["GET","POST"])
def login():
    err = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["user"] = ADMIN_USER
            identify_device(request)
            return redirect("/")
        err = "Invalid username or password"
    return render_template_string(LOGIN_HTML, error=err)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@require_login
def dash():
    dev = identify_device(request)
    devs = db.devices()
    accs = db.accounts(limit=10)
    total = len(db.accounts(limit=99999))
    logs = db.logs(limit=12)
    acc_rows = "".join(
        f'<tr><td><b style="color:#FFD700">{a["account_id"]}</b></td><td>{a["name"]}</td>'
        f'<td><span class="badge badge-info">{a["region"]}</span></td>'
        f'<td style="font-size:11px;color:#8B92B8">{a["device_id"]}</td>'
        f'<td><span class="badge badge-success">{a["online_status"]}</span></td>'
        f'<td style="font-size:11px">{a["created_at"]}</td></tr>' for a in accs
    ) or '<tr><td colspan="6" style="text-align:center;padding:20px;color:#8B92B8">No accounts yet</td></tr>'
    log_lines = "".join(
        f'<div class="log-line {l["level"]}"><span class="ts">[{l["ts"]}]</span>'
        f'<span class="dev">[{l["device_id"]}]</span>{l["message"]}</div>' for l in logs
    ) or '<div class="log-line">No logs yet</div>'
    content = f"""
    <div class="hero">
      <div class="hero-logo">M</div>
      <h1>M1NX PREMIUM</h1>
      <p>Advanced Account Generator | Owner : M1NXGAMINGVIP</p>
      <p style="margin-top:8px"><a class="tg-link" href="https://t.me/M1NXGAMINGVIP">Telegram DM : @M1NXGAMINGVIP</a></p>
    </div>
    <div class="grid-3">
      <div class="stat"><div class="stat-label"><span class="dot"></span>Total Devices</div><div class="stat-value">{len(devs)}</div></div>
      <div class="stat"><div class="stat-label"><span class="dot"></span>Total Accounts</div><div class="stat-value">{total}</div></div>
      <div class="stat"><div class="stat-label"><span class="dot"></span>Your Device</div><div class="stat-value stat-value-sm">{dev['device_id']}</div></div>
    </div>
    <div class="card">
      <div class="card-title">Recent Accounts</div>
      <table class="table"><thead><tr><th>Account</th><th>Name</th><th>Region</th><th>Device</th><th>Status</th><th>Created</th></tr></thead><tbody>{acc_rows}</tbody></table>
    </div>
    <div class="card">
      <div class="card-title">Live Activity</div>
      <div class="log-box">{log_lines}</div>
    </div>
    """
    return render("Dashboard", "dash", content)

@app.route("/devices")
@require_login
def devices():
    devs = db.devices()
    rows = "".join(
        f'<tr><td><b style="color:#FFD700">{d["device_id"]}</b></td>'
        f'<td>{d["name"]}</td>'
        f'<td><span class="badge badge-info">{d["platform"]}</span></td>'
        f'<td style="font-size:11px;color:#8B92B8">{d["ip"]}</td>'
        f'<td>{d["total_generated"]}</td>'
        f'<td style="color:#00D9FF;font-size:11px">{d["current_action"]}</td>'
        f'<td><span class="badge badge-success">{d["status"]}</span></td>'
        f'<td style="font-size:11px">{d["last_seen"]}</td>'
        f'<td><a class="btn btn-sm" href="/device/{d["device_id"]}">View</a></td></tr>' for d in devs
    ) or '<tr><td colspan="9" style="text-align:center;padding:20px;color:#8B92B8">No devices yet</td></tr>'
    content = f"""
    <div class="card">
      <div class="card-title">All Devices ({len(devs)})</div>
      <p style="color:#8B92B8;font-size:13px;margin-bottom:14px">Each device is tracked separately. You can see what each device is currently doing.</p>
      <table class="table"><thead><tr><th>Device ID</th><th>Name</th><th>Platform</th><th>IP</th><th>Generated</th><th>Current Action</th><th>Status</th><th>Last Seen</th><th></th></tr></thead><tbody>{rows}</tbody></table>
    </div>"""
    return render("Devices", "dev", content)

@app.route("/device/<did>")
@require_login
def device_detail(did):
    d = db.device(did)
    if not d: return redirect("/devices")
    accs = db.accounts(did, limit=999)
    logs = db.logs(did, 80)
    acc_rows = "".join(
        f'<tr><td><b style="color:#FFD700">{a["account_id"]}</b></td>'
        f'<td>{a["name"]}</td><td><span class="badge badge-info">{a["region"]}</span></td>'
        f'<td style="font-size:11px">{a["uid"]}</td><td style="font-size:11px;word-break:break-all">{a["password"]}</td>'
        f'<td><span class="badge badge-success">{a["online_status"]}</span></td>'
        f'<td style="font-size:11px">{a["created_at"]}</td></tr>' for a in accs
    ) or '<tr><td colspan="7" style="text-align:center;padding:20px;color:#8B92B8">No accounts from this device</td></tr>'
    log_lines = "".join(
        f'<div class="log-line {l["level"]}"><span class="ts">[{l["ts"]}]</span>{l["message"]}</div>' for l in logs
    ) or '<div class="log-line">No logs</div>'
    content = f"""
    <div class="card">
      <div class="card-title">Device: {d['device_id']}</div>
      <div class="grid-3">
        <div class="stat"><div class="stat-label">Name</div><div class="stat-value stat-value-sm">{d['name']}</div></div>
        <div class="stat"><div class="stat-label">Platform</div><div class="stat-value stat-value-sm">{d['platform']}</div></div>
        <div class="stat"><div class="stat-label">Total Generated</div><div class="stat-value">{d['total_generated']}</div></div>
      </div>
      <div class="grid-2" style="margin-top:16px">
        <div class="stat"><div class="stat-label">Current Action</div><div class="stat-value stat-value-sm" style="color:#00D9FF">{d['current_action']}</div></div>
        <div class="stat"><div class="stat-label">Region</div><div class="stat-value stat-value-sm">{d['region']}</div></div>
      </div>
      <p style="margin-top:16px;color:#8B92B8;font-size:12px;line-height:1.8">
        <b>IP:</b> {d['ip']}<br>
        <b>First Seen:</b> {d['first_seen']} &nbsp;|&nbsp; <b>Last Seen:</b> {d['last_seen']}<br>
        <b>User-Agent:</b> <span style="word-break:break-all">{d['ua'][:180]}</span>
      </p>
    </div>
    <div class="card">
      <div class="card-title">Accounts ({len(accs)})</div>
      <table class="table"><thead><tr><th>Account</th><th>Name</th><th>Region</th><th>UID</th><th>Password</th><th>Status</th><th>Created</th></tr></thead><tbody>{acc_rows}</tbody></table>
    </div>
    <div class="card">
      <div class="card-title">Activity Logs</div>
      <div class="log-box">{log_lines}</div>
    </div>"""
    return render("Device Detail", "dev", content)

@app.route("/accounts")
@require_login
def accounts():
    reg = request.args.get("region","")
    did = request.args.get("device","")
    accs = db.accounts(did or None, region=reg or None)
    rows = "".join(
        f'<tr><td><b style="color:#FFD700">{a["account_id"]}</b></td>'
        f'<td>{a["name"]}</td><td><span class="badge badge-info">{a["region"]}</span></td>'
        f'<td style="font-size:11px">{a["uid"]}</td>'
        f'<td style="font-size:11px;word-break:break-all">{a["password"]}</td>'
        f'<td style="font-size:11px;color:#8B92B8">{a["device_id"]}</td>'
        f'<td><span class="badge badge-success">{a["online_status"]}</span></td>'
        f'<td style="font-size:11px">{a["created_at"]}</td></tr>' for a in accs
    ) or '<tr><td colspan="8" style="text-align:center;padding:20px;color:#8B92B8">No accounts yet</td></tr>'
    content = f"""
    <div class="card">
      <div class="card-title">All Accounts ({len(accs)})</div>
      <div class="action-row">
        <a class="btn btn-sm" href="/accounts">All</a>
        <a class="btn btn-sm" href="/accounts?region=BD">BD</a>
        <a class="btn btn-sm" href="/accounts?region=IND">IND</a>
        <a class="btn btn-sm btn-success" href="/download" style="margin-left:auto">Download Files</a>
      </div>
      <table class="table"><thead><tr><th>Account</th><th>Name</th><th>Region</th><th>UID</th><th>Password</th><th>Device</th><th>Status</th><th>Created</th></tr></thead><tbody>{rows}</tbody></table>
    </div>"""
    return render("Accounts", "acc", content)

@app.route("/generate", methods=["GET","POST"])
@require_login
def generate_page():
    dev = identify_device(request)
    if request.method == "POST":
        try:
            count = int(request.form.get("count",1))
            region = request.form.get("region","BD")
            if count <= 0 or count > 100: raise ValueError
            threading.Thread(target=run_generation, args=(dev["device_id"], region, count), daemon=True).start()
            flash(f"Generation started: {count} x {region}. Check Logs page.", "success")
            return redirect("/logs")
        except Exception:
            flash("Invalid input", "error")
    content = f"""
    <div class="card">
      <div class="card-title">Start Generation</div>
      <p style="color:#8B92B8;font-size:13px;margin-bottom:16px">The system will keep retrying until the target count is reached.</p>
      <form method="POST">
        <div class="grid-2">
          <div><label>How many accounts</label><input class="input" name="count" type="number" value="5" min="1" max="100" required></div>
          <div><label>Region</label>
            <select class="input" name="region">
              <option value="BD">Bangladesh (BD)</option>
              <option value="IND">India (IND)</option>
            </select>
          </div>
        </div>
        <button type="submit" class="btn" style="margin-top:18px">START GENERATION</button>
      </form>
    </div>
    <div class="card">
      <div class="card-title">Info</div>
      <p style="color:#8B92B8;font-size:13px;line-height:2">
        <b style="color:#FFD700">Your Device:</b> {dev['device_id']}<br>
        <b style="color:#FFD700">Prefix:</b> {CUSTOM_PREFIX}XXXXXX<br>
        <b style="color:#FFD700">Bio:</b> {CUSTOM_BIO}<br>
        <b style="color:#FFD700">Owner:</b> M1NXGAMINGVIP &nbsp;|&nbsp;
        <b style="color:#FFD700">Telegram:</b> <a href="https://t.me/M1NXGAMINGVIP" style="color:#00D9FF">@M1NXGAMINGVIP</a>
      </p>
    </div>"""
    return render("Generate", "gen", content)

@app.route("/logs")
@require_login
def logs_page():
    all_logs = db.logs(limit=200)
    lines = "".join(
        f'<div class="log-line {l["level"]}"><span class="ts">[{l["ts"]}]</span>'
        f'<span class="dev">[{l["device_id"]}]</span>{l["message"]}</div>' for l in all_logs
    ) or '<div class="log-line">No logs yet</div>'
    content = f"""
    <div class="card">
      <div class="card-title">Live Logs (auto-refresh)</div>
      <div class="log-box" id="logbox">{lines}</div>
    </div>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
      const s = io();
      const box = document.getElementById('logbox');
      s.on('log', d => {{
        const div = document.createElement('div');
        div.className = 'log-line ' + d.level;
        div.innerHTML = '<span class="ts">[' + (d.ts||'') + ']</span><span class="dev">[' + (d.device||'') + ']</span>' + d.message;
        box.prepend(div);
      }});
      setTimeout(() => location.reload(), 25000);
    </script>"""
    return render("Live Logs", "log", content)

@app.route("/download")
@require_login
def download_page():
    _refresh_download_files()
    files = sorted(os.listdir(DOWNLOAD_DIR))
    rows = "".join(
        f'<tr><td><b style="color:#FFD700">{f}</b></td>'
        f'<td>{os.path.getsize(os.path.join(DOWNLOAD_DIR,f))} bytes</td>'
        f'<td><a class="btn btn-sm btn-success" href="/download/{f}">Download</a></td></tr>'
        for f in files if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))
    ) or '<tr><td colspan="3" style="text-align:center;padding:20px;color:#8B92B8">No files yet</td></tr>'
    content = f"""
    <div class="card">
      <div class="card-title">Auto Download Files ({len(files)})</div>
      <p style="color:#8B92B8;font-size:13px;margin-bottom:14px">Files are auto-generated after each successful account creation.</p>
      <table class="table"><thead><tr><th>File</th><th>Size</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>
    </div>"""
    return render("Download", "dl", content)

@app.route("/download/<path:fn>")
@require_login
def download_file(fn):
    return send_from_directory(DOWNLOAD_DIR, fn, as_attachment=True)

@app.route("/api/stats")
@require_login
def api_stats():
    return jsonify({"devices":len(db.devices()),"accounts":len(db.accounts(limit=99999)),
                    "owner":OWNER_NAME,"telegram":OWNER_TG})

# ═══════════════════════ STARTUP ═══════════════════════
def _start_tg_thread():
    if TG_BOT_TOKEN:
        t = threading.Thread(target=tg_poll_loop, daemon=True)
        t.start()
        print("[TG] Bot started")

_start_tg_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(f"  M1NX PREMIUM SYSTEM STARTED")
    print(f"  Owner     : {OWNER_NAME}")
    print(f"  Telegram  : {OWNER_TG}")
    print(f"  Login User: {ADMIN_USER}")
    print(f"  Login Pass: {ADMIN_PASS}")
    print(f"  Port      : {port}")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)