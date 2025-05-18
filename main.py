import logging
import re
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware

API_TOKEN = 'YOUR_TOKEN_HERE'  # Вставь сюда токен бота
LOG_CHANNEL_ID = -1001234567890  # Вставь сюда ID канала для логов (отрицательное число)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# --- Хранилища ---
admins = {}  # {chat_id: {user_id: level}}
group_settings = {}  # {chat_id: {'antilinks': True/False}}

# Регулярное выражение для ссылок
link_regex = re.compile(r'(https?://|t\.me/|telegram\.me/|www\.)', re.IGNORECASE)

# Функции для работы с админами
def get_admin_level(chat_id, user_id):
    return admins.get(chat_id, {}).get(user_id, 0)

def set_admin_level(chat_id, user_id, level):
    if chat_id not in admins:
        admins[chat_id] = {}
    admins[chat_id][user_id] = level

def remove_admin(chat_id, user_id):
    if chat_id in admins and user_id in admins[chat_id]:
        del admins[chat_id][user_id]

def is_owner(chat_member):
    return chat_member.status == 'creator'

# --- Уведомление в лог с кнопками ---
async def notify_log(chat_id, text, violator_id=None):
    keyboard = None
    if violator_id:
        keyboard = InlineKeyboardMarkup(row_width=3)
        keyboard.add(
            InlineKeyboardButton("Мут 10 мин", callback_data=f"mute:{chat_id}:{violator_id}:10"),
            InlineKeyboardButton("Мут 1 час", callback_data=f"mute:{chat_id}:{violator_id}:60"),
            InlineKeyboardButton("Бан 1 час", callback_data=f"ban:{chat_id}:{violator_id}:60"),
            InlineKeyboardButton("Бан 1 день", callback_data=f"ban:{chat_id}:{violator_id}:1440"),
            InlineKeyboardButton("Разблокировать", callback_data=f"unmute:{chat_id}:{violator_id}:0"),
        )
    await bot.send_message(LOG_CHANNEL_ID, text, reply_markup=keyboard)

# --- Автоудаление уведомлений о входе/выходе ---
@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def new_member_welcome(message: types.Message):
    chat_id = message.chat.id
    new_members = message.new_chat_members

    # Удаляем системное сообщение о новых участниках (если возможно)
    try:
        await message.delete()
    except:
        pass

    # Автовыдача админки создателю (уровень 10)
    chat_admins = await bot.get_chat_administrators(chat_id)
    owner = next((a for a in chat_admins if is_owner(a)), None)
    if owner:
        owner_id = owner.user.id
        if get_admin_level(chat_id, owner_id) < 10:
            set_admin_level(chat_id, owner_id, 10)

    for member in new_members:
        await bot.send_message(chat_id, f"Добро пожаловать, {member.full_name}!")

@dp.message_handler(content_types=types.ContentTypes.LEFT_CHAT_MEMBER)
async def left_member_delete_notify(message: types.Message):
    # Удаляем сообщение о выходе участника
    try:
        await message.delete()
    except:
        pass

# --- Анти-ссылки ---
@dp.message_handler()
async def check_links(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if message.chat.type in ['group', 'supergroup']:
        # Проверяем включен ли анти-ссылочный фильтр
        antilinks_enabled = group_settings.get(chat_id, {}).get('antilinks', False)
        if antilinks_enabled and link_regex.search(message.text or ''):
            # Удаляем сообщение со ссылкой
            try:
                await message.delete()
            except:
                pass
            # Логируем нарушение
            text = f"Ссылка от {message.from_user.full_name} (ID: {user_id}) в чате {chat_id} удалена."
            await notify_log(chat_id, text, violator_id=user_id)
            return

# --- Команда /adminpanel ---
@dp.message_handler(commands=['adminpanel'])
async def admin_panel(message: types.Message):
    if message.chat.type != 'private':
        await message.reply("Команда доступна только в личных сообщениях.")
        return

    user_id = message.from_user.id
    user_groups = [chat_id for chat_id, mods in admins.items() if user_id in mods]
    if not user_groups:
        await message.reply("Вы не являетесь администратором ни в одной группе.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Список админов", callback_data="list_admins"),
        InlineKeyboardButton("Добавить модератора", callback_data="add_mod"),
        InlineKeyboardButton("Удалить модератора", callback_data="remove_mod"),
        InlineKeyboardButton("Переключить анти-ссылки", callback_data="toggle_antilinks")
    )
    await message.answer("Панель администратора:", reply_markup=keyboard)

