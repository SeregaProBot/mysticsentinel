import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
import re

API_TOKEN = 'ВАШ_ТОКЕН_БОТА'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Хранилище настроек для групп (здесь простой словарь, для реального — БД)
groups_settings = {}

# Пример структуры:
# groups_settings = {
#   chat_id: {
#       'admins': [user_id, ...],
#       'log_channel_id': channel_id,
#       'welcome_text': "Привет, {user}!",
#       'anti_arab': True,
#       'anti_spam': True,
#       'anti_mat': True,
#       'anti_link': True,
#       'autoanswers': { "привет": "Привет!", "как дела": "Хорошо, спасибо!" },
#       'mod_level': 1,
#       'muted': {user_id: until_timestamp},
#       'banned': {user_id: until_timestamp}
#   }
# }

# Простейшая проверка админа группы
async def is_group_admin(chat_id: int, user_id: int) -> bool:
    if chat_id in groups_settings and 'admins' in groups_settings[chat_id]:
        return user_id in groups_settings[chat_id]['admins']
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.is_chat_admin()
    except:
        return False

# --- Команды ---

@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    chat_id = message.chat.id
    if chat_id < 0:  # Группа
        admins = await bot.get_chat_administrators(chat_id)
        admins_mentions = []
        for admin in admins:
            user = admin.user
            mention = user.get_mention()
            admins_mentions.append(mention)
        await message.reply("Администраторы группы:\n" + "\n".join(admins_mentions), parse_mode=ParseMode.HTML)
    else:
        await message.reply("Команда доступна только в группах.")

@dp.message_handler(commands=['adminpanel'])
async def cmd_adminpanel(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id < 0:
        if not await is_group_admin(chat_id, user_id):
            await message.reply("Только администраторы могут пользоваться панелью.")
            return

        if chat_id not in groups_settings:
            groups_settings[chat_id] = {
                'admins': [],
                'log_channel_id': None,
                'welcome_text': "Привет, {user}!",
                'anti_arab': True,
                'anti_spam': True,
                'anti_mat': True,
                'anti_link': True,
                'autoanswers': {},
                'mod_level': 1,
                'muted': {},
                'banned': {}
            }
        settings = groups_settings[chat_id]

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("Настроить приветствие", callback_data='set_welcome'),
            InlineKeyboardButton("Лог-канал", callback_data='set_log_channel'),
            InlineKeyboardButton("Антиараб", callback_data='toggle_anti_arab'),
            InlineKeyboardButton("Антиспам", callback_data='toggle_anti_spam'),
            InlineKeyboardButton("Антимат", callback_data='toggle_anti_mat'),
            InlineKeyboardButton("Антилинк", callback_data='toggle_anti_link'),
            InlineKeyboardButton("Автоответчик", callback_data='edit_autoanswers'),
            InlineKeyboardButton("Уровень модерации", callback_data='set_mod_level')
        )
        await message.reply("Панель управления ботом:", reply_markup=kb)
    else:
        await message.reply("Панель доступна только в группах.")

# --- Callback для админпанели ---

