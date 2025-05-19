import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.types import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.methods import RestrictChatMember, BanChatMember, UnbanChatMember

# --- Конфигурация --- #
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "7954709613:AAFccAMIVagLzxheXI94ryTVHwqYGmwkgx4"
ADMINS = [692826378]  # Ваш ID
MODERATORS = [869747941]
LOG_CHANNEL = "-1002625004448"  # Канал для логов

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
    "мат": ["дурак", "идиот", "придурок"],
    "реклама": ["купить", "бесплатно", "http"]
}
MAX_WARNS = 3
MUTE_DURATION = timedelta(hours=1)

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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            anti_mat BOOLEAN DEFAULT 1,
            anti_spam BOOLEAN DEFAULT 1,
            anti_arab BOOLEAN DEFAULT 1
        )""")

def get_chat_settings(chat_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO settings (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        return cursor.execute("SELECT anti_mat, anti_spam, anti_arab FROM settings WHERE chat_id = ?", 
                            (chat_id,)).fetchone()

def update_setting(chat_id: int, setting: str, value: bool):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE settings SET {setting} = ? WHERE chat_id = ?", (value, chat_id))

def add_warn(user_id: int, chat_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO warns VALUES (?, ?, 0)", (user_id, chat_id))
        conn.execute("UPDATE warns SET count = count + 1 WHERE user_id = ? AND chat_id = ?", 
                    (user_id, chat_id))
        return conn.execute("SELECT count FROM warns WHERE user_id = ? AND chat_id = ?", 
                          (user_id, chat_id)).fetchone()[0]

def reset_warns(user_id: int, chat_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM warns WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

# --- Логирование --- #
async def log_action(action: str, chat: types.Chat, user: types.User, moderator: types.User = None, reason: str = None):
    text = (
        f"🛡 **Действие модерации**\n"
        f"• **Тип:** {action}\n"
        f"• **Чат:** {chat.title if chat.title else 'ЛС'}\n"
        f"• **Пользователь:** {user.mention}\n"
        f"• **ID:** `{user.id}`\n"
    )
    
    if moderator:
        text += f"• **Модератор:** {moderator.mention}\n"
    if reason:
        text += f"• **Причина:** {reason}\n"
    
    await bot.send_message(LOG_CHANNEL, text)

# --- Клавиатуры --- #
def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔇 Мут", callback_data="mute"),
        InlineKeyboardButton(text="🚷 Бан", callback_data="ban"),
        InlineKeyboardButton(text="👢 Кик", callback_data="kick")
    )
    builder.row(
        InlineKeyboardButton(text="⚠️ Варн", callback_data="warn"),
        InlineKeyboardButton(text="♻️ Сбросить варны", callback_data="reset_warns")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    return builder.as_markup()

def get_settings_keyboard(chat_id: int):
    anti_mat, anti_spam, anti_arab = get_chat_settings(chat_id)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"Анти-мат {'✅' if anti_mat else '❌'}",
            callback_data=f"toggle_anti_mat"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"Анти-спам {'✅' if anti_spam else '❌'}",
            callback_data=f"toggle_anti_spam"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"Анти-араб {'✅' if anti_arab else '❌'}",
            callback_data=f"toggle_anti_arab"
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")
    )
    return builder.as_markup()

# --- Команды --- #
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🔮 Mystic Sentinel - магический страж вашего чата")

@dp.message(Command("admin"), F.from_user.id.in_(ADMINS + MODERATORS))
async def admin_panel(message: types.Message):
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())

@dp.message(Command("mute"), F.from_user.id.in_(ADMINS + MODERATORS), F.reply_to_message)
async def mute_cmd(message: types.Message, command: CommandObject):
    duration = timedelta(hours=1)
    if command.args:
        try:
            duration = timedelta(minutes=int(command.args))
        except ValueError:
            await message.reply("Используйте: /mute [минуты]")
            return
    
    await restrict_user(
        message, 
        permissions=ChatPermissions(can_send_messages=False),
        action="Мут",
        duration=duration
    )

@dp.message(Command("ban"), F.from_user.id.in_(ADMINS), F.reply_to_message)
async def ban_cmd(message: types.Message, command: CommandObject):
    await ban_user(message, command.args)

@dp.message(Command("kick"), F.from_user.id.in_(ADMINS + MODERATORS), F.reply_to_message)
async def kick_cmd(message: types.Message):
    await ban_user(message, duration=timedelta(seconds=30))

@dp.message(Command("warn"), F.from_user.id.in_(ADMINS + MODERATORS), F.reply_to_message)
async def warn_cmd(message: types.Message):
    warns = add_warn(message.reply_to_message.from_user.id, message.chat.id)
    await message.reply(f"⚠️ Пользователь {message.reply_to_message.from_user.mention} получил варн. Всего: {warns}/{MAX_WARNS}")
    
    if warns >= MAX_WARNS:
        await ban_user(message, reason=f"Достигнут лимит варнов ({MAX_WARNS})")
    
    await log_action(
        "Варн",
        message.chat,
        message.reply_to_message.from_user,
        message.from_user
    )

# --- Модерация --- #
async def restrict_user(
    message: types.Message,
    permissions: ChatPermissions,
    action: str,
    duration: timedelta = None,
    reason: str = None
):
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=message.reply_to_message.from_user.id,
            permissions=permissions,
            until_date=datetime.now() + duration if duration else None
        )
        
        text = f"🛡 {action} для {message.reply_to_message.from_user.mention}"
        if duration:
            text += f" на {duration.seconds//60} минут"
        if reason:
            text += f"\nПричина: {reason}"
            
        await message.reply(text)
        await log_action(
            action,
            message.chat,
            message.reply_to_message.from_user,
            message.from_user,
            reason
        )
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

async def ban_user(message: types.Message, reason: str = None, duration: timedelta = None):
    try:
        await bot.ban_chat_member(
            chat_id=message.chat.id,
            user_id=message.reply_to_message.from_user.id,
            until_date=datetime.now() + duration if duration else None
        )
        
        text = f"🛡 Бан для {message.reply_to_message.from_user.mention}"
        if duration:
            text += f" на {duration.days} дней" if duration.days else f" на {duration.seconds//3600} часов"
        if reason:
            text += f"\nПричина: {reason}"
            
        await message.reply(text)
        await log_action(
            "Бан" if not duration else "Временный бан",
            message.chat,
            message.reply_to_message.from_user,
            message.from_user,
            reason
        )
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# --- Обработчики --- #
@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_setting(callback: types.CallbackQuery):
    setting = callback.data.replace("toggle_", "")
    current = get_chat_settings(callback.message.chat.id)[["anti_mat", "anti_spam", "anti_arab"].index(setting)]
    update_setting(callback.message.chat.id, setting, not current)
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(callback.message.chat.id))

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ Настройки автоматической модерации:", 
                                  reply_markup=get_settings_keyboard(callback.message.chat.id))

@dp.callback_query(F.data.in_(["mute", "ban", "kick", "warn", "reset_warns"]))
async def admin_actions(callback: types.CallbackQuery):
    if not callback.message.reply_to_message:
        await callback.answer("❌ Нужно ответить на сообщение пользователя")
        return
    
    user = callback.message.reply_to_message.from_user
    action = callback.data
    
    if action == "mute":
        await restrict_user(
            callback.message,
            permissions=ChatPermissions(can_send_messages=False),
            action="Мут",
            duration=MUTE_DURATION
        )
    elif action == "ban":
        await ban_user(callback.message)
    elif action == "kick":
        await ban_user(callback.message, duration=timedelta(seconds=30))
    elif action == "warn":
        warns = add_warn(user.id, callback.message.chat.id)
        await callback.message.reply(f"⚠️ Пользователь {user.mention} получил варн. Всего: {warns}/{MAX_WARNS}")
        if warns >= MAX_WARNS:
            await ban_user(callback.message, reason=f"Достигнут лимит варнов ({MAX_WARNS})")
    elif action == "reset_warns":
        reset_warns(user.id, callback.message.chat.id)
        await callback.message.reply(f"♻️ Варны для {user.mention} сброшены")
    
    await log_action(
        {
            "mute": "Мут",
            "ban": "Бан",
            "kick": "Кик",
            "warn": "Варн",
            "reset_warns": "Сброс варнов"
        }[action],
        callback.message.chat,
        user,
        callback.from_user
    )

# --- Автомодерация --- #
@dp.message(F.text.contains("араб"))
async def anti_arab(message: types.Message):
    anti_mat, anti_spam, anti_arab = get_chat_settings(message.chat.id)
    if not anti_arab:
        return
    
    await message.delete()
    warns = add_warn(message.from_user.id, message.chat.id)
    await message.answer(f"🚫 {message.from_user.mention}, арабские символы запрещены! Варнов: {warns}/{MAX_WARNS}")
    
    if warns >= MAX_WARNS:
        await ban_user(message, reason="Достигнут лимит варнов")
    
    await log_action("Авто-варн (анти-араб)", message.chat, message.from_user)

@dp.message(lambda msg: any(word in msg.text.lower() for words in TRIGGERS.values() for word in words))
async def anti_trigger(message: types.Message):
    anti_mat, anti_spam, anti_arab = get_chat_settings(message.chat.id)
    if not anti_mat:
        return
    
    await message.delete()
    warns = add_warn(message.from_user.id, message.chat.id)
    await message.answer(f"⚠️ {message.from_user.mention}, нарушение правил! Варнов: {warns}/{MAX_WARNS}")
    
    if warns >= MAX_WARNS:
        await ban_user(message, reason="Достигнут лимит варнов")
    
    await log_action("Авто-варн (анти-мат)", message.chat, message.from_user)

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