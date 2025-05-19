import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from config import BOT_TOKEN, ADMINS, MODERATORS

# Настройка логов
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Права модераторов и админов
ADMINS = ADMINS  # Список ID админов (из config.py)
MODERATORS = MODERATORS  # Список ID модераторов

# Триггеры (можно расширять)
TRIGGERS = {
    "оскорбления": ["дурак", "идиот", "тупой"],
    "реклама": ["купить", "бесплатно", "перейди"],
}

# Приветственное сообщение
WELCOME_MSG = (
    "🔮 Добро пожаловать в {chat_title}, {user_name}! \n\n"
    "⚠️ Соблюдайте правила: \n"
    "— Не спамьте \n"
    "— Не оскорбляйте других \n"
    "— Не используйте арабские символы \n\n"
    "Наслаждайтесь общением! ✨"
)

# ========== ОСНОВНЫЕ КОМАНДЫ ========== #
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.chat.type == 'private':
        await message.answer("🔮 *Mystic Sentinel* — твой магический страж. \n"
                           "Используй /help для списка команд.", parse_mode="Markdown")

# ========== АДМИН-МЕНЮ (В ЛИЧКЕ) ========== #
@dp.message_handler(Command("admin"), user_id=ADMINS)
async def admin_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("🛡 Анти-спам", callback_data="antispam"),
        InlineKeyboardButton("🔞 Анти-араб", callback_data="antiarab"),
        InlineKeyboardButton("⚡ Триггеры", callback_data="triggers"),
        InlineKeyboardButton("👥 Управление", callback_data="manage"),
    ]
    keyboard.add(*buttons)
    await message.answer("⚙️ *Админ-панель Mystic Sentinel*", reply_markup=keyboard, parse_mode="Markdown")

# ========== АНТИ-АРАБ ========== #
@dp.message_handler(lambda msg: any(char in "؀-ۿ" for char in msg.text))
async def anti_arab(message: types.Message):
    await message.delete()
    await message.answer(f"🚫 {message.from_user.mention}, арабские символы запрещены!")

# ========== АНТИ-СПАМ ========== #
@dp.message_handler(content_types=types.ContentType.ANY, is_automatic_forward=True)
async def anti_spam(message: types.Message):
    if message.from_user.id not in ADMINS + MODERATORS:
        await message.delete()
        await bot.restrict_chat_member(message.chat.id, message.from_user.id, ChatPermissions(can_send_messages=False))

# ========== ПРИВЕТСТВИЕ НОВЫХ ========== #
@dp.message_handler(content_types=types.ContentType.NEW_CHAT_MEMBERS)
async def welcome_new_member(message: types.Message):
    for user in message.new_chat_members:
        await message.answer(WELCOME_MSG.format(
            chat_title=message.chat.title,
            user_name=user.get_mention()
        ))
    await message.delete()  # Удаляем системное сообщение

# ========== УДАЛЕНИЕ СООБЩЕНИЙ О ВЫХОДЕ ========== #
@dp.message_handler(content_types=types.ContentType.LEFT_CHAT_MEMBER)
async def delete_left_member(message: types.Message):
    await message.delete()

# ========== КОМАНДА @ADMIN ========== #
@dp.message_handler(Text(startswith="@admin"))
async def call_admin(message: types.Message):
    admins_mention = " ".join([f"👑 {admin}" for admin in ADMINS])
    await message.reply(f"Администраторы, внимание! {admins_mention}")

# ========== ЗАПУСК ========== #
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)