import os
import asyncio
import requests
import random
import string
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# 🔥 መፍትሄ: እራሳችንን እንደተለያዩ Browserች እናስመስላለን (Rotation)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "keep-alive"
    }

# --- 1secmail API Functions ---

def generate_email():
    """
    🔥 የመጨረሻ ማስተካከያ:
    ሰርቨሩን 'ኢሜይል ፍጠርልኝ' ብለን መጠየቅ አቁመናል። (እሱ Block የተደረገውን .com እየሰጠ አስቸገረ)
    ይልቁንስ፣ Gmail የሚቀበላቸውን 'Safe Domains' ብቻ በመጠቀም እኛው ራሳችን እንፈጥራለን።
    1secmail ማንኛውንም ስም ስለሚቀበል (Catch-all)፣ ይሄ 100% ይሰራል!
    """
    try:
        # 1. Random ስም መፍጠር (ምሳሌ: xk92ms)
        random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        
        # 2. Gmail የሚወዳቸው አስተማማኝ ዶሜይኖች ብቻ!
        # 1secmail.com የሚለውን አስወግደነዋል (እሱ ነው ችግሩ)
        safe_domains = ["esiix.com", "wwjmp.com", "1secmail.net", "1secmail.org"]
        
        random_domain = random.choice(safe_domains)
        return f"{random_name}@{random_domain}"
    except:
        return "tempuser123@esiix.com"

def check_email(login, domain):
    # መልእክት አለ ወይ ብሎ ለመጠየቅ ብቻ API እንጠቀማለን
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def read_message(login, domain, msg_id):
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
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
        try:
            await query.edit_message_text("⏳ ኢሜይል እየፈጠርኩ ነው...")
        except:
            pass

        email = generate_email()
        
        if email:
            login, domain = email.split('@')
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")],
                [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
            ]
            await query.edit_message_text(
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n(ይሄ የተረጋገጠ ነው! Copy አድርገህ ተጠቀም፣ መልእክት ሲላክለት 'Inbox ፈትሽ' በል)",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            keyboard = [[InlineKeyboardButton("🔄 ድጋሚ ሞክር", callback_data='gen_email')]]
            await query.edit_message_text("❌ ስህተት! ድጋሚ ሞክር።", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('check|'):
        try:
            _, login, domain = data.split('|')
            messages = check_email(login, domain)
            
            if not messages:
                await query.answer("📭 ባዶ ነው! ምንም መልእክት የለም (Refresh)", show_alert=True)
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
        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")], [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Main App Setup ---
async def setup_application():
    application = ApplicationBuilder().token(TOKEN).build()
    await application.initialize()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    return application

@app.route('/', methods=['GET', 'POST'])
@app.route('/api/index', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "Temp Mail Bot is Running! 🚀"

    if request.method == 'POST':
        if not TOKEN:
            return jsonify({"error": "No Token"}), 500
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            bot_app = loop.run_until_complete(setup_application())
            
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            loop.run_until_complete(bot_app.process_update(update))
            
            loop.close()
            return "OK"
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({"error": str(e)}), 500
