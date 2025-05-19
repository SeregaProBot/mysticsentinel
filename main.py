import sqlite3
import re
import time
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions, ChatMember
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ChatMemberHandler, CallbackQueryHandler
)

TOKEN = "7954709613:AAFccAMIVagLzxheXI94ryTVHwqYGmwkgx4"
LOG_CHANNEL_ID = -1002625004448
OWNER_ID = 692826378
ADMINS = set([OWNER_ID])
BAD_WORDS = {"плохое_слово1", "плохое_слово2"}
LINK_PATTERN = re.compile(r"(https?://|t\.me/|telegram\.me/)")
user_message_times = {}
ANTISPAM_THRESHOLD = 3

AUTO_REPLY = {
    "привет": "Привет! Чем могу помочь?",
    "как дела": "Отлично, а у тебя?",
    "шлюхобот": "Да, я здесь, чтобы помочь вам!",
    "бот": "Я бот-модератор с автоответами.",
}

def init_db():
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS greetings (
        chat_id INTEGER PRIMARY KEY,
        text TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS features (
        chat_id INTEGER,
        feature_name TEXT,
        enabled INTEGER,
        PRIMARY KEY (chat_id, feature_name)
    )""")
    conn.commit()
    conn.close()

def get_feature(chat_id, feature):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT enabled FROM features WHERE chat_id=? AND feature_name=?", (chat_id, feature))
    row = cur.fetchone()
    conn.close()
    return row[0] == 1 if row else True  # По умолчанию включено

def toggle_feature(chat_id, feature):
    current = get_feature(chat_id, feature)
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO features (chat_id, feature_name, enabled) VALUES (?, ?, ?)",
                (chat_id, feature, 0 if current else 1))
    conn.commit()
    conn.close()
    return not current

def get_greeting(chat_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT text FROM greetings WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "Привет, {name}! Добро пожаловать!"

def set_greeting(chat_id, text):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO greetings (chat_id, text) VALUES (?, ?)", (chat_id, text))
    conn.commit()
    conn.close()

async def log_to_channel(context, text, keyboard=None):
    await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот-модератор с SQLite и панелью управления.")

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
                    await context.bot.send_message(chat.id, f"{admin.user.full_name} назначен админом бота.")
                break

async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Администраторы:\n" + "\n".join(str(a) for a in ADMINS))

def check_spam(user_id):
    now = time.time()
    times = user_message_times.get(user_id, [])
    times = [t for t in times if now - t < 1]
    times.append(now)
    user_message_times[user_id] = times
    return len(times) > ANTISPAM_THRESHOLD

async def log_user_action(context, chat_id, user_id, user_name, action):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Мут", callback_data=f"mute:{user_id}:{chat_id}"),
         InlineKeyboardButton("Бан", callback_data=f"ban:{user_id}:{chat_id}")],
        [InlineKeyboardButton("Размут", callback_data=f"unmute:{user_id}:{chat_id}"),
         InlineKeyboardButton("Разбан", callback_data=f"unban:{user_id}:{chat_id}")]
    ])
    await log_to_channel(context, f"Пользователь {user_name} ({user_id}) {action}.", keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        action, user_id_str, chat_id_str = query.data.split(":")
        user_id = int(user_id_str)
        chat_id = int(chat_id_str)

        if query.from_user.id not in ADMINS:
            await query.edit_message_text("Нет доступа.")
            return

        if action == "mute":
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
            await query.edit_message_text(f"Замучен {user_id}")
        elif action == "ban":
            await context.bot.ban_chat_member(chat_id, user_id)
            await query.edit_message_text(f"Забанен {user_id}")
        elif action == "unmute":
            await context.bot.restrict_chat_member(chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=True))
            await query.edit_message_text(f"Размучен {user_id}")
        elif action == "unban":
            await context.bot.unban_chat_member(chat_id, user_id)
            await query.edit_message_text(f"Разбанен {user_id}")
    except Exception as e:
        await query.edit_message_text(f"Ошибка: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    text = message.text.lower()
    chat_id = message.chat_id

    if user.is_bot:
        return

    if get_feature(chat_id, "antispam") and check_spam(user.id):
        await message.delete()
        await log_user_action(context, chat_id, user.id, user.full_name, "спамил")
        return

    if get_feature(chat_id, "badwords") and any(word in text for word in BAD_WORDS):
        await message.delete()
        await log_user_action(context, chat_id, user.id, user.full_name, "мат")
        return

    if get_feature(chat_id, "antilink") and LINK_PATTERN.search(text):
        await message.delete()
        await log_user_action(context, chat_id, user.id, user.full_name, "ссылка")
        return

    if get_feature(chat_id, "greetings") and "привет" in text:
        greet = get_greeting(chat_id)
        await message.reply_text(greet.format(name=user.first_name))

    for trigger, reply in AUTO_REPLY.items():
        if trigger in text:
            await message.reply_text(reply)
            break

async def command_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    admins = await context.bot.get_chat_administrators(chat.id)
    mention = [f"[{a.user.first_name}](tg://user?id={a.user.id})" for a in admins]
    await update.message.reply_text("Админы: " + ", ".join(mention), parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if user.id not in ADMINS:
        await update.message.reply_text("Нет доступа.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Антимат", callback_data="toggle:badwords"),
         InlineKeyboardButton("Антилинк", callback_data="toggle:antilink")],
        [InlineKeyboardButton("Антиспам", callback_data="toggle:antispam"),
         InlineKeyboardButton("Приветствие", callback_data="toggle:greetings")],
        [InlineKeyboardButton("Редактировать приветствие", callback_data="edit:greeting")]
    ])
    await update.message.reply_text("Панель администратора:", reply_markup=keyboard)

async def callback_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data.startswith("toggle:"):
        feature = data.split(":")[1]
        status = toggle_feature(chat_id, feature)
        await query.edit_message_text(f"Функция {feature} теперь {'включена' if status else 'выключена'}.")

    elif data.startswith("edit:greeting"):
        context.user_data["edit_greeting"] = True
        await query.edit_message_text("Введите новый текст приветствия. Используйте {name} для имени пользователя.")

async def greeting_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("edit_greeting"):
        set_greeting(update.effective_chat.id, update.message.text)
        await update.message.reply_text("Приветствие обновлено.")
        context.user_data["edit_greeting"] = False

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("admin", command_admin))
    app.add_handler(CommandHandler("adminpanel", admin_panel))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r"^(mute|ban|unmute|unban):"))
    app.add_handler(CallbackQueryHandler(callback_admin_panel))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^((?!/).)*$"), message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, greeting_text_handler))

    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()