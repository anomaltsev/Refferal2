
import os
import sqlite3
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

API_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@producersdelok"   # канал для проверки подписки
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB_PATH = "referrals.db"

# === Константы программы ===
# Постоянные уровни (по ЛАЙФТАЙМ-приглашениям)
LEVELS = [
    (3, "Мерч 🎁"),
    (10, "Худи или сертификат"),
    (25, "Умные весы или наушники")
]
TOP_SEASON_LIMIT = 20  # сколько показывать в /season_stats и внизу /winners
SEASON_TOP_N_TO_SAVE = 3  # сколько сохранять как победителей сезона при /season_close

def current_season() -> str:
    # Формат, удобный для сортировки и чтения
    return datetime.utcnow().strftime("%Y-%m")

# === БАЗА ===
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Базовые таблицы
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,    -- СЕЗОННЫЕ приглашения
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

# Миграции: добавим lifetime_referrals, если нет
def ensure_column(table, coldef):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # колонка уже есть

ensure_column("users", "lifetime_referrals INTEGER DEFAULT 0")

# Таблица для сезонных победителей
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
conn.commit()

# Таблица фиксации выданных уровней (чтобы не дублировать награды за один и тот же порог)
cursor.execute("""
CREATE TABLE IF NOT EXISTS awarded_levels (
    tg_id INTEGER,
    level_threshold INTEGER,
    PRIMARY KEY (tg_id, level_threshold)
)
""")
conn.commit()

# === Утилиты БД ===
def get_user(tg_id: int):
    cursor.execute("SELECT tg_id, username, referrer_id, referrals_count, suspicious, lifetime_referrals FROM users WHERE tg_id=?", (tg_id,))
    return cursor.fetchone()

def add_user(tg_id, username, referrer_id=None, suspicious=0):
    # Вставляем, если нет; если есть — не трогаем (капча может жаться повторно)
    try:
        cursor.execute(
            "INSERT INTO users (tg_id, username, referrer_id, suspicious) VALUES (?, ?, ?, ?)",
            (tg_id, username, referrer_id, suspicious)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def increment_referrer(referrer_id: int, delta: int = 1):
    # Увеличиваем сезонные и лайфтайм счётчики и проверяем уровни
    cursor.execute("UPDATE users SET referrals_count = referrals_count + ?, lifetime_referrals = lifetime_referrals + ? WHERE tg_id=?",
                   (delta, delta, referrer_id))
    conn.commit()
    check_and_award_levels(referrer_id)

def check_and_award_levels(tg_id: int):
    # Автовыдача призов за уровни на основе ЛАЙФТАЙМ-приглашений
    cursor.execute("SELECT lifetime_referrals FROM users WHERE tg_id=?", (tg_id,))
    row = cursor.fetchone()
    lifetime = row[0] if row else 0
    for threshold, prize_name in LEVELS:
        if lifetime >= threshold:
            # Проверяем, не выдавали ли уже
            cursor.execute("SELECT 1 FROM awarded_levels WHERE tg_id=? AND level_threshold=?", (tg_id, threshold))
            already = cursor.fetchone()
            if not already:
                # Фиксируем в awarded_levels и пишем в prizes понятной строкой
                cursor.execute("INSERT INTO awarded_levels (tg_id, level_threshold) VALUES (?, ?)", (tg_id, threshold))
                cursor.execute("INSERT INTO prizes (tg_id, prize) VALUES (?, ?)", (tg_id, f"Автоматический приз за уровень {threshold}: {prize_name}"))
                conn.commit()

# === Команды участников ===
@dp.message(CommandStart(deep_link=True))
async def start_deeplink(msg: types.Message, command: CommandStart):
    user_id = msg.from_user.id
    referrer_id = int(command.args) if command.args and command.args.isdigit() else None

    # проверка подписки
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if getattr(member, "status", "left") in ["left", "kicked"]:
        await msg.answer(f"Чтобы участвовать, подпишись на {CHANNEL_ID} и снова нажми /start")
        return

    # Мини-капча
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я не бот 🟢", callback_data=f"captcha_ok:{user_id}:{referrer_id or 0}")]
    ])
    await msg.answer("Перед началом подтвердите, что вы человек:", reply_markup=keyboard)

