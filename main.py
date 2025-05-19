import asyncio
import logging
import sqlite3
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Конфигурация --- #
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "ВАШ_ТОКЕН"
ADMINS = [123456789]  # Ваш ID
MODERATORS = [987654321]

# --- Инициализация --- #
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher()
DB_PATH = Path("mystic.db")

# --- Константы --- #
WELCOME_MSG = """🔮 Добро пожаловать, {user_mention}!

Правила чата:
1. Не спамьте
2. Не используйте мат
3. Уважайте других"""
TRIGGERS = {
    "мат": ["дурак", "идиот"],
    "реклама": ["купить", "бесплатно"]
}
MAX_WARNS = 3

# --- База данных --- #
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS warns (
            user_id INTEGER,
            chat_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )""")

def add_warn(user_id: int, chat_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO warns VALUES (?, ?, 0)", (user_id, chat_id))
        conn.execute("UPDATE warns SET count = count + 1 WHERE user_id = ? AND chat_id = ?", 
                    (user_id, chat_id))
        return conn.execute("SELECT count FROM warns WHERE user_id = ? AND chat_id = ?", 
                          (user_id, chat_id)).fetchone()[0]

# --- Команды --- #
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🔮 Mystic Sentinel - магический страж вашего чата")

@dp.message(Command("admin"), F.from_user.id.in_(ADMINS))
async def admin_panel(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Управление", callback_data="admin_menu"))
    await message.answer("⚙️ Админ-панель:", reply_markup=builder.as_markup())

# --- Модерация --- #
@dp.message(F.text.contains("араб"))
async def anti_arab(message: types.Message):
    await message.delete()
    await message.answer(f"🚫 {message.from_user.mention}, арабские символы запрещены!")

@dp.message(lambda msg: any(word in msg.text.lower() for words in TRIGGERS.values() for word in words))
async def anti_trigger(message: types.Message):
    warns = add_warn(message.from_user.id, message.chat.id)
    await message.delete()
    if warns >= MAX_WARNS:
        await message.answer(f"⛔ {message.from_user.mention} получил бан!")
        await bot.ban_chat_member(message.chat.id, message.from_user.id)
    else:
        await message.answer(f"⚠️ {message.from_user.mention}, нарушение! Варнов: {warns}/{MAX_WARNS}")

# --- Системные события --- #
@dp.message(F.new_chat_members)
async def welcome(message: types.Message):
    for user in message.new_chat_members:
        await message.answer(WELCOME_MSG.format(user_mention=user.mention))
    await message.delete()

@dp.message(F.left_chat_member)
async def goodbye(message: types.Message):
    await message.delete()

# --- Запуск --- #
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())