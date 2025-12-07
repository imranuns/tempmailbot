import os
import asyncio
import requests
import random
import string
import time
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "keep-alive"
    }

# --- 1secmail API ---

def generate_email():
    # 1secmail.comን ሙሉ ለሙሉ እናስወግዳለን (ለ Gmail ችግር ስላለበት)
    try:
        random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        # esiix.com እና wwjmp.com በጣም ፈጣን እና አስተማማኝ ናቸው
        safe_domains = ["esiix.com", "wwjmp.com"] 
        random_domain = random.choice(safe_domains)
        return f"{random_name}@{random_domain}"
    except:
        return "user123@esiix.com"

def check_email(login, domain):
    # መልእክት አለ ወይ?
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def read_message(login, domain, msg_id):
    # መልእክቱን አንብብ
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# --- Telegram Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **ሰላም! እኔ Temp Mail Bot ነኝ።**\n\nለ Facebook/TikTok መመዝገቢያ ጊዜያዊ ኢሜይል እሰራለሁ። 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # እዚህ ጋር answer() አንልም፣ Loading እንዲያሳይ እንፈልጋለን
    data = query.data

    if data == 'gen_email':
        await query.answer("⏳ ኢሜይል እየተፈጠረ ነው...")
        email = generate_email()
        
        if email:
            login, domain = email.split('@')
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=f"check|{login}|{domain}")],
                [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
            ]
            await query.edit_message_text(
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n(ይሄ ይሰራል! Gmail ላይ ሄደህ ለዚህ ኢሜይል መልእክት ላክና፣ ከ 10 ሰከንድ በኋላ 'Inbox ፈትሽ' በል)",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.answer("Error!", show_alert=True)

    elif data.startswith('check|'):
        # 🔥 ለውጥ: ዝም እንዳይል "እየፈተሸኩ ነው..." እንለዋለን
        _, login, domain = data.split('|')
        
        # አሁን ያለውን ሰዓት ለ User ለማሳየት (እንዲያውቅ)
        current_time = time.strftime("%H:%M:%S") 
        
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
        ]

        try:
            # 1. መልእክት ቀይረን "Checking..." እንበል
            try:
                await query.edit_message_text(f"⏳ Inbox እየፈተሸኩ ነው... ({current_time})", reply_markup=InlineKeyboardMarkup(keyboard))
            except:
                pass # Text ካልተቀየረ ችግር የለም

            # 2. API እንጠይቅ
            messages = check_email(login, domain)
            
            if not messages:
                # 3. መልእክት ከሌለ እንንገረው
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!** ({current_time})\n\nኢሜይሉ ገና አልደረሰ ይሆናል። ከ 5 ሰከንድ በኋላ ድጋሚ ይሞክሩ።\n\n`{login}@{domain}`",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            else:
                # 4. መልእክት ከተገኘ
                last_msg = messages[0]
                full_msg = read_message(login, domain, last_msg['id'])
                if full_msg:
                    sender = full_msg.get('from')
                    subject = full_msg.get('subject')
                    body = full_msg.get('textBody', 'No content')
                    
                    back_kb = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{login}|{domain}")]]
                    
                    await query.edit_message_text(
                        f"📬 **አዲስ መልእክት!**\n\n**ከ:** `{sender}`\n**ርዕስ:** `{subject}`\n\n{body}\n",
                        reply_markup=InlineKeyboardMarkup(back_kb), parse_mode='Markdown'
                    )
        except Exception as e:
             await query.answer(f"Error: {str(e)}", show_alert=True)
             
    elif data.startswith('back|'):
        await query.answer()
        _, login, domain = data.split('|')
        email = f"{login}@{domain}"
        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")], [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- App Setup ---
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
        return "Bot Running with Better UX! 🚀"

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
