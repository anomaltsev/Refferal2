# Referral Bot — FINAL (Seasons + Levels + Export/Import + CSV)

Готовая версия со всеми командами и фиксом под Aiogram 3 (Router).

## Участники
/start — капча + проверка подписки
/me — сезонные и лайфтайм рефералы + ссылка

## Админ
/whoami — твой ID
/admin_stats — агрегированная статистика
/id @username — узнать tg_id по username (если есть в базе)
/adduser <id> <username> <refs> — добавить/обновить пользователя (и сезон, и лайфтайм), автопроверка уровней
/linkref <referrer_id> <referral_id> — связать и добавить +1 пригласившему
/referrals <tg_id> — список рефералов пользователя
/top — ТОП-20 по лайфтайму
/season_stats — ТОП-20 текущего сезона
/winners — уровни (lifetime) + текущий ТОП сезона
/season_close — закрыть сезон: сохранить ТОП-3 и обнулить сезонные счётчики
/season_winners — архив победителей сезонов (последние 30 записей)
/giveprize <tg_id|@username> <приз> — вручить приз
/prizeslog — журнал призов
/exportdb — прислать referrals.db
/importdb — в ответ на файл .db заменить базу (после — рестарт)
/all_users [страница] — посмотреть всех участников постранично (по 50)
/export_users — выгрузить всех участников в CSV

## Запуск
pip install -r requirements.txt
export BOT_TOKEN=<токен>
export ADMIN_ID=<id>
# (опционально) export CHANNEL_ID=@твойдляпроверки
python bot.py
