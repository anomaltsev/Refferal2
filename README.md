# Referral Bot Final

## 🚀 Возможности
- Мини-капча при старте (антибот)
- Проверка подписки на канал
- Подсчёт друзей
- Подозрительные аккаунты (⚠️)
- /me — мои результаты
- /admin_stats — статистика
- /id @username — узнать user_id
- /adduser <tg_id> <username> <refs>
- /top — ТОП-20 участников
- /winners — победители по уровням (3, 10, 25) + ТОП-20 месяца
- /giveprize <id> <приз>
- /prizeslog — журнал призов
- /exportdb — скачать базу
- /importdb — загрузить базу
- /linkref <referrer_id> <referral_id>
- /referrals <tg_id> — список всех рефералов

## ⚙️ Запуск
```bash
pip install -r requirements.txt
export BOT_TOKEN=твой_токен
export ADMIN_ID=твой_id
python bot.py
```
