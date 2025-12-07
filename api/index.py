import os
import requests
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Setup ---
app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# --- 1secmail API Functions ---

def generate_email():
    url = "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1"
    try:
        response = requests.get(url).json()
        return response[0]
    except:
        return None

def check_email(login, domain):
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    try:
        response = requests.get(url).json()
        return response
    except:
        return []

def read_message(login, domain, msg_id):
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        response = requests.get(url).json()
        return response
    except:
        return None

# --- Telegram Bot Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **ሰላም! እኔ Temp Mail Bot ነኝ።**\n\nለ Facebook/TikTok መመዝገቢያ ጊዜያዊ ኢሜይል እሰራለሁ። 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
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
                last_msg = messages[0]
                full_msg = read_message(login, domain, last_msg['id'])
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
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
        ]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Main Bot Application ---
# Global application instance to avoid rebuilding on every request
global_app = None

async def get_application():
    global global_app
    if global_app is None:
        global_app = ApplicationBuilder().token(TOKEN).build()
        await global_app.initialize()
        global_app.add_handler(CommandHandler("start", start))
        global_app.add_handler(CallbackQueryHandler(button_handler))
    return global_app

# --- Vercel Route (Flask) ---

@app.route('/', methods=['GET'])
def home():
    return "Temp Mail Bot is Running! 🚀 (Use POST for Webhook)"

@app.route('/api/index', methods=['POST'])
def webhook():
    if not TOKEN:
        return jsonify({"error": "No Token"}), 500
        
    try:
        # Run async code inside Flask
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot_app = loop.run_until_complete(get_application())
        
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        loop.run_until_complete(bot_app.process_update(update))
        loop.close()
        
        return "OK"
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# For local testing
if __name__ == '__main__':
    app.run(debug=True)
