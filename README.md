# Referral Bot — Seasons Fix

Эта версия:
- Все хэндлеры переписаны под Router (корректный синтаксис Aiogram 3).
- /me показывает два счётчика (сезон + lifetime).
- /top — ТОП за всё время.
- /season_stats — ТОП текущего сезона.
- /winners — уровни (lifetime) + ТОП сезона.
- /season_close — завершает сезон, фиксирует победителей и сбрасывает сезонные счётчики.
- Сохранены все прошлые функции.

## Запуск
pip install -r requirements.txt
export BOT_TOKEN=<токен>
export ADMIN_ID=<id>
python bot.py
