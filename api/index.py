import os
import asyncio
import requests
import random
import string
import json
import time
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# 🔥 እዚህ ጋር ያንተን የቴሌግራም ID አስገባ (ቁጥር ብቻ)
# ምሳሌ: ADMIN_ID = 123456789
ADMIN_ID = 123456789  # <--- ይሄን ቀይር!

# ለጊዜው ተጠቃሚዎችን እዚህ እንይዛለን (Vercel ሲዘጋ ይጠፋል፣ ለቋሚነት Database ያስፈልጋል)
users_db = set()

# --- Mail Servers (Hybrid) ---
TM_PROVIDERS = ["https://api.mail.gw", "https://api.mail.tm"]
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"

# ===========================
# 🛠️ Helper Functions (Mail)
# ===========================
def create_tm_account():
    for base_url in TM_PROVIDERS:
        try:
            domains_resp = requests.get(f"{base_url}/domains", timeout=4)
            if domains_resp.status_code != 200: continue
            domain_list = domains_resp.json()['hydra:member']
            if not domain_list: continue
            
            premium = [d for d in domain_list if any(x in d['domain'] for x in ['.com', '.net', '.org'])]
            domain_obj = random.choice(premium) if premium else random.choice(domain_list)
            
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            address = f"{username}@{domain_obj['domain']}"
            
            reg = requests.post(f"{base_url}/accounts", json={"address": address, "password": password}, headers={"Content-Type": "application/json"}, timeout=4)
            if reg.status_code == 201:
                return {"type": "tm", "email": address, "password": password, "url": base_url}
        except: continue
    return None

