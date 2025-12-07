import os
import requests
import asyncio
import json
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# 🔥 ራስን እንደ እውነተኛ Browser ማስመሰል (More Headers)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive"
}

# --- 1secmail API Functions (With Short Timeout) ---

def generate_email():
    url = "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1"
    try:
        # Timeout ወደ 4 ሰከንድ ዝቅ ተደርጓል (Vercel እንዳይጨናነቅ)
        response = requests.get(url, headers=HEADERS, timeout=4).json()
        return response[0]
    except Exception as e:
        print(f"API Error (Generate): {e}")
        return None

def check_email(login, domain):
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=4).json()
        return response
    except Exception as e:
        print(f"API Error (Check): {e}")
        return []

def read_message(login, domain, msg_id):
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=4).json()
        return response
    except Exception as e:
        print(f"API Error (Read): {e}")
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
            # ፈጣን ምላሽ ለመስጠት
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
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n(Copy አድርገህ ተጠቀም፣ ኮድ ሲላክ 'Inbox ፈትሽ' በል)",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            keyboard = [[InlineKeyboardButton("🔄 ድጋሚ ሞክር", callback_data='gen_email')]]
            await query.edit_message_text("❌ የኔትወርክ ችግር! እባክህ ድጋሚ ሞክር።", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('check|'):
        try:
            _, login, domain = data.split('|')
            messages = check_email(login, domain)
            
            if not messages:
                await query.answer("📭 ባዶ ነው! ምንም መልእክት አልገባም (Refresh)", show_alert=True)
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
        except Exception as e:
             print(f"Check Error: {e}")
             await query.answer("Error checking mail", show_alert=True)

    elif data.startswith('back|'):
        _, login, domain = data.split('|')
        email = f"{login}@{domain}"
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
        ]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Vercel Route ---
@app.route('/', methods=['GET'])
def home():
    return "Bot is Running! (Loop Issue Fixed)"

@app.route('/api/index', methods=['POST'])
def webhook():
    if not TOKEN:
        return jsonify({"error": "No Token"}), 200
    try:
        # 🔥 FIX: ሁሌም አዲስ Loop እና አዲስ App መገንባት (Global መጠቀም ያቆማል)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot_app = ApplicationBuilder().token(TOKEN).build()
        loop.run_until_complete(bot_app.initialize()) # Initialize application
        
        # Handlers መጨመር
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CallbackQueryHandler(button_handler))
        
        # Update ማስተናገድ
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        loop.run_until_complete(bot_app.process_update(update))
        
        # ጨርሰን Shutdown ማድረግ
        loop.run_until_complete(bot_app.shutdown())
        loop.close()
        
        return "OK"
    except Exception as e:
        print(f"Fatal Error: {e}")
        return "OK"