# --- Обработка нажатий inline кнопок в админ панели и логах ---
@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("mute:") or c.data.startswith("ban:") or c.data.startswith("unmute:")))
async def moderation_actions(callback: CallbackQuery):
    data = callback.data.split(":")
    action, chat_id_str, user_id_str, duration_str = data
    chat_id = int(chat_id_str)
    user_id = int(user_id_str)
    duration = int(duration_str)

    caller_id = callback.from_user.id
    caller_level = get_admin_level(chat_id, caller_id)
    if caller_level < 3:
        await callback.answer("Нет прав для действия.", show_alert=True)
        return

    until_date = None
    if duration > 0:
        until_date = datetime.datetime.now() + datetime.timedelta(minutes=duration)

    try:
        if action == "mute":
            await bot.restrict_chat_member(chat_id, user_id,
                                          can_send_messages=False,
                                          until_date=until_date)
            await callback.answer(f"Пользователь замучен на {duration} мин.")
        elif action == "ban":
            await bot.kick_chat_member(chat_id, user_id, until_date=until_date)
            await callback.answer(f"Пользователь забанен на {duration} мин.")
        elif action == "unmute":
            await bot.restrict_chat_member(chat_id, user_id,
                                          can_send_messages=True,
                                          can_send_media_messages=True,
                                          can_send_other_messages=True,
                                          can_add_web_page_previews=True)
            await bot.unban_chat_member(chat_id, user_id)
            await callback.answer("Пользователь разблокирован.")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query_handler(lambda c: c.data in ["list_admins", "add_mod", "remove_mod", "toggle_antilinks"])
async def adminpanel_callbacks(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_chats = [chat_id for chat_id in admins if user_id in admins[chat_id]]
    if not user_chats:
        await callback.answer("Вы не админ ни в одной группе.", show_alert=True)
        return

    chat_id = user_chats[0]  # Для простоты — первая группа
    level = get_admin_level(chat_id, user_id)
    if level < 3:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    if callback.data == "list_admins":
        text = "Админы в группе:\n"
        for uid, lvl in admins.get(chat_id, {}).items():
            try:
                user = await bot.get_chat_member(chat_id, uid)
                text += f"{user.user.full_name} (ID: {uid}) — уровень {lvl}\n"
            except:
                text += f"ID: {uid} — уровень {lvl}\n"
        await callback.message.edit_text(text)
    elif callback.data == "add_mod":
        await callback.message.edit_text("Отправьте ID или пересылайте сообщение пользователя для назначения модератором.")
        dp.register_message_handler(add_mod_handler, state=None)
    elif callback.data == "remove_mod":
        await callback.message.edit_text("Отправьте ID или пересылайте сообщение пользователя для удаления из модераторов.")
        dp.register_message_handler(remove_mod_handler, state=None)
    elif callback.data == "toggle_antilinks":
        current = group_settings.get(chat_id, {}).get('antilinks', False)
        group_settings.setdefault(chat_id, {})['antilinks'] = not current
        await callback.answer(f"Анти-ссылки {'включены' if not current else 'выключены'}")
        await callback.message.edit_text(f"Анти-ссылки теперь {'включены' if not current else 'выключены'}.")

async def add_mod_handler(message: types.Message):
    chat_id = next(iter(admins))  # Берём первую группу
    if message.forward_from:
        user_id = message.forward_from.id
    else:
        try:
            user_id = int(message.text.strip())
        except:
            await message.reply("Не удалось определить пользователя. Перешлите сообщение или отправьте ID.")
            return
    set_admin_level(chat_id, user_id, 3)
    await message.reply(f"Пользователь {user_id} назначен модератором (уровень 3).")
    dp.message_handlers.unregister(add_mod_handler)

async def remove_mod_handler(message: