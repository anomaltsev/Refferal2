# Referral Bot (Telegram)

## 🚀 Возможности
- Реферальные ссылки (`t.me/bot?start=userid`)
- Проверка обязательной подписки на канал
- Мини-капча при старте
- Подсчёт друзей
- Отметка подозрительных аккаунтов (⚠️)
- Команда /me — мои результаты
- Команда /admin_stats — статистика
- Команда /id @username — получить user_id по username
- Команда /adduser <tg_id> <username> <refs> — вручную добавить/обновить пользователя
- Остальные команды: /top, /winners, /giveprize, /prizeslog, /exportdb, /importdb, /linkref, /referrals

## ⚙️ Запуск
```bash
pip install -r requirements.txt
export BOT_TOKEN=твой_токен
export ADMIN_ID=твой_id
python bot.py
```
