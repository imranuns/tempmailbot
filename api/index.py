import os
import asyncio
import requests
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# --- Helper Functions ---
def generate_email():
    try:
        url = "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1"
        return requests.get(url).json()[0]
    except:
        return None

def check_email(login, domain):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
        return requests.get(url).json()
    except:
        return []

def read_message(login, domain, msg_id):
    try:
        url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
        return requests.get(url).json()
    except:
        return None

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]]
    await update.message.reply_text(
        "👋 **ሰላም! እኔ Temp Mail Bot ነኝ።**\n\nለ Facebook/TikTok መመዝገቢያ ጊዜያዊ ኢሜይል እሰራለሁ። 👇", 
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'gen_email':
        email = generate_email()
        if email:
            login, domain = email.split('@')
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")],
                [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
            ]
            await query.edit_message_text(
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n(Copy አድርገህ ተጠቀም፣ ኮድ ሲላክ 'Inbox ፈትሽ' በል)",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
    elif data.startswith('check|'):
        try:
            _, login, domain = data.split('|')
            messages = check_email(login, domain)
            if not messages:
                await query.answer("📭 ምንም መልእክት የለም!", show_alert=True)
            else:
                full_msg = read_message(login, domain, messages[0]['id'])
                if full_msg:
                    sender = full_msg.get('from')
                    subject = full_msg.get('subject')
                    body = full_msg.get('textBody', 'No content')
                    keyboard = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{login}|{domain}")]]
                    await query.edit_message_text(
                        f"📬 **መልእክት:**\n\n**ከ:** `{sender}`\n**ርዕስ:** `{subject}`\n\n{body}\n",
                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                    )
        except:
             await query.answer("Error checking mail", show_alert=True)
    elif data.startswith('back|'):
        _, login, domain = data.split('|')
        email = f"{login}@{domain}"
        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")], [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Main App Setup ---
global_bot_app = None

async def get_bot_app():
    global global_bot_app
    if global_bot_app is None:
        global_bot_app = ApplicationBuilder().token(TOKEN).build()
        await global_bot_app.initialize()
        global_bot_app.add_handler(CommandHandler("start", start))
        global_bot_app.add_handler(CallbackQueryHandler(button_handler))
    return global_bot_app

@app.route('/', methods=['GET', 'POST'])
@app.route('/api/index', methods=['GET', 'POST'])
def handler():
    if request.method == 'GET':
        return "Temp Mail Bot is Running! 🚀"

    if request.method == 'POST':
        if not TOKEN:
            return jsonify({"error": "No Token"}), 500
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot_app = loop.run_until_complete(get_bot_app())
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            loop.run_until_complete(bot_app.process_update(update))
            loop.close()
            return "OK"
        except Exception as e:
            return jsonify({"error": str(e)}), 500
