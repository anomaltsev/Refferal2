
import os
import csv
import sqlite3
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# ----------------- CONFIG -----------------
API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@producersdelok")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
DB_PATH = "referrals.db"

LEVELS = [
    (3, "Мерч 🎁"),
    (10, "Худи или сертификат"),
    (25, "Умные весы или наушники"),
]

TOP_LIMIT = 20
SEASON_TOP_N_TO_SAVE = 3

# ----------------- LOGGING -----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("refbot")

if not API_TOKEN:
    log.error("BOT_TOKEN is not set in environment. Exiting.")
    raise SystemExit(1)

# ----------------- BOT CORE -----------------
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

def current_season() -> str:
    return datetime.utcnow().strftime("%Y-%m")

# ----------------- DB INIT -----------------
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

cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_referrals ON users(referrals_count)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_lifetime ON users(lifetime_referrals)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_season_winners_season ON season_winners(season)")
conn.commit()

# ----------------- DB UTILS -----------------
def get_user(tg_id: int):
    cursor.execute("SELECT tg_id, username, referrer_id, referrals_count, suspicious, lifetime_referrals FROM users WHERE tg_id=?",
                   (tg_id,))
    return cursor.fetchone()

def add_user(tg_id, username, referrer_id=None, suspicious=0):
    try:
        cursor.execute("INSERT INTO users (tg_id, username, referrer_id, suspicious) VALUES (?, ?, ?, ?)",
                       (tg_id, username, referrer_id, suspicious))
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

# ----------------- HANDLERS: PARTICIPANTS -----------------
@router.message(CommandStart(deep_link=True))
async def start_deeplink(msg: types.Message, command: CommandStart):
    user_id = msg.from_user.id
    referrer_id = int(command.args) if command.args and command.args.isdigit() else None

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if getattr(member, "status", "left") in ["left", "kicked"]:
            await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
            return
    except Exception as e:
        log.warning(f"get_chat_member failed: {e}")

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
    except Exception as e:
        log.warning(f"get_chat_member failed: {e}")

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

# ----------------- RUN -----------------
async def main():
    log.info("Bot starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