@dp.message(CommandStart())
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

@dp.callback_query(lambda c: c.data.startswith("captcha_ok"))
async def captcha_ok(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    referrer_id = int(parts[2]) if parts[2] != "0" else None
    user = callback.from_user

    # Повторное нажатие капчи не должно дублировать регистрации
    existed = get_user(user_id)

    # Проверка профиля (username и имя)
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

@dp.message(Command("me"))
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

# === Утилиты для админа ===
def admin_only(user_id: int) -> bool:
    return user_id == ADMIN_ID

@dp.message(Command("whoami"))
async def whoami(msg: types.Message):
    await msg.answer(f"🔎 Твой Telegram ID: <code>{msg.from_user.id}</code>")

@dp.message(Command("admin_stats"))
async def admin_stats(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(referrals_count),0), COALESCE(SUM(suspicious),0), COALESCE(SUM(lifetime_referrals),0) FROM users")
    total_users, total_refs_season, suspicious_count, total_refs_lifetime = cursor.fetchone()
    await msg.answer(
        "📊 Статистика\n"
        f"👥 Пользователей: {total_users}\n"
        f"🔗 Рефералов за сезон: {total_refs_season}\n"
        f"🏁 Рефералов за всё время: {total_refs_lifetime}\n"
        f"⚠️ Подозрительных: {suspicious_count}"
    )

@dp.message(Command("id"))
async def get_id(msg: types.Message):
    if not admin_only(msg.from_user.id):
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

@dp.message(Command("adduser"))
async def adduser_cmd(msg: types.Message):
    if not admin_only(msg.from_user.id):
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

# === Списки и победители ===
@dp.message(Command("top"))
async def top(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    # ТОП по лайфтайму
    cursor.execute("SELECT username, tg_id, lifetime_referrals, suspicious FROM users ORDER BY lifetime_referrals DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Пока нет участников.")
        return
    text = "🏆 ТОП-20 (за всё время):\n\n"
    for i, (username, tg_id, refs, suspicious) in enumerate(rows, start=1):
        name = f"@{username}" if username else f"id:{tg_id}"
        if suspicious:
            name += " ⚠️"
        text += f"{i}. {name} — {refs} всего\n"
    await msg.answer(text)

@dp.message(Command("season_stats"))
async def season_stats(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count, suspicious FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_SEASON_LIMIT,))
    rows = cursor.fetchall()
    text = f"📅 Сезон {season} — ТОП-{TOP_SEASON_LIMIT}:\n\n"
    if rows:
        for i, (username, tg_id, refs, suspicious) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            if suspicious:
                name += " ⚠️"
            text += f"{i}. {name} — {refs} за сезон\n"
    else:
        text += "Пока пусто."
    await msg.answer(text)

@dp.message(Command("winners"))
async def winners(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    # Победители уровней по ЛАЙФТАЙМ
    text = "🎁 Победители по постоянным уровням (за всё время):\n\n"
    for threshold, prize in LEVELS:
        cursor.execute("SELECT username, tg_id, lifetime_referrals, suspicious FROM users WHERE lifetime_referrals >= ? ORDER BY lifetime_referrals DESC", (threshold,))
        rows = cursor.fetchall()
        text += f"— Уровень {threshold}+ ({prize}):\n"
        if rows:
            for username, tg_id, refs, suspicious in rows:
                name = f"@{username}" if username else f"id:{tg_id}"
                if suspicious:
                    name += " ⚠️"
                text += f"   {name} — {refs} всего\n"
        else:
            text += "   (пока пусто)\n"
        text += "\n"

    # ТОП-20 сезона внизу
    season = current_season()
    cursor.execute("SELECT username, tg_id, referrals_count, suspicious FROM users ORDER BY referrals_count DESC LIMIT ?", (TOP_SEASON_LIMIT,))
    rows = cursor.fetchall()
    text += f"🏁 Текущий сезон {season} — ТОП-{TOP_SEASON_LIMIT}:\n"
    if rows:
        for i, (username, tg_id, refs, suspicious) in enumerate(rows, start=1):
            name = f"@{username}" if username else f"id:{tg_id}"
            if suspicious:
                name += " ⚠️"
            text += f"{i}. {name} — {refs} за сезон\n"
    else:
        text += "   (пока пусто)\n"
    await msg.answer(text)

# === Призы ===
@dp.message(Command("giveprize"))
async def giveprize(msg: types.Message):
    if not admin_only(msg.from_user.id):
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

@dp.message(Command("prizeslog"))
async def prizeslog(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    cursor.execute("SELECT tg_id, prize, given_at FROM prizes ORDER BY given_at DESC LIMIT 20")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Журнал пока пуст.")
        return
    text = "📂 Журнал призов (последние 20):\n\n"
    for tg_id, prize, given_at in rows:
        text += f"👤 {tg_id} — {prize} ({given_at})\n"
    await msg.answer(text)

# === Бэкапы базы ===
@dp.message(Command("exportdb"))
async def exportdb(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    try:
        if not os.path.exists(DB_PATH):
            await msg.answer("❌ Файл базы не найден.")
            return
        size = os.path.getsize(DB_PATH)
        if size == 0:
            await msg.answer("❌ Файл базы пустой (0 байт).")
            return
        await msg.answer_document(FSInputFile(DB_PATH))
    except Exception as e:
        await msg.answer(f"❌ Ошибка при экспорте: {e}")

@dp.message(Command("importdb"))
async def importdb(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.answer("Пришли файл referrals.db и ответь на него командой /importdb")
        return
    doc = msg.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await msg.answer("❌ Это не .db файл. Пришли именно referrals.db")
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
        await msg.answer("✅ База данных заменена. Перезапусти бота, чтобы изменения вступили в силу.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка при импорте: {e}")

# === Связи и рефералы ===
@dp.message(Command("linkref"))
async def linkref(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("Используй: /linkref <referrer_id> <referral_id>")
        return
    referrer_id = int(parts[1])
    referral_id = int(parts[2])
    cursor.execute("UPDATE users SET referrer_id=? WHERE tg_id=?", (referrer_id, referral_id))
    conn.commit()
    # Увеличиваем счётчики за реферала и проверяем уровни
    increment_referrer(referrer_id, delta=1)
    await msg.answer(f"✅ Пользователь {referral_id} отмечен как реферал {referrer_id}")

@dp.message(Command("referrals"))
async def referrals(msg: types.Message):
    if not admin_only(msg.from_user.id):
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

# === Сезоны ===
@dp.message(Command("season_stats"))
async def cmd_season_stats(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    await season_stats(msg)  # используем ту же логику

@dp.message(Command("season_close"))
async def season_close(msg: types.Message):
    if not admin_only(msg.from_user.id):
        return
    season = current_season()

    # Получим ТОП по сезону и сохраним первых N
    cursor.execute("SELECT tg_id, referrals_count FROM users ORDER BY referrals_count DESC LIMIT ?", (SEASON_TOP_N_TO_SAVE,))
    winners = cursor.fetchall()

    if not winners:
        await msg.answer(f"Сезон {season}: нет данных для закрытия.")
        return

    for place, (tg_id, refs) in enumerate(winners, start=1):
        cursor.execute("INSERT INTO season_winners (season, tg_id, place, referrals_count) VALUES (?, ?, ?, ?)",
                       (season, tg_id, place, refs))
    conn.commit()

    # Сброс сезонных счётчиков
    cursor.execute("UPDATE users SET referrals_count = 0")
    conn.commit()

    # Итоговый отчёт
    text = f"✅ Сезон {season} закрыт. Победители:
"
    for place, (tg_id, refs) in enumerate(winners, start=1):
        # покажем username если есть
        cursor.execute("SELECT username FROM users WHERE tg_id=?", (tg_id,))
        row = cursor.fetchone()
        name = f"@{row[0]}" if row and row[0] else f"id:{tg_id}"
        text += f"{place}. {name} — {refs} за сезон
"
    text += "\nСезонные счётчики обнулены. Новый сезон начался!"
    await msg.answer(text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
