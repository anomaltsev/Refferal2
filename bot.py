
import os
import sqlite3
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@producersdelok"
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

DB_PATH = "referrals.db"

LEVELS = [
    (3, "Мерч 🎁"),
    (10, "Худи или сертификат"),
    (25, "Умные весы или наушники")
]
TOP_SEASON_LIMIT = 20
SEASON_TOP_N_TO_SAVE = 3

def current_season() -> str:
    return datetime.utcnow().strftime("%Y-%m")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    suspicious INTEGER DEFAULT 0,
    lifetime_referrals INTEGER DEFAULT 0
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
conn.commit()

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
                cursor.execute("INSERT INTO awarded_levels (tg_id, level_threshold) VALUES (?, ?)", (tg_id, threshold))
                cursor.execute("INSERT INTO prizes (tg_id, prize) VALUES (?, ?)", (tg_id, f"Приз за уровень {threshold}: {prize_name}"))
                conn.commit()

@router.message(CommandStart(deep_link=True))
async def start_deeplink(msg: types.Message, command: CommandStart):
    user_id = msg.from_user.id
    referrer_id = int(command.args) if command.args and command.args.isdigit() else None
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if getattr(member, "status", "left") in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:{referrer_id or 0}")
    ]])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

@router.message(CommandStart())
async def start_plain(msg: types.Message):
    user_id = msg.from_user.id
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if getattr(member, "status", "left") in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return
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
        "✅ Спасибо, подтверждено!\n\n"
        f"Твоя ссылка: {link}\n\n"
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
        f"👤 Твой прогресс:\n"
        f"— За сезон: {season}\n"
        f"— За всё время: {lifetime}\n\n"
        f"Твоя ссылка: https://t.me/{(await bot.me()).username}?start={user_id}"
    )

@router.message(Command("admin_stats"))
async def admin_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(referrals_count),0), COALESCE(SUM(lifetime_referrals),0) FROM users")
    total_users, total_refs_season, total_refs_lifetime = cursor.fetchone()
    await msg.answer(
        "📊 Статистика\n"
        f"👥 Пользователей: {total_users}\n"
        f"🔗 За сезон: {total_refs_season}\n"
        f"🏁 За всё время: {total_refs_lifetime}"
    )

@router.message(Command("top"))
async def top(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT username, tg_id, lifetime_referrals FROM users ORDER BY lifetime_referrals DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Пока нет участников.")
        return
    text = "🏆 ТОП-20 (за всё время):\n\n"
    for i, (username, tg_id, refs) in enumerate(rows, start=1):
        name = f"@{username}" if username else f"id:{tg_id}"
        text += f"{i}. {name} — {refs} всего\n"
    await msg.answer(text)

@router.message(Command("season_stats"))
async def season_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_SEASON_LIMIT,))
    rows = cursor.fetchall()
    text = f"📅 Сезон {season} — ТОП-{TOP_SEASON_LIMIT}:\n\n"
    if rows:
        for i, (username, tg_id, refs) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            text += f"{i}. {name} — {refs} за сезон\n"
    else:
        text += "Пока пусто."
    await msg.answer(text)

@router.message(Command("winners"))
async def winners(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    text = "🎁 Победители по уровням (лайфтайм):\n\n"
    for threshold, prize in LEVELS:
        cursor.execute("SELECT username, tg_id, lifetime_referrals FROM users WHERE lifetime_referrals >= ? ORDER BY lifetime_referrals DESC", (threshold,))
        rows = cursor.fetchall()
        text += f"— Уровень {threshold}+ ({prize}):\n"
        if rows:
            for username, tg_id, refs in rows:
                name = f"@{username}" if username else f"id:{tg_id}"
                text += f"   {name} — {refs} всего\n"
        else:
            text += "   (пока пусто)\n"
        text += "\n"
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_SEASON_LIMIT,))
    rows = cursor.fetchall()
    text += f"🏁 Текущий сезон {season} — ТОП-{TOP_SEASON_LIMIT}:\n"
    if rows:
        for i, (username, tg_id, refs) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            text += f"{i}. {name} — {refs} за сезон\n"
    else:
        text += "   (пока пусто)\n"
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
        cursor.execute("INSERT INTO season_winners (season, tg_id, place, referrals_count) VALUES (?, ?, ?, ?)", (season, tg_id, place, refs))
    conn.commit()
    cursor.execute("UPDATE users SET referrals_count = 0")
    conn.commit()
    text = f"✅ Сезон {season} закрыт. Победители:\n"
    for place, (tg_id, refs) in enumerate(winners, start=1):
        cursor.execute("SELECT username FROM users WHERE tg_id=?", (tg_id,))
        row = cursor.fetchone()
        name = f"@{row[0]}" if row and row[0] else f"id:{tg_id}"
        text += f"{place}. {name} — {refs} за сезон\n"
    text += "\nСезонные счётчики обнулены."
    await msg.answer(text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
