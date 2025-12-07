import os
import asyncio
import requests
import random
import string
import json
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# --- Mail.tm API Functions (The Professional Choice) ---
BASE_URL = "https://api.mail.tm"

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_account():
    """
    1secmailን ትተን Mail.tm እንጠቀማለን።
    ይሄኛው በዘፈቀደ ሳይሆን Register አድርጎ ነው የሚሰጠን። (100% Legit)
    """
    try:
        # 1. Available Domains ማምጣት
        domains_resp = requests.get(f"{BASE_URL}/domains")
        if domains_resp.status_code != 200:
            return None
        
        # የመጀመሪያውን ዶሜይን እንምረጥ (ብዙ ጊዜ አዳዲስ ናቸው)
        domain = domains_resp.json()['hydra:member'][0]['domain']
        
        # 2. አካውንት መፍጠር
        username = get_random_string(6)
        password = get_random_string(5) # ቀላል ፓስወርድ
        address = f"{username}@{domain}"
        
        headers = {"Content-Type": "application/json"}
        data = {"address": address, "password": password}
        
        reg_resp = requests.post(f"{BASE_URL}/accounts", json=data, headers=headers)
        
        if reg_resp.status_code == 201:
            # ኢሜይሉን እና ፓስወርዱን እንመልሳለን (ለ Login ያስፈልጋል)
            return {"email": address, "password": password}
        return None
    except Exception as e:
        print(f"Error creating account: {e}")
        return None

def get_token(email, password):
    """ኢሜይሉን ለማንበብ Token መቀበል (Login)"""
    try:
        data = {"address": email, "password": password}
        resp = requests.post(f"{BASE_URL}/token", json=data)
        if resp.status_code == 200:
            return resp.json()['token']
        return None
    except:
        return None

def check_messages(token):
    """መልእክት መፈተሽ"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/messages", headers=headers)
        if resp.status_code == 200:
            return resp.json()['hydra:member']
        return []
    except:
        return []

def get_message_content(token, msg_id):
    """የመልእክቱን ዝርዝር ማምጣት"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/messages/{msg_id}", headers=headers)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

# --- Telegram Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **ሰላም! እኔ Temp Mail Bot (Pro) ነኝ።**\n\n"
        "አዲሱ እና አስተማማኙን Mail.tm ሰርቨር እየተጠቀምኩ ነው።\n"
        "Facebook/TikTok ለመክፈት 'አዲስ ኢሜይል' ይበሉ። 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'gen_email':
        await query.answer("⏳ አዲስ አካውንት እየከፈትኩ ነው...")
        
        # አካውንት መፍጠር
        account = create_account()
        
        if account:
            email = account['email']
            password = account['password']
            
            # 🔥 ፓስወርዱን button ላይ እንደብቀዋለን (ለ Check እንዲመች)
            # Format: chk|password|email
            callback_str = f"chk|{password}|{email}"
            
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=callback_str)],
                [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            await query.edit_message_text(
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n"
                "(ይሄ በ Mail.tm የተመዘገበ ህጋዊ ኢሜይል ነው!)\n"
                "Copy አድርገህ ተጠቀም፣ ከዚያ 'Inbox ፈትሽ' በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ ስህተት! ድጋሚ ሞክር።", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ድጋሚ ሞክር", callback_data='gen_email')]]))

    elif data.startswith('chk|'):
        # መረጃውን ከ Button መልሰን እናወጣለን
        try:
            _, password, email = data.split('|')
            
            await query.answer("⏳ Inbox እየፈተሸኩ ነው...")
            
            # 1. Login (Token ማግኘት)
            token = get_token(email, password)
            
            if not token:
                await query.answer("⚠️ Login Failed! ኢሜይሉ ጊዜው አልፎ ሊሆን ይችላል።", show_alert=True)
                return

            # 2. Messages መፈተሽ
            messages = check_messages(token)
            
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)],
                [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            if not messages:
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!**\n\n`{email}`\n\n(ኢሜይሉ ለመድረስ ትንሽ ሊቆይ ይችላል፣ ደጋግመህ ሞክር።)",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
            else:
                # መልእክት ተገኘ!
                last_msg = messages[0]
                full_content = get_message_content(token, last_msg['id'])
                
                if full_content:
                    sender = full_content.get('from', {}).get('address', 'Unknown')
                    subject = full_content.get('subject', 'No Subject')
                    body = full_content.get('text', 'No Content') # Text body
                    
                    # ወደ ኋላ መመለሻ (Original Data እንይዛለን)
                    back_kb = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{password}|{email}")]]
                    
                    await query.edit_message_text(
                        f"📬 **አዲስ መልእክት!**\n\n**ከ:** `{sender}`\n**ርዕስ:** `{subject}`\n\n**መልእክት:**\n{body[:4000]}", # ቴሌግራም ከ4096 በላይ አይቀበልም
                        reply_markup=InlineKeyboardMarkup(back_kb), parse_mode='Markdown'
                    )
        except Exception as e:
            print(f"Check Error: {e}")
            await query.answer("Error checking mail", show_alert=True)

    elif data.startswith('back|'):
        _, password, email = data.split('|')
        callback_str = f"chk|{password}|{email}"
        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=callback_str)], [InlineKeyboardButton("🔄 ሌላ አዲስ", callback_data='gen_email')]]
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
        return "Temp Mail Bot (Mail.tm Edition) is Running! 🚀"

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
