
import os
import csv
import sqlite3
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# ========= НАСТРОЙКИ =========
API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@producersdelok")  # можно переопределить через переменные окружения
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
DB_PATH = "referrals.db"

# Призы за постоянные уровни (лайфтайм)
LEVELS = [
    (3, "Мерч 🎁"),
    (10, "Худи или сертификат"),
    (25, "Умные весы или наушники"),
]

TOP_LIMIT = 20            # сколько показывать в топах
SEASON_TOP_N_TO_SAVE = 3  # сколько победителей сохранять при закрытии сезона

# ========= ИНИЦ =========
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

def current_season() -> str:
    return datetime.utcnow().strftime("%Y-%m")

# ========= БД =========
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,   -- сезонные
    suspicious INTEGER DEFAULT 0,
    lifetime_referrals INTEGER DEFAULT 0 -- за всё время
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS prizes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    given_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS season_winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season TEXT,
    tg_id INTEGER,
    place INTEGER,
    referrals_count INTEGER,
    given_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS awarded_levels (
    tg_id INTEGER,
    level_threshold INTEGER,
    PRIMARY KEY (tg_id, level_threshold)
)
""")

# Индексы для ускорения
cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_referrals ON users(referrals_count)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_lifetime ON users(lifetime_referrals)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_season_winners_season ON season_winners(season)")
conn.commit()

# ========= УТИЛИТЫ БД =========
def get_user(tg_id: int):
    cursor.execute("SELECT tg_id, username, referrer_id, referrals_count, suspicious, lifetime_referrals FROM users WHERE tg_id=?", (tg_id,))
    return cursor.fetchone()

def add_user(tg_id, username, referrer_id=None, suspicious=0):
    try:
        cursor.execute(
            "INSERT INTO users (tg_id, username, referrer_id, suspicious) VALUES (?, ?, ?, ?)",
            (tg_id, username, referrer_id, suspicious)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def increment_referrer(referrer_id: int, delta: int = 1):
    cursor.execute("UPDATE users SET referrals_count = referrals_count + ?, lifetime_referrals = lifetime_referrals + ? WHERE tg_id=?",
                   (delta, delta, referrer_id))
    conn.commit()
    check_and_award_levels(referrer_id)

def check_and_award_levels(tg_id: int):
    cursor.execute("SELECT lifetime_referrals FROM users WHERE tg_id=?", (tg_id,))
    row = cursor.fetchone()
    lifetime = row[0] if row else 0
    for threshold, prize_name in LEVELS:
        if lifetime >= threshold:
            cursor.execute("SELECT 1 FROM awarded_levels WHERE tg_id=? AND level_threshold=?", (tg_id, threshold))
            already = cursor.fetchone()
            if not already:
                cursor.execute("INSERT INTO awarded_levels (tg_id, level_threshold) VALUES (?, ?)",
                               (tg_id, threshold))
                cursor.execute("INSERT INTO prizes (tg_id, prize) VALUES (?, ?)",
                               (tg_id, f"Приз за уровень {threshold}: {prize_name}"))
                conn.commit()

# ========= ОБЩИЕ ХЭНДЛЕРЫ =========
@router.message(CommandStart(deep_link=True))
async def start_deeplink(msg: types.Message, command: CommandStart):
    user_id = msg.from_user.id
    referrer_id = int(command.args) if command.args and command.args.isdigit() else None

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if getattr(member, "status", "left") in ["left", "kicked"]:
            await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
            return
    except Exception:
        # Если канал не доступен/приватный/не добавлен бот — пропускаем проверку, но лучше настроить канал
        pass

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:{referrer_id or 0}")
    ]])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

@router.message(CommandStart())
async def start_plain(msg: types.Message):
    user_id = msg.from_user.id
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if getattr(member, "status", "left") in ["left", "kicked"]:
            await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
            return
    except Exception:
        pass

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:0")
    ]])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

@router.callback_query(lambda c: c.data.startswith("captcha_ok"))
async def captcha_ok(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    referrer_id = int(parts[2]) if parts[2] != "0" else None
    user = callback.from_user

    existed = get_user(user_id)
    suspicious = 0
    if not user.username or not user.first_name:
        suspicious = 1

    add_user(user_id, user.username, referrer_id, suspicious)

    if not existed and referrer_id and referrer_id != user_id:
        increment_referrer(referrer_id)

    link = f"https://t.me/{(await bot.me()).username}?start={user_id}"
    await callback.message.answer(
        "✅ Спасибо, подтверждено!

"
        f"Твоя ссылка: {link}

"
        "Смотри прогресс через /me"
    )
    await callback.answer()

@router.message(Command("me"))
async def me(msg: types.Message):
    user_id = msg.from_user.id
    cursor.execute("SELECT referrals_count, lifetime_referrals FROM users WHERE tg_id=?", (user_id,))
    row = cursor.fetchone()
    season = row[0] if row else 0
    lifetime = row[1] if row else 0
    await msg.answer(
        f"👤 Твой прогресс:
"
        f"— За сезон: {season}
"
        f"— За всё время: {lifetime}

"
        f"Твоя ссылка: https://t.me/{(await bot.me()).username}?start={user_id}"
    )

# ========= АДМИН =========
@router.message(Command("whoami"))
async def whoami(msg: types.Message):
    await msg.answer(f"🔎 Твой Telegram ID: <code>{msg.from_user.id}</code>")

@router.message(Command("admin_stats"))
async def admin_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(referrals_count),0), COALESCE(SUM(lifetime_referrals),0) FROM users")
    total_users, total_refs_season, total_refs_lifetime = cursor.fetchone()
    await msg.answer(
        "📊 Статистика
"
        f"👥 Пользователей: {total_users}
"
        f"🔗 За сезон: {total_refs_season}
"
        f"🏁 За всё время: {total_refs_lifetime}"
    )

@router.message(Command("id"))
async def get_id(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Используй: /id @username")
        return
    username = parts[1].lstrip("@")
    cursor.execute("SELECT tg_id FROM users WHERE username=?", (username,))
    row = cursor.fetchone()
    if row:
        await msg.answer(f"👤 @{username} → <code>{row[0]}</code>")
    else:
        await msg.answer(f"Пользователь @{username} не найден в базе.")

@router.message(Command("adduser"))
async def adduser_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 4:
        await msg.answer("Используй: /adduser <tg_id> <username> <refs>  (refs применятся и к сезону, и к лайфтайму)")
        return
    tg_id = int(parts[1])
    username = parts[2]
    refs = int(parts[3])
    cursor.execute("""
        INSERT INTO users (tg_id, username, referrals_count, lifetime_referrals, suspicious)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(tg_id) DO UPDATE SET
          username=excluded.username,
          referrals_count=excluded.referrals_count,
          lifetime_referrals=excluded.lifetime_referrals
    """, (tg_id, username, refs, refs))
    conn.commit()
    check_and_award_levels(tg_id)
    await msg.answer(f"✅ Пользователь {username} ({tg_id}) установлен: сезон={refs}, всего={refs}.")

@router.message(Command("linkref"))
async def linkref(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("Используй: /linkref <referrer_id> <referral_id>")
        return
    referrer_id = int(parts[1])
    referral_id = int(parts[2])
    cursor.execute("UPDATE users SET referrer_id=? WHERE tg_id=?", (referrer_id, referral_id))
    conn.commit()
    increment_referrer(referrer_id, delta=1)
    await msg.answer(f"✅ Пользователь {referral_id} отмечен как реферал {referrer_id}")

@router.message(Command("referrals"))
async def referrals(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Используй: /referrals <tg_id>")
        return
    tg_id = int(parts[1])
    cursor.execute("SELECT tg_id, username FROM users WHERE referrer_id=?", (tg_id,))
    rows = cursor.fetchall()
    if not rows:
        await msg.answer(f"У {tg_id} нет рефералов.")
        return
    text = f"👥 Рефералы пользователя {tg_id}:
"
    for ref_id, username in rows[:100]:
        name = f"@{username}" if username else f"id:{ref_id}"
        text += f" - {name}
"
    if len(rows) > 100:
        text += f"
… и ещё {len(rows)-100}"
    await msg.answer(text)

@router.message(Command("top"))
async def top(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT username, tg_id, lifetime_referrals FROM users ORDER BY lifetime_referrals DESC LIMIT ?", (TOP_LIMIT,))
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Пока нет участников.")
        return
    text = f"🏆 ТОП-{TOP_LIMIT} (за всё время):

"
    for i, (username, tg_id, refs) in enumerate(rows, start=1):
        name = f"@{username}" if username else f"id:{tg_id}"
        text += f"{i}. {name} — {refs} всего
"
    await msg.answer(text)

@router.message(Command("season_stats"))
async def season_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_LIMIT,))
    rows = cursor.fetchall()
    text = f"📅 Сезон {season} — ТОП-{TOP_LIMIT}:

"
    if rows:
        for i, (username, tg_id, refs) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            text += f"{i}. {name} — {refs} за сезон
"
    else:
        text += "Пока пусто."
    await msg.answer(text)

@router.message(Command("winners"))
async def winners(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    # Победители уровней по лайфтайму
    text = "🎁 Победители по уровням (за всё время):

"
    for threshold, prize in LEVELS:
        cursor.execute("SELECT username, tg_id, lifetime_referrals FROM users WHERE lifetime_referrals >= ? ORDER BY lifetime_referrals DESC", (threshold,))
        rows = cursor.fetchall()
        text += f"— Уровень {threshold}+ ({prize}):
"
        if rows:
            for username, tg_id, refs in rows:
                name = f"@{username}" if username else f"id:{tg_id}"
                text += f"   {name} — {refs} всего
"
        else:
            text += "   (пока пусто)
"
        text += "
"
    # Текущий сезонный ТОП
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_LIMIT,))
    rows = cursor.fetchall()
    text += f"🏁 Текущий сезон {season} — ТОП-{TOP_LIMIT}:
"
    if rows:
        for i, (username, tg_id, refs) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            text += f"{i}. {name} — {refs} за сезон
"
    else:
        text += "   (пока пусто)
"
    await msg.answer(text)

@router.message(Command("season_close"))
async def season_close(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    season = current_season()
    cursor.execute("SELECT tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (SEASON_TOP_N_TO_SAVE,))
    winners = cursor.fetchall()
    if not winners:
        await msg.answer(f"Сезон {season}: нет данных для закрытия.")
        return
    for place, (tg_id, refs) in enumerate(winners, start=1):
        cursor.execute("INSERT INTO season_winners (season, tg_id, place, referrals_count) VALUES (?, ?, ?, ?)",
                       (season, tg_id, place, refs))
    conn.commit()
    cursor.execute("UPDATE users SET referrals_count = 0")
    conn.commit()
    text = f"✅ Сезон {season} закрыт. Победители:
"
    for place, (tg_id, refs) in enumerate(winners, start=1):
        cursor.execute("SELECT username FROM users WHERE tg_id=?", (tg_id,))
        row = cursor.fetchone()
        name = f"@{row[0]}" if row and row[0] else f"id:{tg_id}"
        text += f"{place}. {name} — {refs} за сезон
"
    text += "
Сезонные счётчики обнулены."
    await msg.answer(text)

@router.message(Command("season_winners"))
async def season_winners(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT season, tg_id, place, referrals_count, given_at FROM season_winners ORDER BY given_at DESC LIMIT 30")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Пока нет сохранённых сезонов.")
        return
    text = "🏅 Архив победителей сезонов (последние 30 записей):

"
    for season, tg_id, place, refs, given_at in rows:
        cursor.execute("SELECT username FROM users WHERE tg_id=?", (tg_id,))
        row = cursor.fetchone()
        name = f"@{row[0]}" if row and row[0] else f"id:{tg_id}"
        text += f"{season} — место {place}: {name} ({refs}) • {given_at}
"
    await msg.answer(text)

@router.message(Command("giveprize"))
async def giveprize(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Используй: /giveprize <tg_id|@username> <название приза>")
        return
    target = parts[1]
    if target.startswith("@"):
        username = target.lstrip("@")
        cursor.execute("SELECT tg_id FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        if not row:
            await msg.answer(f"❌ Пользователь @{username} не найден в базе. Сначала добавь /adduser.")
            return
        tg_id = int(row[0])
    else:
        try:
            tg_id = int(target)
        except ValueError:
            await msg.answer("❌ Укажи корректный tg_id или @username.")
            return
    prize = parts[2].strip()
    try:
        cursor.execute("INSERT INTO prizes (tg_id, prize) VALUES (?, ?)", (tg_id, prize))
        conn.commit()
        await msg.answer(f"✅ Приз «{prize}» отмечен для пользователя {tg_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка при записи приза: {e}")

@router.message(Command("prizeslog"))
async def prizeslog(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT tg_id, prize, given_at FROM prizes ORDER BY given_at DESC LIMIT 50")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Журнал пока пуст.")
        return
    text = "📂 Журнал призов (последние 50):

"
    for tg_id, prize, given_at in rows:
        text += f"👤 {tg_id} — {prize} ({given_at})
"
    await msg.answer(text)

@router.message(Command("exportdb"))
async def exportdb(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    if not os.path.exists(DB_PATH):
        await msg.answer("❌ Файл базы не найден.")
        return
    if os.path.getsize(DB_PATH) == 0:
        await msg.answer("❌ Файл базы пустой.")
        return
    try:
        file = FSInputFile(DB_PATH, filename="referrals.db")
        await msg.answer_document(file)
    except Exception as e:
        await msg.answer(f"❌ Ошибка при экспорте: {e}")

@router.message(Command("importdb"))
async def importdb(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.answer("Пришли файл referrals.db и ответь на него командой /importdb")
        return
    doc = msg.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await msg.answer("❌ Это не .db файл.")
        return
    try:
        # Закрываем текущее соединение, записываем новый файл
        global conn, cursor
        try:
            conn.close()
        except Exception:
            pass
        file = await bot.get_file(doc.file_id)
        downloaded = await bot.download_file(file.file_path)
        with open(DB_PATH, "wb") as f:
            f.write(downloaded.read())
        await msg.answer("✅ База успешно импортирована. Перезапусти бота.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка при импорте: {e}")

# ========= ВЫГРУЗКИ СПИСКОВ =========
@router.message(Command("all_users"))
async def all_users(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    page = 1
    if len(parts) >= 2 and parts[1].isdigit():
        page = max(1, int(parts[1]))
    per_page = 50
    offset = (page - 1) * per_page
    cursor.execute("SELECT tg_id, username, referrals_count, lifetime_referrals FROM users ORDER BY tg_id LIMIT ? OFFSET ?", (per_page, offset))
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Список пуст или страница вне диапазона.")
        return
    text = f"👥 Все участники — страница {page}:

"
    for tg_id, username, season, lifetime in rows:
        name = f"@{username}" if username else f"id:{tg_id}"
        text += f"{name} — сезон: {season}, всего: {lifetime}
"
    text += f"
Используй: /all_users <страница> (по {per_page} на страницу)"
    await msg.answer(text)

@router.message(Command("export_users"))
async def export_users(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT tg_id, username, referrer_id, referrals_count, lifetime_referrals, suspicious FROM users")
    rows = cursor.fetchall()
    fname = "users.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tg_id", "username", "referrer_id", "season_refs", "lifetime_refs", "suspicious"])
        writer.writerows(rows)
    await msg.answer_document(FSInputFile(fname))

# ========= RUN =========
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