@dp.callback_query_handler(lambda c: c.data and c.data.startswith(('set_welcome', 'set_log_channel', 'toggle_', 'edit_autoanswers', 'set_mod_level')))
async def process_callback_adminpanel(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    if not await is_group_admin(chat_id, user_id):
        await callback_query.answer("Только администраторы.", show_alert=True)
        return

    settings = groups_settings.get(chat_id)
    if not settings:
        await callback_query.answer("Настройки не найдены.", show_alert=True)
        return

    data = callback_query.data

    if data == 'set_welcome':
        await callback_query.message.answer("Отправьте новое приветствие. Используйте {user} для упоминания пользователя.")
        await WelcomeState.waiting.set()

    elif data == 'set_log_channel':
        await callback_query.message.answer("Отправьте ID канала для логов. Канал должен быть доступен боту.")
        await LogChannelState.waiting.set()

    elif data == 'toggle_anti_arab':
        settings['anti_arab'] = not settings.get('anti_arab', True)
        await callback_query.answer(f"Антиараб {'включён' if settings['anti_arab'] else 'выключен'}")

    elif data == 'toggle_anti_spam':
        settings['anti_spam'] = not settings.get('anti_spam', True)
        await callback_query.answer(f"Антиспам {'включён' if settings['anti_spam'] else 'выключен'}")

    elif data == 'toggle_anti_mat':
        settings['anti_mat'] = not settings.get('anti_mat', True)
        await callback_query.answer(f"Антимат {'включён' if settings['anti_mat'] else 'выключен'}")

    elif data == 'toggle_anti_link':
        settings['anti_link'] = not settings.get('anti_link', True)
        await callback_query.answer(f"Антилинк {'включён' if settings['anti_link'] else 'выключен'}")

    elif data == 'edit_autoanswers':
        text = "Текущие автоответы:\n"
        for k, v in settings['autoanswers'].items():
            text += f"Фраза: {k} → Ответ: {v}\n"
        text += "\nОтправьте сообщение в формате 'фраза=ответ' для добавления/обновления автоответа.\n" \
                "Или 'удалить=фраза' для удаления."
        await callback_query.message.answer(text)
        await AutoAnswerState.waiting.set()

    elif data == 'set_mod_level':
        await callback_query.message.answer(f"Текущий уровень модерации: {settings.get('mod_level',1)}\n" 
                                            "Отправьте число от 0 до 5 для установки.")
        await ModLevelState.waiting.set()

    await callback_query.answer()

# --- FSM States ---

from aiogram.dispatcher.filters.state import State, StatesGroup

class WelcomeState(StatesGroup):
    waiting = State()

class LogChannelState(StatesGroup):
    waiting = State()

class AutoAnswerState(StatesGroup):
    waiting = State()

class ModLevelState(StatesGroup):
    waiting = State()

# --- Обработчики состояний ---

@dp.message_handler(state=WelcomeState.waiting, content_types=types.ContentTypes.TEXT)
async def set_welcome_text(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    text = message.text
    if chat_id not in groups_settings:
        groups_settings[chat_id] = {}
    groups_settings[chat_id]['welcome_text'] = text
    await message.reply("Приветствие сохранено!")
    await state.finish()

@dp.message_handler(state=LogChannelState.waiting, content_types=types.ContentTypes.TEXT)
async def set_log_channel(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    text = message.text.strip()
    try:
        channel_id = int(text)
        # Можно добавить проверку прав бота в канале
        if chat_id not in groups_settings:
            groups_settings[chat_id] = {}
        groups_settings[chat_id]['log_channel_id'] = channel_id
        await message.reply("Канал для логов сохранён!")
    except Exception:
        await message.reply("Ошибка: отправьте корректный ID канала (число).")
    await state.finish()

@dp.message_handler(state=AutoAnswerState.waiting, content_types=types.ContentTypes.TEXT)
async def edit_autoanswers(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    text = message.text.strip()
    settings = groups_settings.get(chat_id)
    if not settings:
        await message.reply("Ошибка: нет настроек.")
        await state.finish()
        return

    if '=' not in text:
        await message.reply("Неверный формат. Используйте 'фраза=ответ' или 'удалить=фраза'")
        return

    cmd, val = map(str.strip, text.split('=',1))
    if cmd.lower() == 'удалить':
        if val in settings['autoanswers']:
            del settings['autoanswers'][val]
            await message.reply(f"Удалён автоответ на фразу: {val}")
        else:
            await message.reply("Такой фразы нет.")
    else:
        settings['autoanswers'][cmd] = val
        await message.reply(f"Добавлен/обновлён автоответ: {cmd} → {val}")

@dp.message_handler(state=ModLevelState.waiting, content_types=types.ContentTypes.TEXT)
async def set_mod_level(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    text = message.text.strip()
    if not text.isdigit():
        await message.reply("Введите число от 0 до 5.")
        return
    lvl = int(text)
    if lvl < 0 or lvl > 5:
        await message.reply("Введите число от 0 до 5.")
        return
    if chat_id not in groups_settings:
        groups_settings[chat_id] = {}
    groups_settings[chat_id]['mod_level'] = lvl
    await message.reply(f"Уровень модерации установлен: {lvl}")
    await state.finish()

# --- Основные фильтры (антиараб, антимат, антиспам, антилинк) ---

arabic_pattern = re.compile('[\u0600-\u06FF\u0750-\u077F]', re.UNICODE)

mat_words = {'блин', 'мат1', 'мат2'}  # Добавь свои слова

url_pattern = re.compile(r'https?://\S+|www\.\S+')

# Для антиспама сделаем простую задержку сообщений

user_last_message_time = {}

SPAM_DELAY_SECONDS = 3

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def message_handler(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.lower()

    if chat_id not in groups_settings:
        # Инициализация настроек группы, если нет
        groups_settings[chat_id] = {
            'admins': [],
            'log_channel_id': None,
            'welcome_text': "Привет, {user}!",
            'anti_arab': True,
            'anti_spam': True,
            'anti_mat': True,
            'anti_link': True,
            'autoanswers': {},
            'mod_level': 1,
            'muted': {},
            'banned': {}
        }
    settings = groups_settings[chat_id]

    # Проверка мутов/банов
    if user_id in settings['muted']:
        await message.delete()
        return

    if user_id in settings['banned']:
        await message.delete()
        return

    # Антиараб
    if settings.get('anti_arab') and arabic_pattern.search(text):
        await message.delete()
        await log_action(chat_id, f"Удалено сообщение с арабскими символами от {message.from_user.get_mention()}")
        return

    # Антимат
    if settings.get('anti_mat'):
        for w in mat_words:
            if w in text:
                await message.delete()
                await log_action(chat_id, f"Удалено сообщение с матом от {message.from_user.get_mention()}")
                return

    # Антилинк
    if settings.get('anti_link') and url_pattern.search(text):
        await message.delete()
        await log_action(chat_id, f"Удалено сообщение со ссылкой от {message.from_user.get_mention()}")
        return

    # Антиспам
    import time
    now = time.time()
    last_time = user_last_message_time.get(user_id, 0)
    if settings.get('anti_spam') and (now - last_time < SPAM_DELAY_SECONDS):
        await message.delete()
        await log_action(chat_id, f"Удалено сообщение из-за спама от {message.from_user.get_mention()}")
        return
    user_last_message_time[user_id] = now

    # Автоответчик
    for phrase, answer in settings['autoanswers'].items():
        if phrase in text:
            await message.reply(answer)
            break

# --- Логирование с inline кнопками ---

async def log_action(chat_id: int, text: str):
    settings = groups_settings.get(chat_id)
    if not settings:
        return
    log_channel_id = settings.get('log_channel_id')
    if not log_channel_id:
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Мут 10 мин", callback_data=f"mute|{chat_id}|10"),
        InlineKeyboardButton("Мут 1 час", callback_data=f"mute|{chat_id}|60"),
        InlineKeyboardButton("Бан 1 час", callback_data=f"ban|{chat_id}|60"),
        InlineKeyboardButton("Бан навсегда", callback_data=f"ban|{chat_id}|-1")
    )
    try:
        await bot.send_message(log_channel_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        pass

@dp.callback_query_handler(lambda c: c.data and (c.data.startswith('mute') or c.data.startswith('ban')))
async def callback_mute_ban(call: types.CallbackQuery):
    parts = call.data.split('|')
    action = parts[0]
    chat_id = int(parts[1])
    duration = int(parts[2])

    if not await is_group_admin(chat_id, call.from_user.id):
        await call.answer("Только админы могут использовать.", show_alert=True)
        return

    # Здесь можно получить user_id по reply или другим способом
    # Но в данном примере для простоты не реализуем получение user_id
    await call.answer("Действие реализуйте отдельно, так как user_id не передаётся.", show_alert=True)

# --- Приветствие новых участников ---

@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def on_user_join(message: types.Message):
    chat_id = message.chat.id
    settings = groups_settings.get(chat_id)
    if not settings:
        return
    welcome_text = settings.get('welcome_text', "Привет, {user}!")
    for new_member in message.new_chat_members:
        text = welcome_text.replace("{user}", new_member.get_mention())
        await message.reply(text, parse_mode=ParseMode.HTML)

# --- Запуск бота ---

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)