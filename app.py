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
        CREATE TABLE IF NOT EXISTS wallets (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'cash', balance REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS spending_limits (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          category TEXT NOT NULL, amount REAL NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(user_id, category)
        );
        CREATE TABLE IF NOT EXISTS recurring_payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
          amount REAL NOT NULL, category TEXT NOT NULL, note TEXT DEFAULT '',
          frequency TEXT NOT NULL CHECK(frequency IN ('weekly','monthly','yearly')),
          next_date TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
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

class RecurringIn(BaseModel):
    kind: str
    amount: float = Field(gt=0, le=100000000)
    category: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=160)
    frequency: str
    next_date: str

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

def advance_date(date_text: str, frequency: str) -> str:
    from datetime import date, timedelta
    from calendar import monthrange
    d = date.fromisoformat(date_text)
    if frequency == "weekly":
        d += timedelta(days=7)
    elif frequency == "yearly":
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            d = d.replace(year=d.year + 1, day=28)
    else:
        month = d.month + 1
        year = d.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        d = d.replace(year=year, month=month, day=min(d.day, monthrange(year, month)[1]))
    return d.isoformat()

def process_due_payments(uid: str):
    today = datetime.now().date().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        rows = c.execute("SELECT * FROM recurring_payments WHERE user_id=? AND active=1 AND next_date<=?", (uid, today)).fetchall()
        for item in rows:
            next_date = item["next_date"]
            # Catch up every missed occurrence exactly once when the user opens the app.
            for _ in range(120):
                if next_date > today:
                    break
                c.execute("INSERT INTO transactions(user_id,kind,amount,category,note,happened_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (uid, item["kind"], item["amount"], item["category"], item["note"], next_date, now))
                next_date = advance_date(next_date, item["frequency"])
            c.execute("UPDATE recurring_payments SET next_date=? WHERE id=? AND user_id=?", (next_date, item["id"], uid))

@app.get("/api/recurring")
def list_recurring(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    process_due_payments(uid)
    with db() as c:
        rows = c.execute("SELECT * FROM recurring_payments WHERE user_id=? ORDER BY active DESC,next_date ASC,id DESC", (uid,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/recurring")
def add_recurring(data: RecurringIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    if data.kind not in ("income", "expense") or data.frequency not in ("weekly", "monthly", "yearly"):
        raise HTTPException(400, "Invalid recurring payment settings")
    try:
        datetime.strptime(data.next_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid next date")
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        cur = c.execute("INSERT INTO recurring_payments(user_id,kind,amount,category,note,frequency,next_date,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (uid, data.kind, data.amount, data.category.strip(), data.note.strip(), data.frequency, data.next_date, now))
        row = c.execute("SELECT * FROM recurring_payments WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.patch("/api/recurring/{payment_id}")
def toggle_recurring(payment_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        c.execute("UPDATE recurring_payments SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND user_id=?", (payment_id, uid))
        row = c.execute("SELECT * FROM recurring_payments WHERE id=? AND user_id=?", (payment_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Recurring payment not found")
    return dict(row)

@app.delete("/api/recurring/{payment_id}")
def delete_recurring(payment_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("DELETE FROM recurring_payments WHERE id=? AND user_id=?", (payment_id, uid))
    if not cur.rowcount:
        raise HTTPException(404, "Recurring payment not found")
    return {"ok": True}

class WalletIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    kind: str = Field(default="cash", max_length=20)
    balance: float = Field(default=0, ge=0, le=100000000)

class LimitIn(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    amount: float = Field(gt=0, le=100000000)

@app.get("/api/wallets")
def get_wallets(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM wallets WHERE user_id=? ORDER BY id", (uid,)).fetchall()]

@app.post("/api/wallets")
def create_wallet(data: WalletIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        cur = c.execute("INSERT INTO wallets(user_id,name,kind,balance,created_at) VALUES(?,?,?,?,?)", (uid,data.name.strip(),data.kind,data.balance,now))
        return dict(c.execute("SELECT * FROM wallets WHERE id=?", (cur.lastrowid,)).fetchone())

@app.delete("/api/wallets/{wallet_id}")
def remove_wallet(wallet_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("DELETE FROM wallets WHERE id=? AND user_id=?", (wallet_id,uid))
    if not cur.rowcount: raise HTTPException(404, "Wallet not found")
    return {"ok":True}

@app.get("/api/limits")
def get_limits(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    month = datetime.now().strftime("%Y-%m")
    with db() as c:
        rows = c.execute("SELECT l.*, COALESCE((SELECT SUM(t.amount) FROM transactions t WHERE t.user_id=l.user_id AND t.category=l.category AND t.kind='expense' AND substr(t.happened_at,1,7)=?),0) spent FROM spending_limits l WHERE l.user_id=? ORDER BY l.category", (month,uid)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/limits")
def save_limit(data: LimitIn, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        c.execute("INSERT INTO spending_limits(user_id,category,amount,created_at) VALUES(?,?,?,?) ON CONFLICT(user_id,category) DO UPDATE SET amount=excluded.amount", (uid,data.category.strip(),data.amount,datetime.now(timezone.utc).isoformat()))
    return {"ok":True}

@app.delete("/api/limits/{limit_id}")
def delete_limit(limit_id: int, x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        cur = c.execute("DELETE FROM spending_limits WHERE id=? AND user_id=?", (limit_id,uid))
    if not cur.rowcount: raise HTTPException(404, "Limit not found")
    return {"ok":True}

@app.get("/api/calendar")
def calendar_events(month: str = "", x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    if not month: month = datetime.now().strftime("%Y-%m")
    if len(month)!=7 or month[4]!='-': raise HTTPException(400,"Month must be YYYY-MM")
    with db() as c:
        tx = c.execute("SELECT id,kind,amount,category,happened_at AS date,note FROM transactions WHERE user_id=? AND substr(happened_at,1,7)=? ORDER BY happened_at",(uid,month)).fetchall()
        rp = c.execute("SELECT id,kind,amount,category,next_date AS date,note,frequency FROM recurring_payments WHERE user_id=? AND active=1 AND substr(next_date,1,7)=? ORDER BY next_date",(uid,month)).fetchall()
    return {"month":month,"events":[dict(r,source="operation") for r in tx]+[dict(r,source="planned") for r in rp]}

@app.get("/api/export")
def export_data(x_telegram_init_data: str = Header(default="")):
    uid = current_user(x_telegram_init_data)
    with db() as c:
        result={}
        for table in ("transactions","goals","settings","recurring_payments","wallets","spending_limits"):
            result[table]=[dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE user_id=?",(uid,)).fetchall()]
    return {"exported_at":datetime.now(timezone.utc).isoformat(),"currency":"RUB","data":result}

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
          (uid, "RUB", data.needs, data.wants, data.savings))
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
    income, expense = totals.get("income", 0), totals.get("expense", 0)
    balance = income - expense
    # Transparent 1-100 wellness indicator, not a credit score or financial advice.
    if income <= 0:
        score = 1
        score_parts = {"сбережения": 0, "баланс": 0, "расходы": 0, "резерв": 0}
        score_hint = "Добавь доходы и расходы, чтобы оценка стала точнее."
    else:
        savings_rate = max(0, balance / income)
        savings_points = min(30, savings_rate / 0.20 * 30)
        balance_points = 25 if balance >= 0 else max(0, 25 * (1 + balance / income))
        ratio = expense / income
        spending_points = 25 if ratio <= 0.5 else (25 * max(0, (1-ratio)/0.5) if ratio < 1 else 0)
        with db() as c:
            reserve = c.execute("SELECT COALESCE(SUM(saved),0) FROM goals WHERE user_id=? AND (lower(title) LIKE '%резерв%' OR lower(title) LIKE '%подушк%')", (uid,)).fetchone()[0]
        reserve_points = min(20, reserve / max(expense * 3, 1) * 20) if expense > 0 else (20 if reserve > 0 else 0)
        raw_score = savings_points + balance_points + spending_points + reserve_points
        score = max(1, min(100, round(raw_score)))
        score_parts = {"сбережения": round(savings_points), "баланс": round(balance_points), "расходы": round(spending_points), "резерв": round(reserve_points)}
        score_hint = "Создай цель «Финансовая подушка» и пополняй её, чтобы улучшить оценку." if reserve_points < 20 else "Продолжай поддерживать положительный баланс."
    return {"income": income, "expense": expense, "balance": balance,
      "categories": [dict(r) for r in cats], "settings": dict(settings), "month": month,
      "financial_health": {"score": score, "parts": score_parts, "hint": score_hint}}

@app.get("/")
def index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
