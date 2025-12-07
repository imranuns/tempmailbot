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

# 🔥 ሁለት ሞተሮች (Primary & Backup)
# Mails.gw ከተበላሸ (500 Error) ወደ Mail.tm እንቀይራለን
PROVIDERS = [
    "https://api.mail.gw",  # ምርጥ (Premium)
    "https://api.mail.tm"   # መጠባበቂያ (Backup)
]

# --- Helper Functions ---

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_account():
    """
    ሁለቱንም ሰርቨሮች በየተራ ይሞክራል።
    gw ካልሰራ tm ይተካል።
    """
    for base_url in PROVIDERS:
        try:
            # 1. ዶሜይን ማምጣት
            domains_resp = requests.get(f"{base_url}/domains", timeout=5)
            if domains_resp.status_code != 200: 
                continue # ይሄ ካልሰራ ወደ ቀጣዩ ሰርቨር ዝለል
            
            domain_list = domains_resp.json()['hydra:member']
            if not domain_list: continue
            
            # ለ Facebook የሚሆኑ ምርጥ ዶሜይኖችን እንፈልግ
            try:
                premium_domains = [d for d in domain_list if any(ext in d['domain'] for ext in ['.com', '.net', '.org'])]
                domain_obj = random.choice(premium_domains) if premium_domains else random.choice(domain_list)
            except:
                domain_obj = random.choice(domain_list)
                
            domain = domain_obj['domain']
            
            # 2. አካውንት መፍጠር
            username = get_random_string(6)
            password = get_random_string(8)
            address = f"{username}@{domain}"
            
            data = {"address": address, "password": password}
            headers = {"Content-Type": "application/json"}
            
            reg_resp = requests.post(f"{base_url}/accounts", json=data, headers=headers, timeout=5)
            
            if reg_resp.status_code == 201:
                # የትኛው ሰርቨር እንደሰራ አብረን እንመልስ (gw ወይስ tm)
                # 0 = gw, 1 = tm
                provider_id = PROVIDERS.index(base_url)
                return {"email": address, "password": password, "p_id": provider_id}
        except:
            continue
            
    return None

def get_token(email, password, provider_url):
    try:
        data = {"address": email, "password": password}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(f"{provider_url}/token", json=data, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()['token']
        return None
    except:
        return None

def check_messages(token, provider_url):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{provider_url}/messages?page=1", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()['hydra:member']
        return []
    except:
        return []

def get_message_content(token, msg_id, provider_url):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{provider_url}/messages/{msg_id}", headers=headers, timeout=5)
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
        "👋 **Temp Mail Bot (Hybrid Engine)**\n\n"
        "አንዱ ሰርቨር ቢበላሽ በሌላው የሚሰራ አስተማማኝ ቦት! 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'gen_email':
        await query.answer("⚙️ ምርጥ ሰርቨር እየፈለኩ ነው...")
        account = create_account()
        
        if account:
            email = account['email']
            password = account['password']
            p_id = account['p_id'] # የትኛው ሰርቨር እንደሆነ
            
            # Callback: chk|p_id|password|email
            callback_str = f"chk|{p_id}|{password}|{email}"
            
            keyboard = [
                [InlineKeyboardButton("📨 Inbox ፈትሽ", callback_data=callback_str)],
                [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            provider_name = "Mails.gw" if p_id == 0 else "Mail.tm"
            
            await query.edit_message_text(
                f"✅ **ኢሜይል ተፈጥሯል!** ({provider_name})\n\n"
                f"📧 **Email:** `{email}`\n"
                f"🔑 **Password:** `{password}`\n\n"
                "⚠️ Facebook ላይ ይህን ኢሜይል አስገባና Code ሲልክልህ **'Inbox ፈትሽ'** በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            # 🔥 Fix Crash: ሰዓት በመጨመር መልእክቱ ሁሌም አዲስ እንዲሆን እናደርጋለን
            current_time = int(time.time())
            await query.edit_message_text(
                f"❌ የኔትወርክ ችግር ({current_time})። እባክህ እንደገና ሞክር።", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ድጋሚ ሞክር", callback_data='gen_email')]])
            )

    elif data.startswith('chk|'):
        try:
            parts = data.split('|')
            # ፎርማቱ 4 ክፍል አለው: chk, p_id, password, email
            if len(parts) != 4:
                await query.answer("Error: Old format. Create new mail.", show_alert=True)
                return

            _, p_id_str, password, email = parts
            p_id = int(p_id_str)
            provider_url = PROVIDERS[p_id] # ትክክለኛውን ሰርቨር እንመርጣለን
            
            await query.answer(f"🔄 Inbox በመፈተሽ ላይ... ({'GW' if p_id==0 else 'TM'})")
            
            token = get_token(email, password, provider_url)
            if not token:
                await query.answer("⚠️ Session Expired or Server Error.", show_alert=True)
                return

            messages = check_messages(token, provider_url)
            
            keyboard = [
                [InlineKeyboardButton("📨 Inbox ፈትሽ (Refresh)", callback_data=data)],
                [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]
            ]
            
            if not messages:
                # Fix Crash here too
                try:
                    current_time = time.strftime("%H:%M:%S")
                    await query.edit_message_text(
                        f"📭 **ባዶ ነው!** ({current_time})\n\n"
                        f"👤 `{email}`\n"
                        f"🔑 `{password}`\n\n"
                        "⏳ የ Facebook ኮድ ለመምጣት ትንሽ ይቆያል። ደጋግመህ Check በል።",
                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                    )
                except:
                    pass 
            else:
                last_msg = messages[0]
                full_content = get_message_content(token, last_msg['id'], provider_url)
                
                if full_content:
                    sender_name = full_content.get('from', {}).get('name', 'Unknown')
                    subject = full_content.get('subject', 'No Subject')
                    body_text = full_content.get('text', '') or full_content.get('intro', 'No Content')

                    formatted_msg = (
                        f"📬 **መልእክት ገብቷል!**\n"
                        f"──────────────\n"
                        f"👤 **From:** {sender_name}\n"
                        f"📌 **Subject:** {subject}\n"
                        f"──────────────\n\n"
                        f"{body_text[:3000]}"
                    )

                    back_kb = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{p_id}|{password}|{email}")]]
                    
                    await query.edit_message_text(
                        formatted_msg, 
                        reply_markup=InlineKeyboardMarkup(back_kb), 
                        parse_mode='Markdown'
                    )
        except Exception as e:
            print(f"Error: {e}")
            await query.answer("❌ Error checking mail.", show_alert=True)

    elif data.startswith('back|'):
        try:
            _, p_id, password, email = data.split('|')
            callback_str = f"chk|{p_id}|{password}|{email}"
            keyboard = [[InlineKeyboardButton("📨 Inbox ፈትሽ", callback_data=callback_str)], [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]]
            await query.edit_message_text(f"✅ **ኢሜይልህ:**\n`{email}`\n🔑 **Password:** `{password}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except:
             await query.edit_message_text("Error loading back.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("New", callback_data='gen_email')]]))

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
        return "Temp Mail Bot (Hybrid Mode) is Running! 🚀"

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
