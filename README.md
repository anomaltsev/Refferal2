# Referral Bot (Telegram)

## 🚀 Возможности
- Реферальные ссылки (`t.me/bot?start=userid`)
- Проверка обязательной подписки на канал
- Подсчёт друзей
- Команда /me для участника
- Команда /admin_stats для администратора
- Команда /top - ТОП-20 участников
- Команда /winners - список заслуживших призы
- Команда /giveprize <user_id> <название> - отметить вручение приза
- Команда /prizeslog - журнал выданных призов

## ⚙️ Запуск локально
```bash
pip install -r requirements.txt
export BOT_TOKEN=твой_токен
export ADMIN_ID=твой_id
python bot.py
```

## ☁️ Запуск на Render
1. Создай репозиторий на GitHub и залей эти файлы.
2. На [Render](https://render.com) → New Background Worker → подключи репозиторий.
3. Build Command:
```bash
pip install -r requirements.txt
```
4. Start Command:
```bash
python bot.py
```
5. В Settings → Environment добавь переменные:
   - BOT_TOKEN=твой_токен
   - ADMIN_ID=твой_id

Render сам поднимет сервер и будет держать бота онлайн 24/7.
