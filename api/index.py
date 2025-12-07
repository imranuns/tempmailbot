import os
import asyncio
import requests
import random
import string
import json
import time
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# ==========================================
# 🔧 Engine 1: Mail.tm & Mail.gw (Standard)
# ==========================================
TM_PROVIDERS = ["https://api.mail.gw", "https://api.mail.tm"]

def create_tm_account():
    for base_url in TM_PROVIDERS:
        try:
            domains_resp = requests.get(f"{base_url}/domains", timeout=4)
            if domains_resp.status_code != 200: continue
            
            domain_list = domains_resp.json()['hydra:member']
            if not domain_list: continue
            
            # Premium የሚመስሉትን እንምረጥ
            premium = [d for d in domain_list if any(x in d['domain'] for x in ['.com', '.net', '.org'])]
            domain_obj = random.choice(premium) if premium else random.choice(domain_list)
            
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            address = f"{username}@{domain_obj['domain']}"
            
            reg = requests.post(f"{base_url}/accounts", json={"address": address, "password": password}, headers={"Content-Type": "application/json"}, timeout=4)
            
            if reg.status_code == 201:
                return {"type": "tm", "email": address, "password": password, "url": base_url}
        except:
            continue
    return None

def check_tm_mail(account):
    try:
        # Get Token
        token_resp = requests.post(f"{account['url']}/token", json={"address": account['email'], "password": account['password']}, headers={"Content-Type": "application/json"}, timeout=5)
        if token_resp.status_code != 200: return []
        token = token_resp.json()['token']
        
        # Get Messages
        msg_resp = requests.get(f"{account['url']}/messages?page=1", headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if msg_resp.status_code != 200: return []
        messages = msg_resp.json()['hydra:member']
        
        results = []
        for msg in messages:
            # Get Content
            content_resp = requests.get(f"{account['url']}/messages/{msg['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=5)
            if content_resp.status_code == 200:
                full = content_resp.json()
                results.append({
                    "from": full.get('from', {}).get('address', 'Unknown'),
                    "subject": full.get('subject', 'No Subject'),
                    "body": full.get('text', '') or full.get('intro', 'No Content')
                })
        return results
    except:
        return []

# ==========================================
# 🛠️ Engine 2: Guerrilla Mail (Old but Gold)
# ==========================================
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"

def create_guerrilla_account():
    try:
        # አዲስ Session እንፈጥራለን
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_address", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # sid_token በጣም ወሳኝ ነው (እንደ Password ያገለግላል)
            return {
                "type": "gr", 
                "email": data['email_addr'], 
                "sid": data['sid_token']
            }
    except:
        pass
    return None

def check_guerrilla_mail(account):
    try:
        # መልእክት ለመፈተሽ sid ያስፈልጋል (Cookie)
        cookies = {"PHPSESSID": account['sid']}
        # seq=0 ማለት ሁሉንም አዲስ መልእክት አምጣ ማለት ነው
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_list&offset=0&seq=0", cookies=cookies, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for msg in data.get('list', []):
                # Guerrilla የመጀመሪያውን የ Welcome መልእክት ይልካል፣ እሱን እንዝለለው
                if msg['mail_subject'].startswith("Welcome"): continue
                
                results.append({
                    "from": msg['mail_from'],
                    "subject": msg['mail_subject'],
                    "body": msg['mail_excerpt'] # Guerrilla ሙሉ Body በ API ለመስጠት ያስቸግራል፣ Excerpt ይሻላል
                })
            return results
    except:
        pass
    return []

# ==========================================
# 🤖 Telegram Logic
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📧 መደበኛ ኢሜይል (Standard)", callback_data='gen_tm')],
        [InlineKeyboardButton("🔥 አማራጭ ሰርቨር (Alternative)", callback_data='gen_gr')]
    ]
    await update.message.reply_text(
        "👋 **Temp Mail Bot (Hybrid)**\n\n"
        "ለማንኛውም ድረገጽ ምዝገባ የሚሆን ጊዜያዊ ኢሜይል ያግኙ።\n"
        "አንኛው ሰርቨር እምቢ ካለ፣ ሌላኛው አማራጭ ሊሰራ ይችላል። 👇", 
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # --- GENERATE HANDLERS ---
    if data in ['gen_tm', 'gen_gr']:
        await query.answer("⚙️ በመፍጠር ላይ...")
        
        if data == 'gen_tm':
            account = create_tm_account()
        else:
            account = create_guerrilla_account()
            
        if account:
            if account['type'] == 'tm':
                safe_data = f"chk|tm|{account['password']}|{account['email']}"
            else:
                safe_data = f"chk|gr|{account['sid']}"

            if len(safe_data.encode('utf-8')) > 64:
                 await query.edit_message_text("❌ ኢሜይሉ በጣም ረዘመ! እባክህ እንደገና ሞክር።", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]]))
                 return

            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=safe_data)],
                [InlineKeyboardButton("🔄 ሌላ አይነት", callback_data='start_menu')]
            ]
            
            provider_name = "Standard" if account['type'] == 'tm' else "Alternative"
            
            await query.edit_message_text(
                f"✅ **ኢሜይል ተፈጥሯል!** ({provider_name})\n\n"
                f"`{account['email']}`\n\n"
                "ይህንን Copy አድርገው በተፈለገው ድረገጽ ላይ ይጠቀሙ። መልእክት ሲላክ **'Inbox ፈትሽ'** ይበሉ።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.answer("Error creating mail", show_alert=True)

    elif data == 'start_menu':
        # ወደ ዋና ሜኑ መመለስ
        keyboard = [
            [InlineKeyboardButton("📧 መደበኛ ኢሜይል (Standard)", callback_data='gen_tm')],
            [InlineKeyboardButton("🔥 አማራጭ ሰርቨር (Alternative)", callback_data='gen_gr')]
        ]
        await query.edit_message_text("የሚፈልጉትን የኢሜይል አይነት ይምረጡ:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- CHECK HANDLERS ---
    elif data.startswith('chk|'):
        parts = data.split('|')
        engine = parts[1]
        
        await query.answer("🔄 Inbox በመፈተሽ ላይ...")
        
        messages = []
        email_display = "Unknown"
        
        if engine == 'tm':
            # chk|tm|pass|email
            if len(parts) < 4: return
            password = parts[2]
            email = parts[3]
            email_display = email
            for url in TM_PROVIDERS:
                acct = {"url": url, "email": email, "password": password}
                res = check_tm_mail(acct)
                if res: 
                    messages = res
                    break
                    
        elif engine == 'gr':
            # chk|gr|sid
            sid = parts[2]
            email_display = "Alternative Mail" 
            messages = check_guerrilla_mail({"sid": sid})

        # ውጤት ማሳየት
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)],
            [InlineKeyboardButton("🔙 ተመለስ", callback_data='start_menu')]
        ]
        
        if not messages:
            current_time = time.strftime("%H:%M:%S")
            try:
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!** ({current_time})\n\n"
                    f"ኢሜይል: `{email_display}`\n\n"
                    "እስካሁን ምንም መልእክት የለም። ኮድ ለመላክ ጊዜ ሊወስድ ስለሚችል እባክዎ ትንሽ ቆይተው ድጋሚ ይሞክሩ።",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
            except:
                pass
        else:
            # መልእክት አለ!
            msg = messages[0]
            text = (
                f"📬 **መልእክት ገብቷል!**\n\n"
                f"👤 **From:** {msg['from']}\n"
                f"📌 **Subject:** {msg['subject']}\n\n"
                f"{msg['body'][:3000]}"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
        return "Hybrid Bot Running! 🚀"
    if request.method == 'POST':
        if not TOKEN: return jsonify({"error": "No Token"}), 500
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
