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

# 🔥 መፍትሄ: ሰርቨሩን ቀይረነዋል! (From Mail.tm -> Mails.gw)
# Mails.gw ፌስቡክ ያልዘጋቸው አዳዲስ ዶሜይኖች አሉት።
BASE_URL = "https://api.mails.gw"

# --- Helper Functions ---

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_account():
    try:
        # 1. ያሉትን ዶሜይኖች በሙሉ እናምጣ
        domains_resp = requests.get(f"{BASE_URL}/domains", timeout=5)
        if domains_resp.status_code != 200: return None
        
        domain_list = domains_resp.json()['hydra:member']
        if not domain_list: return None
        
        # 🔥 ምርምር ውጤት (Research Result): 
        # Facebook የሚወዳቸው .com, .net, .org ዶሜይኖች ካሉ እነሱን ብቻ እንምረጥ።
        # እነዚህ 'Premium' ስለሆኑ አይዘጉም።
        try:
            premium_domains = [d for d in domain_list if any(ext in d['domain'] for ext in ['.com', '.net', '.org'])]
            
            if premium_domains:
                domain_obj = random.choice(premium_domains)
            else:
                # ካልተገኘ በዘፈቀደ እንምረጥ (ግን ከ Mails.gw ስለሆነ ይሻላል)
                domain_obj = random.choice(domain_list)
        except:
            domain_obj = random.choice(domain_list)
            
        domain = domain_obj['domain']
        
        # 2. አካውንት መፍጠር
        username = get_random_string(6)
        password = get_random_string(8)
        address = f"{username}@{domain}"
        
        data = {"address": address, "password": password}
        headers = {"Content-Type": "application/json"}
        
        reg_resp = requests.post(f"{BASE_URL}/accounts", json=data, headers=headers, timeout=5)
        
        if reg_resp.status_code == 201:
            return {"email": address, "password": password}
        return None
    except:
        return None

def get_token(email, password):
    try:
        data = {"address": email, "password": password}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(f"{BASE_URL}/token", json=data, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()['token']
        return None
    except:
        return None

def check_messages(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/messages?page=1", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()['hydra:member']
        return []
    except:
        return []

def get_message_content(token, msg_id):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        # ቀጥታ መልእክቱን እናመጣለን
        resp = requests.get(f"{BASE_URL}/messages/{msg_id}", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

# --- Telegram Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🚀 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **Temp Mail Bot (Mails.gw)**\n\n"
        "ሰርቨሩ ወደ **Mails.gw** ተቀይሯል! አሁን የሚሰጠው ዶሜይኖች ለ Facebook ተመራጭ ናቸው። 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'gen_email':
        await query.answer("⚙️ Premium Domain እየፈለኩ ነው...")
        account = create_account()
        
        if account:
            email = account['email']
            password = account['password']
            callback_str = f"chk|{password}|{email}"
            
            keyboard = [
                [InlineKeyboardButton("📨 Inbox ፈትሽ", callback_data=callback_str)],
                [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            await query.edit_message_text(
                f"✅ **ኢሜይል ተፈጥሯል!**\n\n"
                f"📧 **Email:** `{email}`\n"
                f"🔑 **Password:** `{password}`\n\n"
                "⚠️ አዲሱን ሰርቨር እየተጠቀምን ነው። Facebook ላይ አስገባና **'Inbox ፈትሽ'** በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Error. Try Again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data='gen_email')]]))

    elif data.startswith('chk|'):
        try:
            _, password, email = data.split('|')
            # ቶሎ ምላሽ እንስጥ (Loading...)
            await query.answer("🔄 Inbox በመፈተሽ ላይ...")
            
            token = get_token(email, password)
            if not token:
                await query.answer("⚠️ Session Expired. አዲስ ፍጠር።", show_alert=True)
                return

            messages = check_messages(token)
            
            keyboard = [
                [InlineKeyboardButton("📨 Inbox ፈትሽ (Refresh)", callback_data=data)],
                [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            if not messages:
                # ባዶ ከሆነ ዝም እንዳይል Edit እናደርገዋለን
                try:
                    await query.edit_message_text(
                        f"📭 **ባዶ ነው!**\n\n"
                        f"👤 `{email}`\n"
                        f"🔑 `{password}`\n\n"
                        "⏳ የ Facebook ኮድ ለመምጣት ትንሽ ይቆያል። ደጋግመህ Check በል።",
                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                    )
                except:
                    pass # መልእክቱ ካልተቀየረ (ያው ከሆነ) ችግር የለም
            else:
                # መልእክት አለ!
                last_msg = messages[0]
                full_content = get_message_content(token, last_msg['id'])
                
                if full_content:
                    sender_name = full_content.get('from', {}).get('name', 'Unknown')
                    subject = full_content.get('subject', 'No Subject')
                    
                    # 🔥 ወሳኙ ለውጥ: እኛ አናጸዳውም፣ ሰርቨሩ ያጸዳውን 'text' እንቀበላለን
                    # ይሄ በጣም ፈጣን ነው!
                    body_text = full_content.get('text', '') 
                    if not body_text:
                        body_text = full_content.get('intro', 'No Content')

                    # ቆንጆ እይታ
                    formatted_msg = (
                        f"📬 **መልእክት ገብቷል!**\n"
                        f"──────────────\n"
                        f"👤 **From:** {sender_name}\n"
                        f"📌 **Subject:** {subject}\n"
                        f"──────────────\n\n"
                        f"{body_text[:3000]}" # በጣም እንዳይረዝም
                    )

                    back_kb = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{password}|{email}")]]
                    
                    await query.edit_message_text(
                        formatted_msg, 
                        reply_markup=InlineKeyboardMarkup(back_kb), 
                        parse_mode='Markdown'
                    )
        except Exception as e:
            # ስህተት ከተፈጠረ ዝም እንዳይል
            print(f"Error: {e}")
            await query.answer("❌ Error checking mail. Try again.", show_alert=True)

    elif data.startswith('back|'):
        _, password, email = data.split('|')
        callback_str = f"chk|{password}|{email}"
        keyboard = [[InlineKeyboardButton("📨 Inbox ፈትሽ", callback_data=callback_str)], [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]]
        await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`\n🔑 **Password:** `{password}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
        return "Temp Mail Bot (With Password) is Running! 🚀"

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
