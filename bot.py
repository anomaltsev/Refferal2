import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@producersdelok"   # канал для проверки подписки
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- база sqlite ---
conn = sqlite3.connect("referrals.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    suspicious INTEGER DEFAULT 0
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
conn.commit()

def add_user(tg_id, username, referrer_id=None, suspicious=0):
    try:
        cursor.execute("INSERT INTO users (tg_id, username, referrer_id, suspicious) VALUES (?, ?, ?, ?)", 
                       (tg_id, username, referrer_id, suspicious))
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

    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if member.status in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:{referrer_id or 0}")]
    ])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("captcha_ok"))
async def captcha_ok(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    referrer_id = int(parts[2]) if parts[2] != "0" else None
    user = callback.from_user

    suspicious = 0
    if not user.username or not user.first_name:
        suspicious = 1

    add_user(user_id, user.username, referrer_id, suspicious)
    if referrer_id and referrer_id != user_id:
        increment_referrer(referrer_id)

    link = f"https://t.me/{(await bot.me()).username}?start={user_id}"
    await callback.message.answer(f"✅ Спасибо, подтверждено!\n\n"
                                  f"Твоя ссылка: {link}\n\n"
                                  f"Смотри прогресс через /me")
    await callback.answer()

@dp.message(CommandStart())
async def start_plain(msg: types.Message):
    user_id = msg.from_user.id
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if member.status in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:0")]
    ])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

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
    cursor.execute("SELECT COUNT(*), SUM(referrals_count), SUM(suspicious) FROM users")
    total_users, total_refs, suspicious_count = cursor.fetchone()
    await msg.answer(f"👥 Пользователей: {total_users}\n"
                     f"🔗 Всего рефералов: {total_refs}\n"
                     f"⚠️ Подозрительных: {suspicious_count}")

@dp.message(Command("id"))
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
        await msg.answer(f"👤 @{username} → {row[0]}")
    else:
        await msg.answer(f"Пользователь @{username} не найден в базе.")

@dp.message(Command("adduser"))
async def adduser_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split()
    if len(parts) < 4:
        await msg.answer("Используй: /adduser <tg_id> <username> <refs>")
        return
    tg_id = int(parts[1])
    username = parts[2]
    referrals = int(parts[3])

    cursor.execute("""
    INSERT INTO users (tg_id, username, referrals_count, suspicious)
    VALUES (?, ?, ?, 0)
    ON CONFLICT(tg_id) DO UPDATE SET
        username=excluded.username,
        referrals_count=excluded.referrals_count
    """, (tg_id, username, referrals))
    conn.commit()

    await msg.answer(f"✅ Пользователь {username} ({tg_id}) установлен с {referrals} приглашениями.")

@dp.message(Command("top"))
async def top(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT username, tg_id, referrals_count, suspicious FROM users ORDER BY referrals_count DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Пока нет участников.")
        return
    text = "🏆 ТОП-20 участников:\n\n"
    for i, (username, tg_id, refs, suspicious) in enumerate(rows, start=1):
        name = f"@{username}" if username else f"id:{tg_id}"
        if suspicious:
            name += " ⚠️"
        text += f"{i}. {name} — {refs} приглашённых\n"
    await msg.answer(text)

@dp.message(Command("winners"))
async def winners(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    text = "🎁 Победители по уровням:\n\n"
    levels = [(3, "Мерч 🎁"), (10, "Худи или сертификат"), (25, "Умные весы или наушники")]
    for threshold, prize in levels:
        cursor.execute("SELECT username, tg_id, referrals_count, suspicious FROM users WHERE referrals_count >= ? ORDER BY referrals_count DESC", (threshold,))
        rows = cursor.fetchall()
        text += f"— Уровень {threshold}+ ({prize}):\n"
        if rows:
            for username, tg_id, refs, suspicious in rows:
                name = f"@{username}" if username else f"id:{tg_id}"
                if suspicious:
                    name += " ⚠️"
                text += f"   {name} — {refs} приглашённых\n"
        else:
            text += "   (пока пусто)\n"
        text += "\n"

    cursor.execute("SELECT username, tg_id, referrals_count, suspicious FROM users ORDER BY referrals_count DESC LIMIT 20")
    rows = cursor.fetchall()
    text += "🏆 ТОП-20 месяца:\n"
    if rows:
        for i, (username, tg_id, refs, suspicious) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            if suspicious:
                name += " ⚠️"
            text += f"{i}. {name} — {refs} приглашённых\n"
    else:
        text += "   (пока пусто)\n"
    await msg.answer(text)

@dp.message(Command("giveprize"))
async def giveprize(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Используй: /giveprize <user_id> <название приза>")
        return
    tg_id = int(parts[1])
    prize = parts[2]
    cursor.execute("INSERT INTO prizes (tg_id, prize) VALUES (?, ?)",
                   (tg_id, prize))
    conn.commit()
    await msg.answer(f"✅ Приз «{prize}» отмечен для пользователя {tg_id}")

@dp.message(Command("prizeslog"))
async def prizeslog(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT tg_id, prize, given_at FROM prizes ORDER BY given_at DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Журнал пока пуст.")
        return
    text = "📂 Журнал призов:\n\n"
    for tg_id, prize, given_at in rows:
        text += f"👤 {tg_id} — {prize} ({given_at})\n"
    await msg.answer(text)

@dp.message(Command("exportdb"))
async def exportdb(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        await msg.answer_document(open("referrals.db", "rb"))
    except Exception as e:
        await msg.answer(f"Ошибка при экспорте: {e}")

@dp.message(Command("importdb"))
async def importdb(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.answer("Пришли файл referrals.db и ответь на него командой /importdb")
        return
    file = await bot.get_file(msg.reply_to_message.document.file_id)
    downloaded = await bot.download_file(file.file_path)
    with open("referrals.db", "wb") as f:
        f.write(downloaded.read())
    await msg.answer("✅ База данных заменена на загруженную. Перезапусти бота.")

@dp.message(Command("linkref"))
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
    cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id=?", (referrer_id,))
    conn.commit()
    await msg.answer(f"✅ Пользователь {referral_id} отмечен как реферал {referrer_id}")

@dp.message(Command("referrals"))
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
    text = f"👥 Рефералы пользователя {tg_id}:\n"
    for ref_id, username in rows:
        name = f"@{username}" if username else f"id:{ref_id}"
        text += f" - {name}\n"
    await msg.answer(text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
