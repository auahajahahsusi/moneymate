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

## MoneyMate 6.0 — аккаунты и сохранение прогресса

- Регистрация и вход происходят автоматически через проверенный Telegram Mini App initData: отдельный пароль не нужен.
- В таблице `accounts` сохраняются Telegram ID, имя, фамилия, username, дата регистрации и последнего входа.
- Приветствие берёт имя из подтверждённого Telegram-профиля.
- Финансовые данные уже изолированы по Telegram ID: операции, цели, кошельки, лимиты, регулярные платежи и настройки загружаются для вошедшего аккаунта.
- Путь к SQLite задаётся переменной `DB_PATH`. Для сохранения данных между перезапусками Render нужен постоянный диск и `DB_PATH=/var/data/moneymate.db` с диском, смонтированным в `/var/data`. На бесплатном ephemeral filesystem данные могут исчезнуть при redeploy/restart. Не включайте постоянное хранилище, не проверив тариф Render.
- Перед обновлением сделайте экспорт JSON из раздела «Кошельки» и сохраните резервную копию.

Важно: это Telegram-аккаунт, а не отдельная регистрация по email/паролю. Войти можно в тот же аккаунт Telegram — прогресс будет привязан к Telegram ID.


## MoneyMate 6.1 — аккаунты, профиль и темы

### Что добавлено
- Регистрация по имени, логину и паролю; вход по логину и паролю.
- Пароли хранятся в базе только в виде PBKDF2-HMAC-SHA256 хеша с солью.
- Случайные сессионные токены, срок действия 30 дней.
- Профиль: изменение имени, выбор аватара, смена пароля.
- Меню профиля с пунктами «Профиль», «Настройки», «Выйти».
- Шесть тем: зелёная, тёмная, белая, золотая, красно-тёмная, чёрно-белая.
- Тема и профиль сохраняются в базе; финансовые записи привязаны к отдельному ID аккаунта.

### Важное про сохранность данных
MoneyMate по-прежнему использует SQLite. На бесплатном Render локальная файловая система может быть временной, поэтому данные аккаунтов и финансовые записи могут потеряться при перезапуске/деплое. Для постоянного хранения подключите постоянный диск Render (обычно платный) и задайте `DB_PATH=/var/data/moneymate.db`, смонтировав диск в `/var/data`, либо перенесите БД на PostgreSQL. Не обещайте пользователям постоянное хранение, пока постоянное хранилище не подключено.

### Установка
1. Сделайте резервную копию текущего проекта и базы данных.
2. Распакуйте ZIP и загрузите содержимое в корень GitHub-репозитория.
3. Убедитесь, что `app.py`, `requirements.txt` и папка `static` находятся в корне.
4. Commit changes и выполните Manual Deploy в Render.
5. Для проверки создайте тестовый аккаунт, выйдите и войдите снова; проверьте смену темы, аватара и пароля.

### Совместимость и перенос старых данных
Новые локальные аккаунты имеют собственные идентификаторы. Ранее созданные записи, привязанные к Telegram ID из предыдущей версии, автоматически не объединяются с новым логином. Перед переходом сохраните резервную копию; перенос старых записей в локальный аккаунт требует отдельной процедуры связывания/миграции.

### Ограничения
- Логин: 3–24 символа, латинские буквы, цифры, `_`, `.` и `-`.
- Пароль: минимум 6 символов.
- Сброс пароля через email не предусмотрен, так как пользователь выбрал регистрацию только по имени и паролю. Не теряйте пароль.
- Реальный запуск и проверка оплаты Telegram Stars требуют тестирования на опубликованном Render-сервисе.