def check_tm_mail(account):
    try:
        token_resp = requests.post(f"{account['url']}/token", json={"address": account['email'], "password": account['password']}, headers={"Content-Type": "application/json"}, timeout=5)
        if token_resp.status_code != 200: return []
        token = token_resp.json()['token']
        
        msg_resp = requests.get(f"{account['url']}/messages?page=1", headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if msg_resp.status_code != 200: return []
        messages = msg_resp.json()['hydra:member']
        
        results = []
        for msg in messages:
            content_resp = requests.get(f"{account['url']}/messages/{msg['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=5)
            if content_resp.status_code == 200:
                full = content_resp.json()
                results.append({
                    "from": full.get('from', {}).get('address', 'Unknown'),
                    "subject": full.get('subject', 'No Subject'),
                    "body": full.get('text', '') or full.get('intro', 'No Content')
                })
        return results
    except: return []

def create_guerrilla_account():
    try:
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_address", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {"type": "gr", "email": data['email_addr'], "sid": data['sid_token']}
    except: pass
    return None

def check_guerrilla_mail(account):
    try:
        cookies = {"PHPSESSID": account['sid']}
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_list&offset=0&seq=0", cookies=cookies, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for msg in data.get('list', []):
                if msg['mail_subject'].startswith("Welcome"): continue
                results.append({"from": msg['mail_from'], "subject": msg['mail_subject'], "body": msg['mail_excerpt']})
            return results
    except: pass
    return []

# ===========================
# 🤖 Telegram Logic
# ===========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_db.add(user_id) # ተጠቃሚን መዝግብ
    
    # ዋና ሜኑ
    keyboard = [
        [InlineKeyboardButton("📧 መደበኛ (Mail.tm)", callback_data='gen_tm')],
        [InlineKeyboardButton("🔥 ለ Facebook (Guerrilla)", callback_data='gen_gr')],
        [InlineKeyboardButton("🆘 SOS እርዳታ (Support)", callback_data='ask_support')]
    ]
    
    # አድሚን ከሆነ ተጨማሪ Button ይኑረው
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📢 Admin Dashboard", callback_data='admin_panel')])

    await update.message.reply_text(
        "👋 **Temp Mail Bot (v5.0)**\n\n"
        "ፌስቡክ እምቢ ካለህ **'ለ Facebook'** የሚለውን ሞክር።\n"
        "ችግር ካጋጠመህ **'SOS እርዳታ'** የሚለውን ተጠቀም። 👇", 
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    # --- ADMIN PANEL ---
    if data == 'admin_panel':
        if user_id != ADMIN_ID: return
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast (ማስታወቂያ)", callback_data='start_broadcast')],
            [InlineKeyboardButton("📊 Users Count", callback_data='stats')],
            [InlineKeyboardButton("🔙 Back", callback_data='start_menu')]
        ]
        await query.edit_message_text("👨‍✈️ **Admin Dashboard**\nምን ማድረግ ይፈልጋሉ?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    elif data == 'stats':
        await query.answer(f"ጠቅላላ ተጠቃሚዎች: {len(users_db)}", show_alert=True)
        return

    elif data == 'start_broadcast':
        if user_id != ADMIN_ID: return
        # ሁኔታውን ወደ 'waiting_broadcast' እንቀይራለን
        context.user_data['state'] = 'waiting_broadcast'
        await query.edit_message_text(
            "📢 **Broadcast Mode**\n\n"
            "መላክ የሚፈልጉትን ማስታወቂያ (ጽሁፍ፣ ፎቶ፣ ቪዲዮ ከነ Caption) አሁን ይላኩ።\n"
            "ቦቱ ልክ እንደላኩት አድርጎ (ከነ Button) ኮፒ ያደርገዋል።\n\n"
            "ለመሰረዝ /cancel ይበሉ።",
            parse_mode='Markdown'
        )
        return

    # --- SUPPORT SYSTEM ---
    elif data == 'ask_support':
        context.user_data['state'] = 'waiting_support'
        await query.edit_message_text(
            "🆘 **Support Center**\n\n"
            "እባክዎ ያጋጠመዎትን ችግር ወይም አስተያየት እዚህ ይፃፉ።\n"
            "መልእክትዎ በቀጥታ ለ Admin ይላካል።\n\n"
            "ለመሰረዝ /cancel ይበሉ።",
            parse_mode='Markdown'
        )
        return

    # --- TEMP MAIL LOGIC ---
    elif data in ['gen_tm', 'gen_gr']:
        await query.answer("⚙️ በመፍጠር ላይ...")
        account = create_tm_account() if data == 'gen_tm' else create_guerrilla_account()
        
        if account:
            if account['type'] == 'tm':
                safe_data = f"chk|tm|{account['password']}|{account['email']}"
            else:
                safe_data = f"chk|gr|{account['sid']}"

            if len(safe_data.encode('utf-8')) > 64:
                 await query.edit_message_text("❌ Error: Data too long.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]]))
                 return

            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=safe_data)],
                [InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]
            ]
            provider_name = "Mail.tm" if account['type'] == 'tm' else "Guerrilla"
            
            await query.edit_message_text(
                f"✅ **ኢሜይል ተፈጥሯል!** ({provider_name})\n\n`{account['email']}`\n\n"
                "ይህንን Copy አድርገህ ተጠቀም። መልእክት ሲላክ **'Inbox ፈትሽ'** በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.answer("Error creating mail", show_alert=True)

    elif data == 'start_menu':
        await start(update, context) # ወደ መጀመሪያ መልስ

    elif data.startswith('chk|'):
        parts = data.split('|')
        engine = parts[1]
        await query.answer("🔄 Inbox በመፈተሽ ላይ...")
        
        messages = []
        email_display = "Unknown"
        
        if engine == 'tm':
            if len(parts) < 4: return
            password = parts[2]
            email = parts[3]
            email_display = email
            for url in TM_PROVIDERS:
                res = check_tm_mail({"url": url, "email": email, "password": password})
                if res: 
                    messages = res
                    break
        elif engine == 'gr':
            sid = parts[2]
            email_display = "Guerrilla Mail"
            messages = check_guerrilla_mail({"sid": sid})

        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)], [InlineKeyboardButton("🔙 ተመለስ", callback_data='start_menu')]]
        
        if not messages:
            current_time = time.strftime("%H:%M:%S")
            try:
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!** ({current_time})\n\n`{email_display}`\n\n"
                    "እስካሁን ምንም መልእክት የለም። ትንሽ ቆይተው ድጋሚ ይሞክሩ።",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
            except: pass
        else:
            msg = messages[0]
            text = f"📬 **መልእክት ገብቷል!**\n\n👤 **From:** {msg['from']}\n📌 **Subject:** {msg['subject']}\n\n{msg['body'][:3000]}"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- MESSAGE HANDLER (For Broadcast & Support) ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('state')
    
    # 1. BROADCAST HANDLING
    if state == 'waiting_broadcast' and user_id == ADMIN_ID:
        # መልእክቱን ኮፒ አድርጎ ለሁሉም መላክ
        success_count = 0
        fail_count = 0
        
        status_msg = await update.message.reply_text("⏳ Broadcast በመላክ ላይ...")
        
        for uid in users_db:
            if uid == ADMIN_ID: continue
            try:
                # 🔥 ወሳኙ part: copy_message ሁሉንም ነገር (Caption, Button, Media) ይወስዳል
                await context.bot.copy_message(chat_id=uid, from_chat_id=user_id, message_id=update.message.message_id)
                success_count += 1
            except Exception as e:
                fail_count += 1
        
        await status_msg.edit_text(f"✅ **Broadcast ተጠናቋል!**\n\nተላከ: {success_count}\nአልተላከም: {fail_count}")
        context.user_data['state'] = None # Reset state
        
    # 2. SUPPORT HANDLING
    elif state == 'waiting_support':
        # የተጠቃሚውን መልእክት ወደ Admin Forward ማድረግ
        if ADMIN_ID:
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"🆘 **New Support Message!**\nFrom: {update.effective_user.first_name} (ID: {user_id})")
                await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=update.message.message_id)
                await update.message.reply_text("✅ መልእክትዎ ለ Admin ተልኳል። እናመሰግናለን!")
            except:
                await update.message.reply_text("❌ መልእክቱ አልተላከም።")
        else:
            await update.message.reply_text("❌ Admin ID አልተስተካከለም።")
            
        context.user_data['state'] = None # Reset state

# --- Cancel Command ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = None
    await update.message.reply_text("❌ ተሰርዟል። /start ብለው እንደገና ይጀምሩ።")

# --- App Setup ---
async def setup_application():
    application = ApplicationBuilder().token(TOKEN).build()
    await application.initialize()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Text, Photo, Video, ወዘተ የሚቀበል Handler
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    
    return application

@app.route('/', methods=['GET', 'POST'])
@app.route('/api/index', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET': return "Bot Running with Admin Panel! 🚀"
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
