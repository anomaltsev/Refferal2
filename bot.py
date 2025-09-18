import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@producersdelok"   # канал для проверки подписки
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# --- база sqlite ---
conn = sqlite3.connect("referrals.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0
)
""")
conn.commit()

def add_user(tg_id, username, referrer_id=None):
    try:
        cursor.execute("INSERT INTO users (tg_id, username, referrer_id) VALUES (?, ?, ?)", 
                       (tg_id, username, referrer_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def increment_referrer(referrer_id):
    cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id=?", (referrer_id,))
    conn.commit()

# --- команды ---
@dp.message(CommandStart(deep_link=True))
async def start_deeplink(msg: types.Message, command: CommandStart):
    user_id = msg.from_user.id
    referrer_id = int(command.args) if command.args.isdigit() else None

    # проверка подписки
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if member.status in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return

    add_user(user_id, msg.from_user.username, referrer_id)
    if referrer_id and referrer_id != user_id:
        increment_referrer(referrer_id)

    link = f"https://t.me/{(await bot.me()).username}?start={user_id}"
    await msg.answer(f"Добро пожаловать! Делись этой ссылкой:\n{link}\n\n"
                     f"Смотри свои результаты через /me")

@dp.message(CommandStart())
async def start_plain(msg: types.Message):
    user_id = msg.from_user.id
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if member.status in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return

    add_user(user_id, msg.from_user.username)
    link = f"https://t.me/{(await bot.me()).username}?start={user_id}"
    await msg.answer(f"Привет! Делись этой ссылкой:\n{link}\n\n"
                     f"Смотри свои результаты через /me")

@dp.message(Command("me"))
async def me(msg: types.Message):
    user_id = msg.from_user.id
    cursor.execute("SELECT referrals_count FROM users WHERE tg_id=?", (user_id,))
    row = cursor.fetchone()
    count = row[0] if row else 0
    await msg.answer(f"Ты пригласил {count} друзей.\n\n"
                     f"Твоя ссылка: https://t.me/{(await bot.me()).username}?start={user_id}")

@dp.message(Command("admin_stats"))
async def admin_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*), SUM(referrals_count) FROM users")
    total_users, total_refs = cursor.fetchone()
    await msg.answer(f"👥 Пользователей: {total_users}\n"
                     f"🔗 Всего рефералов: {total_refs}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
