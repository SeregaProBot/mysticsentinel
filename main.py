import sqlite3
import re
import time
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

TOKEN = "7954709613:AAFccAMIVagLzxheXI94ryTVHwqYGmwkgx4"
DEFAULT_LOG_CHANNEL_ID = -1002625004448
OWNER_ID = 692826378
ADMINS = set([OWNER_ID])
BAD_WORDS = {"плохое_слово1", "плохое_слово2", "плохое_слово3"}
LINK_PATTERN = re.compile(r"(https?://|t\.me/|telegram\.me/)")
user_message_times = {}
ANTISPAM_THRESHOLD = 3
SHLYUHO_BOT_PHRASES = {"давай знакомиться", "ищу парня", "ищу девушку"}

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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS log_channels (
        chat_id INTEGER PRIMARY KEY,
        log_channel_id INTEGER
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        chat_id INTEGER,
        user_id INTEGER,
        PRIMARY KEY (chat_id, user_id)
    )""")
    conn.commit()
    conn.close()

def get_feature(chat_id, feature):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT enabled FROM features WHERE chat_id=? AND feature_name=?", (chat_id, feature))
    row = cur.fetchone()
    conn.close()
    return row[0] == 1 if row else True

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

def get_log_channel(chat_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT log_channel_id FROM log_channels WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else DEFAULT_LOG_CHANNEL_ID

def set_log_channel(chat_id, log_channel_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO log_channels (chat_id, log_channel_id) VALUES (?, ?)", (chat_id, log_channel_id))
    conn.commit()
    conn.close()

def is_admin(chat_id, user_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    result = cur.fetchone()
    conn.close()
    return result is not None or user_id == OWNER_ID

def add_admin(chat_id, user_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO admins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
    conn.commit()
    conn.close()

def remove_admin(chat_id, user_id):
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()
    conn.close()

async def log_to_channel(context, chat_id, text, keyboard=None):
    log_channel_id = get_log_channel(chat_id)
    await context.bot.send_message(chat_id=log_channel_id, text=text, reply_markup=keyboard)

def check_spam(user_id):
    now = time.time()
    times = user_message_times.get(user_id, [])
    times = [t for t in times if now - t < 1]
    times.append(now)
    user_message_times[user_id] = times
    return len(times) > ANTISPAM_THRESHOLD

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот-модератор с SQLite и панелью управления.")

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE chat_id=?", (chat_id,))
    rows = cur.fetchall()
    conn.close()
    admin_ids = [row[0] for row in rows]
    admin_mentions = [f"[{(await context.bot.get_chat_member(chat_id, uid)).user.full_name}](tg://user?id={uid})" for uid in admin_ids]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Вызвать админа", callback_data="call_admin")]
    ])
    await update.message.reply_text("Администраторы:\n" + "\n".join(admin_mentions), parse_mode="Markdown", reply_markup=keyboard)

async def call_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    conn = sqlite3.connect("modbot_settings.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE chat_id=?", (chat_id,))
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        try:
            await context.bot.send_message(chat_id=row[0], text=f"Пользователь {query.from_user.full_name} вызвал администратора в чате {chat_id}.")
        except:
            pass
    await query.edit_message_text("Администраторы уведомлены.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not is_admin(chat_id, user_id):
        await update.message.reply_text("Нет доступа.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Антимат", callback_data="toggle:badwords"),
         InlineKeyboardButton("Антилинк", callback_data="toggle:antilink")],
        [InlineKeyboardButton("Антиспам", callback_data="toggle:antispam"),
         InlineKeyboardButton("Приветствие", callback_data="toggle:greetings")],
        [InlineKeyboardButton("Редактировать приветствие", callback_data="edit:greeting")],
        [InlineKeyboardButton("Добавить админа", callback_data="add_admin"),
         InlineKeyboardButton("Удалить админа", callback_data="remove_admin")],
        [InlineKeyboardButton("Установить лог-канал", callback_data="set_log_channel")]
    ])
    await update.message.reply_text("Панель администратора:", reply_markup=keyboard)

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    if not is_admin(chat_id, user_id):
        await query.edit_message_text("Нет доступа.")
        return
 