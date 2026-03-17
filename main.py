import asyncio
import logging
import sqlite3
import time
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiohttp import web

# Простейший хендлер
async def handle(request):
    return web.Response(text="Bot is running")

# Функция для запуска веб-сервера параллельно с ботом
async def on_startup(dispatcher):
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 8778662008
CHANNEL = "@kyivtrash1"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(level=logging.INFO)

# ---------------- DATABASE ----------------

conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
telegram_id INTEGER,
username TEXT,
language TEXT DEFAULT 'ru',
tokens INTEGER DEFAULT 0,
referrals INTEGER DEFAULT 0,
invited_by INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS posts(
id INTEGER PRIMARY KEY AUTOINCREMENT,
author_id INTEGER,
text TEXT,
photo TEXT
)
""")

conn.commit()

# ---------------- АНТИ СПАМ ----------------

last_post_time = {}

# ---------------- STATES ----------------

class PostState(StatesGroup):
    waiting_post = State()

# ---------------- LANGUAGE ----------------

def get_lang(user_id):
    user = cur.execute(
        "SELECT language FROM users WHERE telegram_id=?",
        (user_id,)
    ).fetchone()
    return user[0] if user else "ru"

# ---------------- KEYBOARDS ----------------

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📩 Надіслати пост")],
            [KeyboardButton(text="💎 Послуги")],
            [KeyboardButton(text="💰 Купити токени")],
            [KeyboardButton(text="👥 Реферальна система")],
            [KeyboardButton(text="⚙️ Налаштування")]
        ],
        resize_keyboard=True
    )

def settings_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇺🇦 Українська")],
            [KeyboardButton(text="🇷🇺 Русский")]
        ],
        resize_keyboard=True
    )

def buy_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 ⭐ → 5 токенів", callback_data="stars_5")],
        [InlineKeyboardButton(text="25 ⭐ → 25 токенів", callback_data="stars_25")],
        [InlineKeyboardButton(text="50 ⭐ → 50 токенів", callback_data="stars_50")],
        [InlineKeyboardButton(text="75 ⭐ → 75 токенів", callback_data="stars_75")],
        [InlineKeyboardButton(text="100 ⭐ → 100 токенів", callback_data="stars_100")]
    ])

# ---------------- START ----------------

@dp.message(CommandStart())
async def start(message: types.Message):

    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    user = cur.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (message.from_user.id,)
    ).fetchone()

    if not user:
        cur.execute(
            "INSERT INTO users (telegram_id, username, invited_by) VALUES (?, ?, ?)",
            (message.from_user.id, message.from_user.username, ref)
        )
        conn.commit()

        if ref:
            try:
                member = await bot.get_chat_member(CHANNEL, message.from_user.id)
                if member.status in ["member", "administrator", "creator"]:
                    cur.execute(
                        "UPDATE users SET tokens=tokens+1, referrals=referrals+1 WHERE telegram_id=?",
                        (ref,)
                    )
                    conn.commit()
            except:
                pass

    lang = get_lang(message.from_user.id)

    text = "👋 Добро пожаловать" if lang == "ru" else "👋 Вітаємо"

    await message.answer(text, reply_markup=main_menu())

# ---------------- SEND POST ----------------

@dp.message(F.text == "📩 Надіслати пост")
async def send_post(message: types.Message, state: FSMContext):

    lang = get_lang(message.from_user.id)
    text = "Отправьте текст или фото" if lang == "ru" else "Надішліть текст або фото"
    await message.answer(text)
    await state.set_state(PostState.waiting_post)

@dp.message(PostState.waiting_post)
async def get_post(message: types.Message, state: FSMContext):

    user_id = message.from_user.id
    now = time.time()

    if user_id in last_post_time:
        if now - last_post_time[user_id] < 60:
            await message.answer("⏳ Подождите 1 минуту")
            return

    last_post_time[user_id] = now

    photo_id = None
    text = message.caption if message.caption else message.text

    if text and len(text) > 500:
        await message.answer("❌ Слишком длинный текст")
        return

    if message.photo:
        photo_id = message.photo[-1].file_id

    cur.execute(
        "INSERT INTO posts(author_id,text,photo) VALUES(?,?,?)",
        (message.from_user.id, text, photo_id)
    )
    conn.commit()

    post_id = cur.lastrowid

    caption = f"📩 Новый пост\n\nID: {post_id}\n\n{text}\n\nАвтор: @{message.from_user.username}"

    if photo_id:
        await bot.send_photo(ADMIN_ID, photo_id, caption=caption)
    else:
        await bot.send_message(ADMIN_ID, caption)

    await message.answer("✅ Отправлено", reply_markup=main_menu())
    await state.clear()
   
    # ---------------- SERVICES ----------------

@dp.message(F.text == "💎 Послуги")
async def services(message: types.Message):

    await message.answer(
        """
💎 Услуги

🗑 Удалить пост — 50 токенов
🔎 Узнать автора — 100 токенов

Напишите ID поста администратору.
""")

# ---------------- REF ----------------

@dp.message(F.text == "👥 Реферальна система")
async def ref_system(message: types.Message):

    user = cur.execute(
        "SELECT tokens,referrals FROM users WHERE telegram_id=?",
        (message.from_user.id,)
    ).fetchone()

    link = f"https://t.me/kyivtrash_bot?start={message.from_user.id}"

    await message.answer(
        f"👥 {user[1]}\n💎 {user[0]}\n\n{link}"
    )

# ---------------- BUY ----------------

@dp.message(F.text == "💰 Купити токени")
async def buy_tokens(message: types.Message):
    await message.answer("💰 Оберіть пакет:", reply_markup=buy_menu())

@dp.callback_query(F.data.startswith("stars_"))
async def buy_stars(callback: types.CallbackQuery):

    amount = int(callback.data.split("_")[1])

    prices = [LabeledPrice(label="Tokens", amount=amount)]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Покупка токенов",
        description=f"{amount} токенов",
        payload=f"buy_{amount}",
        currency="XTR",
        prices=prices
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):

    payload = message.successful_payment.invoice_payload
    amount = int(payload.split("_")[1])

    user = cur.execute(
        "SELECT tokens FROM users WHERE telegram_id=?",
        (message.from_user.id,)
    ).fetchone()

    new_tokens = user[0] + amount

    cur.execute(
        "UPDATE users SET tokens=? WHERE telegram_id=?",
        (new_tokens, message.from_user.id)
    )
    conn.commit()

    await message.answer(f"✅ +{amount} токенов\nБаланс: {new_tokens}")

# ---------------- SETTINGS ----------------

@dp.message(F.text == "⚙️ Налаштування")
async def settings(message: types.Message):
    await message.answer("Выберите язык:", reply_markup=settings_menu())

@dp.message(F.text.in_(["🇺🇦 Українська", "🇷🇺 Русский"]))
async def set_lang(message: types.Message):

    lang = "ua" if "Українська" in message.text else "ru"

    cur.execute(
        "UPDATE users SET language=? WHERE telegram_id=?",
        (lang, message.from_user.id)
    )
    conn.commit()

    await message.answer("✅ Сохранено", reply_markup=main_menu())

# ---------------- RUN ----------------

async def main():
    await bot.delete_webhook()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
