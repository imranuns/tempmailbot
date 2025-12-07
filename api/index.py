import os
import asyncio
import requests
import random
import string
import json
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from bs4 import BeautifulSoup # 🔥 አዲሱ የጽሁፍ ማጽጃ

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# --- Mail.tm API Engine ---
BASE_URL = "https://api.mail.tm"

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def clean_html_content(html_text):
    """
    🔥 Advanced Feature:
    የተዝረከረከ HTML ኮድን አጥፍቶ ንጹህ ጽሁፍ ብቻ ያወጣል።
    """
    try:
        if not html_text:
            return "No Content"
        soup = BeautifulSoup(html_text, "html.parser")
        
        # Link እንዳይጠፋ URLላቸውን እናውጣ
        for a in soup.find_all('a', href=True):
            a.replace_with(f"{a.get_text()} ({a['href']})")
            
        text = soup.get_text(separator="\n")
        
        # ባዶ ቦታዎችን ማጽዳት
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except:
        return html_text

def create_account():
    try:
        domains_resp = requests.get(f"{BASE_URL}/domains", timeout=5)
        if domains_resp.status_code != 200:
            return None
        
        domain_list = domains_resp.json()['hydra:member']
        if not domain_list:
            return None
        domain = domain_list[0]['domain']
        
        username = get_random_string(6)
        password = get_random_string(8)
        address = f"{username}@{domain}"
        
        headers = {"Content-Type": "application/json"}
        data = {"address": address, "password": password}
        
        reg_resp = requests.post(f"{BASE_URL}/accounts", json=data, headers=headers, timeout=5)
        
        if reg_resp.status_code == 201:
            return {"email": address, "password": password}
        return None
    except Exception as e:
        print(f"Error: {e}")
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
        "👋 **ሰላም! እኔ Temp Mail Bot (Advanced) ነኝ።**\n\n"
        "Facebook, TikTok እና Instagram የሚቀበሉት **Clean Email** እሰራለሁ።\n\n"
        "ለመጀመር ከታች ያለውን ይጫኑ። 👇", 
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'gen_email':
        await query.answer("⚙️ ፕሮፌሽናል አካውንት እየተከፈተ ነው...")
        
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
                "⚠️ ይህንን ኢሜይል Copy አድርገህ ተጠቀም። መልእክት ሲላክ **'Inbox ፈትሽ'** በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Error! Server Busy.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Again", callback_data='gen_email')]]))

    elif data.startswith('chk|'):
        try:
            _, password, email = data.split('|')
            await query.answer("🔄 Inbox በመታደስ ላይ...")
            
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
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!**\n\n"
                    f"👤 `{email}`\n\n"
                    "⏳ መልእክት ለመድረስ ከ 10-30 ሰከንድ ሊፈጅ ይችላል። ትንሽ ቆይተው ይሞክሩ።",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
            else:
                # መልእክት አለ! አሁን እናሳምረው
                last_msg = messages[0]
                full_content = get_message_content(token, last_msg['id'])
                
                if full_content:
                    sender_name = full_content.get('from', {}).get('name', '')
                    sender_addr = full_content.get('from', {}).get('address', 'Unknown')
                    subject = full_content.get('subject', '(No Subject)')
                    
                    # 🔥 HTML Clean Up Logic
                    raw_html = full_content.get('html', [])
                    if raw_html:
                        body_text = clean_html_content(raw_html[0])
                    else:
                        body_text = full_content.get('text', 'No Content')

                    # ቆንጆ እይታ (Format)
                    formatted_msg = (
                        f"📬 **አዲስ መልእክት ገብቷል!**\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"👤 **From:** {sender_name} (`{sender_addr}`)\n"
                        f"📌 **Subject:** {subject}\n"
                        f"━━━━━━━━━━━━━━━━\n\n"
                        f"{body_text[:3500]}" # ቴሌግራም እንዳይጨናነቅ እንቆርጠዋለን
                    )

                    back_kb = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{password}|{email}")]]
                    
                    await query.edit_message_text(
                        formatted_msg, 
                        reply_markup=InlineKeyboardMarkup(back_kb), 
                        parse_mode='Markdown'
                    )
        except Exception as e:
            print(f"Error: {e}")
            await query.answer("Error checking mail", show_alert=True)

    elif data.startswith('back|'):
        _, password, email = data.split('|')
        callback_str = f"chk|{password}|{email}"
        keyboard = [[InlineKeyboardButton("📨 Inbox ፈትሽ", callback_data=callback_str)], [InlineKeyboardButton("♻️ ሌላ አዲስ", callback_data='gen_email')]]
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
        return "Temp Mail Bot (Advanced) is Running! 🚀"

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
