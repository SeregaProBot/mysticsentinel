from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions, ChatMember
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ChatMemberHandler, CallbackQueryHandler
)
import re
import asyncio
import time

TOKEN = "7954709613:AAFccAMIVagLzxheXI94ryTVHwqYGmwkgx4"
LOG_CHANNEL_ID = -1002625004448
OWNER_ID = 692826378

ADMINS = set()
ADMINS.add(OWNER_ID)

ANTISPAM_THRESHOLD = 3
user_message_times = {}

BAD_WORDS = {"плохое_слово1", "плохое_слово2"}
LINK_PATTERN = re.compile(r"(https?://|t\.me/|telegram\.me/)")

AUTO_REPLY = {
    "привет": "Привет! Чем могу помочь?",
    "как дела": "Отлично, а у тебя?",
    "шлюхобот": "Да, я здесь, чтобы помочь вам!",
    "бот": "Я бот-модератор с автоответами.",
}

GREETINGS = {}
USER_LEVELS = {}

async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, text: str, keyboard=None):
    await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот-модератор с автоответами и полным функционалом.")

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.my_chat_member
    new_status = chat_member.new_chat_member.status
    chat = chat_member.chat

    if new_status in ("administrator", "member"):
        admins = await context.bot.get_chat_administrators(chat.id)
        for admin in admins:
            if admin.status == "creator":
                owner_id = admin.user.id
                if owner_id not in ADMINS:
                    ADMINS.add(owner_id)
                    await context.bot.send_message(chat.id, f"Пользователь {admin.user.full_name} назначен администратором бота.")
                break

async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(ADMINS) == 0:
        await update.message.reply_text("Пока нет администраторов.")
    else:
        text = "Администраторы бота:\n" + "\n".join(str(a) for a in ADMINS)
        await update.message.reply_text(text)

def check_spam(user_id):
    now = time.time()
    times = user_message_times.get(user_id, [])
    times = [t for t in times if now - t < 1]
    times.append(now)
    user_message_times[user_id] = times
    return len(times) > ANTISPAM_THRESHOLD

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split(":")
    if len(parts) != 3:
        return
    action, user_id_str, chat_id_str = parts
    user_id = int(user_id_str)
    chat_id = int(chat_id_str)

    if query.from_user.id not in ADMINS:
        await query.edit_message_text("Только администраторы могут использовать эти кнопки.")
        return

    try:
        if action == "mute":
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            await query.edit_message_text(f"Пользователь {user_id} замучен.")
        elif action == "ban":
            await context.bot.ban_chat_member(chat_id, user_id)
            await query.edit_message_text(f"Пользователь {user_id} забанен.")
        elif action == "unmute":
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=True,
                                            can_send_media_messages=True,
                                            can_send_other_messages=True,
                                            can_add_web_page_previews=True)
            )
            await query.edit_message_text(f"Пользователь {user_id} размучен.")
        elif action == "unban":
            await context.bot.unban_chat_member(chat_id, user_id)
            await query.edit_message_text(f"Пользователь {user_id} разбанен.")
    except Exception as e:
        await query.edit_message_text(f"Ошибка: {e}")

async def log_user_action(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id, user_name, action):
    text = f"В чате {chat_id} пользователь {user_name} ({user_id}) {action}."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Мут", callback_data=f"mute:{user_id}:{chat_id}"),
         InlineKeyboardButton("Бан", callback_data=f"ban:{user_id}:{chat_id}")],
        [InlineKeyboardButton("Размут", callback_data=f"unmute:{user_id}:{chat_id}"),
         InlineKeyboardButton("Разбан", callback_data=f"unban:{user_id}:{chat_id}")]
    ])
    await log_to_channel(context, text, keyboard)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    text = message.text.lower()

    if user.is_bot:
        return

    if check_spam(user.id):
        try:
            await message.delete()
        except:
            pass
        await log_user_action(context, message.chat_id, user.id, user.full_name, "спамил (сообщение удалено)")
        return

    if any(bad_word in text for bad_word in BAD_WORDS):
        try:
            await message.delete()
        except:
            pass
        await log_user_action(context, message.chat_id, user.id, user.full_name, "использовал мат (сообщение удалено)")
        return

    if LINK_PATTERN.search(text):
        try:
            await message.delete()
        except:
            pass
        await log_user_action(context, message.chat_id, user.id, user.full_name, "разместил ссылку (сообщение удалено)")
        return

    if "привет" in text:
        greet_text = GREETINGS.get(message.chat_id, "Привет, {name}! Добро пожаловать!")
        await message.reply_text(greet_text.format(name=user.first_name))

    for trigger, response in AUTO_REPLY.items():
        if trigger in text:
            await message.reply_text(response)
            break

async def command_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    admins_in_chat = await context.bot.get_chat_administrators(chat.id)
    mentions = []
    for admin in admins_in_chat:
        user = admin.user
        mentions.append(f"[{user.first_name}](tg://user?id={user.id})")
    await update.message.reply_text("Администраторы чата: " + ", ".join(mentions), parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("У вас нет доступа к админ-панели.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть админ-панель", callback_data="admin_panel_open")]
    ])
    await update.message.reply_text("Панель администратора:", reply_markup=keyboard)

async def callback_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "admin_panel_open":
        text = "Администраторы бота:\n" + "\n".join(str(a) for a in ADMINS)
        await query.edit_message_text(text)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("admin", command_admin))
    app.add_handler(CommandHandler("adminpanel", admin_panel))

    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r"^(mute|ban|unmute|unban):\d+:-?\d+$"))
    app.add_handler(CallbackQueryHandler(callback_admin_panel, pattern="admin_panel_open"))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()