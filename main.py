import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatType
from aiogram.utils import executor
from aiogram.utils.callback_data import CallbackData
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = 'ВАШ_ТОКЕН_БОТА'
LOG_CHANNEL_ID = -1001234567890  # ID канала для логов

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Храним настройки по чатам (chat_id -> dict)
chat_settings = {}
# Модераторы: chat_id -> {user_id: level}
moderators = {}

ADMIN_LEVELS = {"owner": 3, "admin": 2, "mod": 1}
admin_cb = CallbackData("admin", "action", "param")
link_pattern = re.compile(r"(https?://|t\.me/|telegram\.me/)", re.IGNORECASE)

def default_settings():
    return {
        "anti_arab_enabled": True,
        "anti_spam_enabled": True,
        "anti_link_enabled": False,
        "welcome_enabled": True,
        "welcome_message": "Добро пожаловать, {name}!",
        "log_channel": LOG_CHANNEL_ID,
        "triggers": {},
    }

def get_chat_settings(chat_id):
    if chat_id not in chat_settings:
        chat_settings[chat_id] = default_settings()
    return chat_settings[chat_id]

def get_mod_level(chat_id, user_id):
    return moderators.get(chat_id, {}).get(user_id, 0)

def set_mod_level(chat_id, user_id, level):
    if chat_id not in moderators:
        moderators[chat_id] = {}
    if level == 0:
        moderators[chat_id].pop(user_id, None)
    else:
        moderators[chat_id][user_id] = level

async def log_violation(chat_id, user: types.User, reason, message: types.Message):
    settings = get_chat_settings(chat_id)
    channel_id = settings.get("log_channel")
    if not channel_id:
        return
    text = (f"Нарушение в чате {chat_id}\n"
            f"Пользователь: {user.full_name} (id: {user.id})\n"
            f"Причина: {reason}\n"
            f"Сообщение: {message.text or '<не текстовое>'}")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Мут 5 мин", callback_data=f"action_mute_{user.id}_300"),
        InlineKeyboardButton("Бан 1 час", callback_data=f"action_ban_{user.id}_3600"),
    )
    await bot.send_message(channel_id, text, reply_markup=markup)

# FSM для установки приветствия
class WelcomeState(StatesGroup):
    waiting_for_welcome = State()

# FSM для добавления модератора
class AddModState(StatesGroup):
    waiting_for_user_id = State()

# FSM для удаления модератора
class RemoveModState(StatesGroup):
    waiting_for_user_id = State()

# FSM для добавления триггера
class AddTriggerState(StatesGroup):
    waiting_for_trigger_word = State()
    waiting_for_trigger_response = State()

# FSM для удаления триггера
class RemoveTriggerState(StatesGroup):
    waiting_for_trigger_word = State()

# --- Команды ---

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот-модератор. Используйте /admin для управления.")

@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Пожалуйста, обращайся ко мне в ЛС для управления.")
        return
    user_id = message.from_user.id
    mods = [(cid, lvl) for cid, mods_dict in moderators.items() for uid, lvl in mods_dict.items() if uid == user_id]
    if not mods:
        await message.answer("У вас нет модераторских прав ни в одном чате.")
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for cid, lvl in mods:
        kb.insert(InlineKeyboardButton(f"Чат {cid} (уровень {lvl})", callback_data=admin_cb.new(action="chat_menu", param=str(cid))))
    await message.answer("Выберите чат для управления:", reply_markup=kb)

# --- Меню управления чатами и настройками ---

@dp.callback_query_handler(admin_cb.filter(action="chat_menu"))
async def admin_chat_menu(cq: types.CallbackQuery, callback_data: dict):
    chat_id = int(callback_data["param"])
    user_id = cq.from_user.id
    level = get_mod_level(chat_id, user_id)
    if level == 0:
        await cq.answer("Нет доступа", show_alert=True)
        return
    settings = get_chat_settings(chat_id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"Антиараб: {'Вкл' if settings['anti_arab_enabled'] else 'Выкл'}", callback_data=admin_cb.new(action="toggle_anti_arab", param=str(chat_id))),
        InlineKeyboardButton(f"Антиспам: {'Вкл' if settings['anti_spam_enabled'] else 'Выкл'}", callback_data=admin_cb.new(action="toggle_anti_spam", param=str(chat_id))),
        InlineKeyboardButton(f"Антиссылки: {'Вкл' if settings['anti_link_enabled'] else 'Выкл'}", callback_data=admin_cb.new(action="toggle_anti_link", param=str(chat_id))),
        InlineKeyboardButton(f"Приветствие: {'Вкл' if settings['welcome_enabled'] else 'Выкл'}", callback_data=admin_cb.new(action="toggle_welcome", param=str(chat_id))),
        InlineKeyboardButton("Настроить приветствие", callback_data=admin_cb.new(action="set_welcome", param=str(chat_id))),
        InlineKeyboardButton("Управление модераторами", callback_data=admin_cb.new(action="manage_mods", param=str(chat_id))),
        InlineKeyboardButton("Триггеры", callback_data=admin_cb.new(action="triggers_menu", param=str(chat_id))),
    )
    await cq.message.edit_text(f"Управление чатом {chat_id}", reply_markup=kb)
    await cq.answer()

@dp.callback_query_handler(admin_cb.filter(action=["toggle_anti_arab", "toggle_anti_spam", "toggle_anti_link", "toggle_welcome"]))
async def toggle_setting(cq: types.CallbackQuery, callback_data: dict):
    chat_id = int(callback_data["param"])
    action = callback_data["action"]
    user_id = cq.from_user.id
    level = get_mod_level(chat_id, user_id)
    if level < 2:
        await cq.answer("Недостаточно прав", show_alert=True)
        return
    settings = get_chat_settings(chat_id)

    if action == "toggle_anti_arab":
        settings["anti_arab_enabled"] = not settings["anti_arab_enabled"]
        status = "включён" if settings["anti_arab_enabled"] else "выключен"
        await cq.answer(f"Антиараб {status}.", show_alert=True)
    elif action == "toggle_anti_spam":
        settings["anti_spam_enabled"] = not settings["anti_spam_enabled"]
        status = "включён" if settings["anti_spam_enabled"] else "выключен"
        await cq.answer(f"Антиспам {status}.", show_alert=True)
    elif action == "toggle_anti_link":
        settings["anti_link_enabled"] = not settings["anti_link_enabled"]
        status = "включён" if settings["anti_link_enabled"] else "выключен"
        await cq.answer(f"Антиссылки {status}.", show_alert=True)
    elif action == "toggle_welcome":
        settings["welcome_enabled"] = not settings["welcome_enabled"]
        status = "включено" if settings["welcome_enabled"] else "выключено"
        await cq.answer(f"Приветствие {status}.", show_alert=True)

    # Обновляем меню
    await admin_chat_menu(cq, {"param": str(chat_id), "action": "chat_menu"})

# --- Настройка приветствия через FSM ---

@dp.callback_query_handler(admin_cb.filter(action="set_welcome"))
async def set_welcome_start(cq: types.CallbackQuery, callback_data: dict):
    chat_id = int(callback_data["param"])
    user_id = cq.from_user.id
    if get_mod_level(chat_id, user_id) < 2:
        await cq.answer("Недостаточно прав", show_alert=True)
        return
    await cq.answer("Напишите новое приветствие. Используйте {name} для имени.", show_alert=True)
    await WelcomeState.wait