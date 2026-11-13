# MoneyMate — Telegram Mini App (MVP)

A minimal, responsive personal-finance Mini App starter:
- income and expense entry
- three budget buckets: Necessary / Flexible / Non-essential
- editable budget split (defaults to 50/30/20)
- daily journal
- calculator
- SQLite persistence per Telegram user (when opened in Telegram)

## Requirements
- Python 3.10+
- A Telegram bot token from @BotFather
- A public HTTPS URL for the app (for example, a small VPS or a hosting platform)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export BOT_TOKEN="123:abc"       # Windows PowerShell: $env:BOT_TOKEN="123:abc"
uvicorn app:app --host 0.0.0.0 --port 8000
```
Open `http://localhost:8000` in a browser for a local preview. Local browser preview uses a demo user.
For Telegram testing, the app must be served over HTTPS and opened from your bot's Mini App button.

## Connect to Telegram
1. Create a bot with `@BotFather` using `/newbot`.
2. Set the Mini App URL with `/setmenubutton` (or configure a Web App button in your bot).
3. Deploy this project to a public HTTPS address.
4. Set `BOT_TOKEN` in the hosting environment.
5. Configure the menu button URL to your deployed URL.

The backend validates Telegram `initData` when it is supplied. Never put the bot token in frontend JavaScript.

## Important MVP notes
- The default currency is EUR and can be changed in the UI.
- This is a starter, not financial advice.
- For production, add HTTPS hosting, backups, rate limiting, logging, stronger deployment configuration, and privacy/retention controls.
- Do not use real financial account credentials or bank-card data in this app.
