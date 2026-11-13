import os, json, sqlite3, hashlib, hmac, time
from urllib.parse import parse_qsl
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "moneymate.db")
app = FastAPI(title="MoneyMate API")

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
          amount REAL NOT NULL, category TEXT NOT NULL, note TEXT DEFAULT '',
          happened_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS goals (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          title TEXT NOT NULL, target REAL NOT NULL, saved REAL NOT NULL DEFAULT 0,
          deadline TEXT DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
          user_id TEXT PRIMARY KEY, currency TEXT NOT NULL DEFAULT 'RUB',
          needs REAL NOT NULL DEFAULT 50, wants REAL NOT NULL DEFAULT 30,
          savings REAL NOT NULL DEFAULT 20
        );
        """)
init_db()

def verify_init_data(init_data: str):
    if not BOT_TOKEN:
        raise HTTPException(503, "BOT_TOKEN is not configured on the server")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash")
        auth_date = int(pairs.get("auth_date", "0"))
        if time.time() - auth_date > 86400:
            raise ValueError("expired Telegram session")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            raise ValueError("invalid signature")
        user = json.loads(pairs["user"])
        return str(user["id"])
    except Exception:
        raise HTTPException(401, "Open MoneyMate from your Telegram bot")

def current_user(x_telegram_init_data: str = Header(default="")):
    return verify_init_data(x_telegram_init_data)

class TransactionIn(BaseModel):
    kind: str
    amount: float = Field(gt=0, le=100000000)
    category: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=160)
    happened_at: str

class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    target: float = Field(gt=0, le=100000000)
    saved: float = Field(default=0, ge=0)
    deadline: str = ""

class GoalAdd(BaseModel):
    amount: float = Field(gt=0)

class SettingsIn(BaseModel):
    currency: str = "RUB"
    needs: float = Field(ge=0, le=100)
    wants: float = Field(ge=0, le=100)
    savings: float = Field(ge=0, le=100)

@app.get("/api/health")
def health():
    return {"ok": True, "app": "MoneyMate"}

@app.get("/api/me")
def me(user_id: str = Header(default="", alias="X-Telegram-Init-Data")):
    uid = current_user(user_id)
    with db() as c:
        row = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
        if not row:
            c.execute("INSERT INTO settings(user_id) VALUES(?)", (uid,))
            row = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
    return {"user_id": uid, "settings": dict(row)}

@app.get("/api/transactions")
def transactions(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        rows = c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY happened_at DESC, id DESC LIMIT 300", (uid,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/transactions")
def add_transaction(data: TransactionIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    if data.kind not in ("income", "expense"):
        raise HTTPException(400, "Invalid transaction kind")
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        cur = c.execute("INSERT INTO transactions(user_id,kind,amount,category,note,happened_at,created_at) VALUES(?,?,?,?,?,?,?)",
          (uid, data.kind, data.amount, data.category.strip(), data.note.strip(), data.happened_at, now))
        row = c.execute("SELECT * FROM transactions WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (transaction_id, uid))
    if not cur.rowcount:
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}

@app.get("/api/goals")
def goals(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        rows = c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/goals")
def add_goal(data: GoalIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        cur = c.execute("INSERT INTO goals(user_id,title,target,saved,deadline,created_at) VALUES(?,?,?,?,?,?)",
          (uid, data.title.strip(), data.target, data.saved, data.deadline, now))
        row = c.execute("SELECT * FROM goals WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.post("/api/goals/{goal_id}/add")
def contribute(goal_id: int, data: GoalAdd, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("UPDATE goals SET saved=saved+? WHERE id=? AND user_id=?", (data.amount, goal_id, uid))
        if not cur.rowcount:
            raise HTTPException(404, "Goal not found")
        row = c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
    return dict(row)

@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, uid))
    if not cur.rowcount:
        raise HTTPException(404, "Goal not found")
    return {"ok": True}

@app.get("/api/settings")
def get_settings(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        row = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
        if not row:
            c.execute("INSERT INTO settings(user_id) VALUES(?)", (uid,))
            row = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
    return dict(row)

@app.put("/api/settings")
def save_settings(data: SettingsIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    if abs(data.needs + data.wants + data.savings - 100) > 0.01:
        raise HTTPException(400, "Budget percentages must total 100")
    with db() as c:
        c.execute("INSERT INTO settings(user_id,currency,needs,wants,savings) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET currency=excluded.currency,needs=excluded.needs,wants=excluded.wants,savings=excluded.savings",
          (uid, data.currency, data.needs, data.wants, data.savings))
    return {"ok": True}

@app.get("/api/summary")
def summary(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    month = datetime.now().strftime("%Y-%m")
    with db() as c:
        rows = c.execute("SELECT kind, SUM(amount) total FROM transactions WHERE user_id=? AND substr(happened_at,1,7)=? GROUP BY kind", (uid, month)).fetchall()
        cats = c.execute("SELECT category, SUM(amount) total FROM transactions WHERE user_id=? AND kind='expense' AND substr(happened_at,1,7)=? GROUP BY category ORDER BY total DESC", (uid, month)).fetchall()
        settings = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
        if not settings:
            c.execute("INSERT INTO settings(user_id) VALUES(?)", (uid,))
            settings = c.execute("SELECT * FROM settings WHERE user_id=?", (uid,)).fetchone()
    totals = {r["kind"]: r["total"] or 0 for r in rows}
    return {"income": totals.get("income",0), "expense": totals.get("expense",0),
      "balance": totals.get("income",0)-totals.get("expense",0),
      "categories": [dict(r) for r in cats], "settings": dict(settings), "month": month}

@app.get("/")
def index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
