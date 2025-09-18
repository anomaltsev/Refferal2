# Referral Bot — Seasons + Levels (Final)

В этой версии добавлены:
- **Постоянные уровни** (3 / 10 / 25) по *лайфтайм*-приглашениям с **автовыдачей призов** (таблица `awarded_levels` + запись в `prizes`).
- **Сезоны** (месяц как `YYYY-MM`):
  - `/season_stats` — ТОП сезона (по `referrals_count`).
  - `/season_close` — сохраняет ТОП-3 в `season_winners` и **обнуляет сезонные** счётчики. Лайфтайм не трогается.
- Разделены метрики: `referrals_count` (сезон) и `lifetime_referrals` (за всё время).
- Все прежние функции сохранены (капча, антибот ⚠️, winners, top, giveprize, prizeslog, export/import, adduser, linkref, referrals).

## Команды админа
- `/admin_stats` — пользователи, сезонные рефералы, лайфтайм рефералы, подозрительные.
- `/top` — ТОП-20 за всё время (lifetime).
- `/season_stats` — ТОП сезона.
- `/winners` — победители постоянных уровней + ТОП сезона.
- `/giveprize <tg_id|@username> <приз>` — вручить приз; лог см. `/prizeslog`.
- `/exportdb` / `/importdb` (ответом на файл `referrals.db`). После импорта нужен рестарт.
- `/adduser <id> <username> <refs>` — поставить значения и для сезона, и для лайфтайма (и пересчитать уровни).
- `/linkref <referrer_id> <referral_id>` — связать и инкрементировать счётчики.
- `/referrals <tg_id>` — список всех рефералов.

## Запуск
```
pip install -r requirements.txt
export BOT_TOKEN=<токен>
export ADMIN_ID=<твой id>
python bot.py
```

## Примечания
- Уровни считаются по `lifetime_referrals`, сезоны — по `referrals_count`.
- Автовыдача призов за уровни происходит при росте счётчика (авторефералы, `/linkref`, `/adduser`).
- Если используешь Render, следи, чтобы работал **один инстанс** бота.
