import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.utils import executor
from datetime import datetime, timedelta

API_TOKEN = "YOUR_BOT_TOKEN_HERE"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Хранилища данных в памяти (для простоты) ---
# Настройки для каждого чата (chat_id -> dict)
chat_settings = {}

# Формат настроек на чат:
# {
#   "admins": {user_id: level (1-5)},
#   "welcome_enabled": True/False,
#   "links_filter_enabled": True/False,
#   "anti_arab_enabled": True/False,
#   "anti_spam_enabled": True/False,
#   "log_channel": chat_id or None,
# }

# --- FSM состояния для админ меню ---
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_level = State()

# --- Вспомогательные функции ---

def get_settings(chat_id):
    if chat_id not in chat_settings:
        chat_settings[chat_id] = {
            "admins": {},
            "welcome_enabled": True,
            "links_filter_enabled": False,
            "anti_arab_enabled": False,
            "anti_spam_enabled": False,
            "log_channel": None,
        }
    return chat_settings[chat_id]

def is_admin(chat_id, user_id):
    settings = get_settings(chat_id)
    return settings["admins"].get(user_id, 0) > 0

def get_admin_level(chat_id, user_id):
    settings = get_settings(chat_id)
    return settings["admins"].get(user_id, 0)

def set_admin_level(chat_id, user_id, level):
    settings = get_settings(chat_id)
    settings["admins"][user_id] = level

def remove_admin(chat_id, user_id):
    settings = get_settings(chat_id)
    settings["admins"].pop(user_id, None)

def admin_can_manage(chat_id, user_id, required_level=3):
    return get_admin_level(chat_id, user_id) >= required_level

# --- Клавиатуры ---

def get_main_admin_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Выдать модератора", callback_data="admin_add_mod"),
        InlineKeyboardButton("Снять модератора", callback_data="admin_remove_mod"),
    )
    kb.add(
        InlineKeyboardButton("Переключить приветствия", callback_data="toggle_welcome"),
        InlineKeyboardButton("Переключить фильтр ссылок", callback_data="toggle_links"),
    )
    kb.add(
        InlineKeyboardButton("Переключить антиараб", callback_data="toggle_anti_arab"),
        InlineKeyboardButton("Переключить антиспам", callback_data="toggle_anti_spam"),
    )
    kb.add(
        InlineKeyboardButton("Настроить канал логов", callback_data="set_log_channel")
    )
    return kb

def get_time_ban_kb(user_id):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("Мут 10 мин", callback_data=f"mute_{user_id}_10"),
        InlineKeyboardButton("Бан 1 час", callback_data=f"ban_{user_id}_60"),
        InlineKeyboardButton("Бан 1 день", callback_data=f"ban_{user_id}_1440"),
    )
    return kb

# --- Хэндлеры ---

# Автоматическая выдача максимального уровня создателю группы
@dp.chat_member_handler()
async def on_chat_member_updated(chat_member: types.ChatMemberUpdated):
    chat_id = chat_member.chat.id
    new_status = chat_member.new_chat_member.status
    user_id = chat_member.new_chat_member.user.id
    if new_status == "creator":
        settings = get_settings(chat_id)
        # Создателю — уровень 5 (максимальный)
        settings["admins"][user_id] = 5
        try:
            await bot.send_message(chat_id, f"Создатель {chat_member.new_chat_member.user.full_name} получил максимальный уровень админки.")
        except:
            pass

# Удаление сообщений о входе/выходе участников
@dp.message_handler(content_types=[types.ContentType.NEW_CHAT_MEMBERS, types.ContentType.LEFT_CHAT_MEMBER])
async def delete_join_leave(message: types.Message):
    try:
        await message.delete()
    except:
        pass

# Приветствие новых участников (если включено)
@dp.message_handler(content_types=types.ContentType.NEW_CHAT_MEMBERS)
async def welcome_new_members(message: types.Message):
    chat_id = message.chat.id
    settings = get_settings(chat_id)
    if settings["welcome_enabled"]:
        for new_member in message.new_chat_members:
            await message.answer(f"Добро пожаловать, {new_member.full_name}!")

# Команда вызова админ меню
@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        await message.reply("Вы не администратор этой группы.")
        return

    try:
        await bot.send_message(user_id, "Админ-панель:", reply_markup=get_main_admin_kb())
        if message.chat.type != "private":
            await message.reply("Панель админа отправлена в личные сообщения.")
    except:
        await message.reply("Невозможно отправить личное сообщение. Напишите боту первым.")

# Обработка нажатий в админ панели
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("admin_") or
                                       c.data in ["toggle_welcome", "toggle_links", "toggle_anti_arab", "toggle_anti_spam", "set_log_channel"])
async def admin_panel_handler(cq: types.CallbackQuery, state: FSMContext):
    user_id = cq.from_user.id
    chat_id = cq.message.chat.id if cq.message.chat.type != "private" else None
    data = cq.data

    # В личке нет chat_id - надо понять, в какой группе админ управляет
    # Для простоты: если в личке — возьмём все чаты, где он админ (в нашем хранилище), если один — его, иначе попросим указать чат
    # В данном минимальном примере используем первый чат с админом
    if chat_id is None:
        # поиск чата, где этот пользователь админ
        found = None
        for c, s in chat_settings.items():
            if s["admins"].get(user_id, 0) > 0:
                found = c
                break
        if found is None:
            await cq.answer("Не найден чат с вашей админкой.", show_alert=True)
            return
        chat_id = found

    if not admin_can_manage(chat_id, user_id):
        await cq.answer("Недостаточно прав для этого действия.", show_alert=True)
        return

    settings = get_settings(chat_id)

    if data == "admin_add_mod":
        await cq.message.answer("Отправьте ID пользователя (или пересланное сообщение от него) для выдачи модератора.")
        await AdminStates.waiting_for_user_id.set()
        await state.update_data(action="add", chat_id=chat_id)
    elif data == "admin_remove_mod":
        await cq.message.answer("Отправьте ID пользователя (или пересланное сообщение от него) для снятия модератора.")
        await AdminStates.waiting_for_user_id.set()
        await state.update_data(action="remove", chat_id=chat_id)
    elif data == "toggle_welcome":
        settings["welcome_enabled"] = not settings["welcome_enabled"]
        status = "включены" if settings["welcome_enabled"] else "выключены"
        await cq.answer(f"Приветствия теперь {status}.", show_alert=True)
    elif data == "toggle_links":
        settings["links_filter_enabled"] = not settings["links_filter_enabled"]
        status = "включён" if settings["links_filter_enabled"] else "выключен"
        await cq.answer(f"Фильтр ссылок теперь {status}.", show_alert=True)
    elif data == "toggle_anti_arab":
       