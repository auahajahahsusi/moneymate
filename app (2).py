import os, json, hmac, hashlib, time, sqlite3
from urllib.parse import parse_qsl
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
DB = BASE / "moneymate.sqlite3"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = FastAPI(title="MoneyMate")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

with db() as c:
    c.execute("""CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT PRIMARY KEY, necessary REAL DEFAULT 50,
        flexible REAL DEFAULT 30, nonessential REAL DEFAULT 20,
        currency TEXT DEFAULT 'EUR'
    )""")

def telegram_user_id(init_data: str) -> str:
    # In local browser preview, use a demo account. In Telegram, validate initData.
    if not init_data:
        return "local-demo"
    if not BOT_TOKEN:
        raise HTTPException(503, "BOT_TOKEN is not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Invalid Telegram initData")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Telegram signature check failed")
    auth_date = int(pairs.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        raise HTTPException(401, "Telegram session expired; reopen the app")
    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        raise HTTPException(401, "Telegram user is missing")
    return str(user["id"])

async def get_user(request: Request):
    return telegram_user_id(request.headers.get("X-Telegram-Init-Data", ""))

@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/state")
async def state(request: Request):
    uid = await get_user(request)
    with db() as c:
        c.execute("INSERT OR IGNORE INTO settings(user_id) VALUES (?)", (uid,))
        s = dict(c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone())
        entries = [dict(r) for r in c.execute(
            "SELECT * FROM entries WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,))]
        journal = [dict(r) for r in c.execute(
            "SELECT * FROM journal WHERE user_id=? ORDER BY id DESC LIMIT 50", (uid,))]
    return {"settings": s, "entries": entries, "journal": journal}

@app.post("/api/entry")
async def add_entry(request: Request):
    uid = await get_user(request)
    data = await request.json()
    kind, category = data.get("kind"), data.get("category")
    amount, note = data.get("amount"), str(data.get("note", ""))[:300]
    if kind not in ("income", "expense") or not isinstance(amount, (int, float)) or amount <= 0 or amount > 1_000_000_000:
        raise HTTPException(400, "Check transaction type and amount")
    if category not in ("necessary", "flexible", "nonessential", "income"):
        raise HTTPException(400, "Unknown category")
    with db() as c:
        c.execute("INSERT INTO entries(user_id,kind,category,amount,note,created_at) VALUES (?,?,?,?,?,datetime('now'))",
                  (uid, kind, category, float(amount), note))
    return {"ok": True}

@app.post("/api/settings")
async def save_settings(request: Request):
    uid = await get_user(request)
    d = await request.json()
    vals = [float(d.get(k, 0)) for k in ("necessary", "flexible", "nonessential")]
    if any(v < 0 or v > 100 for v in vals) or abs(sum(vals)-100) > 0.001:
        raise HTTPException(400, "Percentages must total 100")
    currency = d.get("currency", "EUR")
    if currency not in ("EUR", "USD", "RUB", "GBP"):
        currency = "EUR"
    with db() as c:
        c.execute("""INSERT INTO settings(user_id,necessary,flexible,nonessential,currency)
                     VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                     necessary=excluded.necessary, flexible=excluded.flexible,
                     nonessential=excluded.nonessential, currency=excluded.currency""",
                  (uid, *vals, currency))
    return {"ok": True}

@app.post("/api/journal")
async def add_journal(request: Request):
    uid = await get_user(request)
    body = str((await request.json()).get("body", "")).strip()[:2000]
    if not body:
        raise HTTPException(400, "Journal entry cannot be empty")
    with db() as c:
        c.execute("INSERT INTO journal(user_id,body,created_at) VALUES (?,?,datetime('now'))", (uid, body))
    return {"ok": True}
