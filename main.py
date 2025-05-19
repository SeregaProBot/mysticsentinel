import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ChatPermissions
from config import BOT_TOKEN, ADMINS, MODERATORS

# --- Настройка бота --- #
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher()

# --- Константы --- #
WELCOME_MSG = "🔮 Добро пожаловать, {user_mention}! Читай правила."
TRIGGERS = {
    "мат": ["дурак", "идиот", "тупой"],
    "реклама": ["купить", "бесплатно", "http"]
}
MAX_WARNS = 3

# --- База данных --- #
def add_warn(user_id: int, chat_id: int):
    conn = sqlite3.connect("mystic.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO warns VALUES (?, ?, 0)", (user_id, chat_id))
    cursor.execute("UPDATE warns SET count = count + 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    warns = cursor.execute("SELECT count FROM warns WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)).fetchone()[0]
    conn.close()
    return warns

# --- Команды --- #
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🔮 Mystic Sentinel — магический страж вашего чата.")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMINS:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🛡 Анти-спам", callback_data="antispam"))
        builder.add(types.InlineKeyboardButton(text="🔞 Анти-араб", callback_data="antiarab"))
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
        await message.answer(f"⛔ {message.from_user.mention} получил бан за {MAX_WARNS} варна!")
        await bot.ban_chat_member(message.chat.id, message.from_user.id)
    else:
        await message.answer(f"⚠️ {message.from_user.mention}, триггер! Варнов: {warns}/{MAX_WARNS}")

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())