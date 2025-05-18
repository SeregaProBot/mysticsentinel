import logging
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

API_TOKEN = os.getenv("API_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1000000000000"))

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

admin_ids = [123456789]
moderators = [111111111]

conn = sqlite3.connect("violations.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    reason TEXT,
    timestamp TEXT
)
""")
conn.commit()

def log_violation(user_id, user_name, reason):
    cursor.execute("INSERT INTO violations (user_id, user_name, reason, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, user_name, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

class TriggerState(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_response = State()

triggers = {}
user_messages = {}

@dp.message_handler(content_types=types.ContentType.NEW_CHAT_MEMBERS)
async def greet_new_users(message: types.Message):
    for user in message.new_chat_members:
        await message.reply(f"Приветствуем, {user.full_name} в {message.chat.title}!")
    await message.delete()

@dp.chat_member_handler()
async def suppress_join_leave(update: types.ChatMemberUpdated):
    try:
        await bot.delete_message(update.chat.id, update.chat.id)
    except:
        pass

@dp.message_handler(commands=["admin"])
async def call_admins(message: types.Message):
    if message.chat.type != "private":
        tagged = " ".join([f"<a href='tg://user?id={uid}'>Админ</a>" for uid in admin_ids])
        await message.reply("Внимание, нужны админы! " + tagged)

@dp.message_handler(lambda m: any(c in m.text for c in "ابتثجحخدذرزسشصضطظعغفقكلمنهو"))
async def anti_arab(message: types.Message):
    await message.delete()
    log_violation(message.from_user.id, message.from_user.full_name, "Арабский текст")
    await bot.send_message(LOG_CHANNEL_ID, f"Арабский текст от {message.from_user.full_name}: {message.text}")

@dp.message_handler(lambda m: m.text and m.text.lower().count("http") > 2)
async def anti_spam(message: types.Message):
    await message.delete()
    log_violation(message.from_user.id, message.from_user.full_name, "Спам (>2 ссылок)")
    await bot.send_message(LOG_CHANNEL_ID, f"Спам от {message.from_user.full_name}: {message.text}")

@dp.message_handler()
async def flood_control_and_triggers(message: types.Message):
    uid = message.from_user.id
    user_messages.setdefault(uid, [])
    user_messages[uid].append(message.date.timestamp())
    user_messages[uid] = [t for t in user_messages[uid] if message.date.timestamp() - t < 10]
    if len(user_messages[uid]) > 5:
        await message.delete()
        log_violation(uid, message.from_user.full_name, "Флуд (>5 сообщений за 10 секунд)")
        await bot.send_message(LOG_CHANNEL_ID, f"Флуд от {message.from_user.full_name}")

    lower = message.text.lower()
    if lower in triggers:
        await message.reply(triggers[lower])

@dp.message_handler(commands=["add_trigger"])
async def add_trigger(message: types.Message):
    if message.from_user.id in admin_ids:
        await message.answer("Отправьте ключевое слово:")
        await TriggerState.waiting_for_keyword.set()

@dp.message_handler(state=TriggerState.waiting_for_keyword)
async def trigger_keyword(message: types.Message, state: FSMContext):
    await state.update_data(keyword=message.text.lower())
    await message.answer("Теперь отправьте ответ:")
    await TriggerState.waiting_for_response.set()

@dp.message_handler(state=TriggerState.waiting_for_response)
async def trigger_response(message: types.Message, state: FSMContext):
    data = await state.get_data()
    triggers[data["keyword"]] = message.text
    await message.answer(f"Триггер '{data['keyword']}' сохранён.")
    await state.finish()

@dp.message_handler(commands=["menu"])
async def admin_menu(message: types.Message):
    if message.from_user.id in admin_ids:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Добавить триггер", callback_data="add_trigger"))
        kb.add(InlineKeyboardButton("Список триггеров", callback_data="list_triggers"))
        kb.add(InlineKeyboardButton("Последние нарушения", callback_data="last_violations"))
        await message.answer("Админ-меню:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "add_trigger")
async def cb_add_trigger(callback: types.CallbackQuery):
    await callback.message.answer("Введите ключевое слово:")
    await TriggerState.waiting_for_keyword.set()
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "list_triggers")
async def cb_list_triggers(callback: types.CallbackQuery):
    if triggers:
        text = "\n".join([f"{k} => {v}" for k, v in triggers.items()])
    else:
        text = "Триггеры ещё не добавлены."
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "last_violations")
async def cb_last_violations(callback: types.CallbackQuery):
    rows = cursor.execute("SELECT user_name, reason, timestamp FROM violations ORDER BY id DESC LIMIT 10").fetchall()
    text = "\n".join([f"{r[0]} — {r[1]} ({r[2]})" for r in rows]) if rows else "Нарушений нет."
    await callback.message.answer("<b>Последние нарушения:</b>\n" + text)
    await callback.answer()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
