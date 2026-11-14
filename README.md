# MoneyMate 4.3

Обновление интерфейса и локального финансового помощника.

## Изменения 4.3
- Раздельные категории доходов и расходов в форме добавления операции.
- Аналитика расходов в банковском стиле: кольцевая диаграмма с цветами по категориям, суммами и долями.
- Исправлен сценарий ИИ-помощника для вопросов о накоплении конкретной суммы. Например, для «Как мне накопить 50000 рублей за 6 месяцев?» рассчитывается ежемесячный и недельный взнос и сравнивается с текущим остатком.
- Если срок не указан, помощник оценивает примерный срок исходя из текущего свободного остатка.

## Развёртывание
1. Сделайте резервную копию текущих данных и файлов.
2. Замените `app.py`, `README.md` и папку `static` файлами из архива.
3. Сохраните существующие настройки Render и `BOT_TOKEN`.
4. Сделайте commit в GitHub и выполните Render → Manual Deploy → Deploy latest commit.

Все суммы отображаются в российских рублях (₽). Локальный помощник не использует внешний API и не является генеративной нейросетью.


## Channel access and MoneyMate Premium (Telegram Stars)

1. Add the Telegram bot as an administrator of the public channel `@MoneyMateDiary` (membership lookup requires the bot to be an administrator).
2. In Render → Environment, keep the existing `BOT_TOKEN` and add:
   - `REQUIRED_CHANNEL` = `@MoneyMateDiary`
   - `PUBLIC_BASE_URL` = `https://moneymate-1g70.onrender.com` (replace if your Render URL changes)
   - `TELEGRAM_WEBHOOK_SECRET` = a long random secret string (generate one privately; do not share it in chat).
3. On startup, the app registers `https://YOUR_PUBLIC_BASE_URL/api/telegram/webhook` with Telegram. The webhook handles pre-checkout confirmation and successful Stars subscription payments.
4. Users must join the channel before entering the Mini App. The app checks membership with Telegram on entry and the API checks it again on protected requests.
5. Premium is a recurring 30-day Telegram Stars subscription priced at 179 XTR. Payment activation is performed only from Telegram's verified `successful_payment` update.

Important: use persistent storage or PostgreSQL for production. The included SQLite database on an ephemeral Render filesystem can be lost during redeploy/restart; that would also lose local subscription records. Telegram's payment history remains on Telegram, but the app's entitlement state needs durable storage. Test payments in a Telegram test environment before announcing sales.
\n\n## Исправление 5.1\nВ клиенте добавлен тайм-аут сетевых запросов (30 секунд) и понятное сообщение при недоступности API, чтобы экран проверки доступа не оставался на бесконечной загрузке без объяснения. Если запрос прерывается по тайм-ауту, проверьте Render Logs и доступность Telegram Bot API.\n