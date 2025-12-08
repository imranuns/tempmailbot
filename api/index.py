import os
import requests
import random
import string
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# 🔥 FIX: Get ADMIN_ID from Environment Variable (Safe for GitHub)
# Don't forget to add 'ADMIN_ID' in Vercel Settings!
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

# ለ Broadcast ተጠቃሚዎችን መያዣ (ማሳሰቢያ: Vercel ላይ ይሄ ቋሚ አይደለም)
users_db = set()

# --- Engines ---
TM_PROVIDERS = ["https://api.mail.gw", "https://api.mail.tm"]
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"

# ===========================
# 🛠️ Helper Functions
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

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ይሄ IDህን ለማወቅ የሚረዳ ድብቅ ኮድ ነው"""
    await update.message.reply_text(f"🆔 ያንተ መታወቂያ ቁጥር: `{update.effective_user.id}`\n\nይሄንን ቁጥር Vercel ላይ 'ADMIN_ID' በሚል Environment Variable አስገባው።", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_db.add(user_id) 
    context.user_data['state'] = None # Clear any previous state

    # ዋና ሜኑ አቀራረብ
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("📩 ኢሜይል ፍጠር (Standard)", callback_data='gen_tm')],
        [InlineKeyboardButton("🔥 አማራጭ (Alternative)", callback_data='gen_gr')],
        [InlineKeyboardButton("🆘 እርዳታ (Support)", callback_data='ask_support')]
    ]
    
    # Admin መሆኑን ማረጋገጥ (ቁጥሩ ትክክል ከሆነ ብቻ ይታያል)
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📢 Admin Dashboard", callback_data='admin_panel')])

    text = (
        "👋 **Temp Mail Bot**\n\n"
        "ለማንኛውም ድረገጽ እና ሶሻል ሚዲያ ምዝገባ የሚሆን ጊዜያዊ ኢሜይል ያግኙ።\n"
        "አንኛው ሰርቨር ካልሰራ፣ 'አማራጭ' የሚለውን ይሞክሩ። 👇"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    # --- ADMIN PANEL ---
    if data == 'admin_panel':
        if user_id != ADMIN_ID: 
            await query.answer("⛔ Access Denied!", show_alert=True)
            return
            
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast (ማስታወቂያ)", callback_data='start_broadcast')],
            [InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]
        ]
        await query.edit_message_text("👨‍✈️ **Admin Dashboard**\n\nማስታወቂያ ለተጠቃሚዎች መላክ ይችላሉ።", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    elif data == 'start_broadcast':
        if user_id != ADMIN_ID: return
        context.user_data['state'] = 'waiting_broadcast'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel_action')]]
        await query.edit_message_text(
            "📢 **Broadcast Mode**\n\n"
            "መላክ የሚፈልጉትን ማስታወቂያ (ጽሁፍ፣ ፎቶ፣ አዝራር) አሁን ይላኩ።\n"
            "ልክ እንደላኩት አድርጌ ኮፒ አደርገዋለሁ።",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    # --- SUPPORT SYSTEM ---
    elif data == 'ask_support':
        context.user_data['state'] = 'waiting_support'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel_action')]]
        await query.edit_message_text(
            "🆘 **Support Center**\n\n"
            "እባክዎ ያጋጠመዎትን ችግር እዚህ ይፃፉ። መልእክቱ በቀጥታ ለቦቱ ባለቤት ይላካል።",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
        
    elif data == 'cancel_action':
        context.user_data['state'] = None
        await show_main_menu(update, context)
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
                 await query.edit_message_text("❌ Error. Retry.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]]))
                 return

            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=safe_data)],
                [InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]
            ]
            
            # ስም መቀየር (Generic Name)
            provider_name = "Standard Mail" if account['type'] == 'tm' else "Alternative Mail"
            
            await query.edit_message_text(
                f"✅ **ኢሜይል ተፈጥሯል!** ({provider_name})\n\n`{account['email']}`\n\n"
                "ይህንን Copy አድርገው ይጠቀሙ። መልእክት ሲላክ **'Inbox ፈትሽ'** በል።",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
        else:
            await query.answer("Server Error. Try again.", show_alert=True)

    elif data == 'start_menu':
        await show_main_menu(update, context)

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
            email_display = "Alternative Mail"
            messages = check_guerrilla_mail({"sid": sid})

        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)], [InlineKeyboardButton("🔙 ተመለስ", callback_data='start_menu')]]
        
        if not messages:
            try:
                await query.edit_message_text(
                    f"📭 **Inbox ባዶ ነው!**\n\n`{email_display}`\n\n"
                    "እስካሁን ምንም መልእክት የለም። ኮድ ለመምጣት ጊዜ ሊወስድ ስለሚችል ትንሽ ቆይተው ድጋሚ ይሞክሩ።",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
            except: pass
        else:
            msg = messages[0]
            text = f"📬 **መልእክት ገብቷል!**\n\n👤 **From:** {msg['from']}\n📌 **Subject:** {msg['subject']}\n\n{msg['body'][:3000]}"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('state')
    
    # 1. BROADCAST
    if state == 'waiting_broadcast' and user_id == ADMIN_ID:
        success = 0
        status_msg = await update.message.reply_text("⏳ Broadcast በመላክ ላይ...")
        
        # ማስታወሻ: Vercel ላይ users_db ጊዜያዊ ነው።
        # በቋሚነት ለመስራት Database ያስፈልጋል።
        temp_users = list(users_db)
        if not temp_users:
             await status_msg.edit_text("❌ ምንም ተጠቃሚ አልተገኘም (Database Empty).")
             context.user_data['state'] = None
             return

        for uid in temp_users:
            if uid == ADMIN_ID: continue
            try:
                # ሙሉ ሜሴጁን ኮፒ ማድረግ (Copy Message)
                await context.bot.copy_message(chat_id=uid, from_chat_id=user_id, message_id=update.message.message_id)
                success += 1
            except: pass
        
        await status_msg.edit_text(f"✅ ተላከ: {success}")
        context.user_data['state'] = None
        
    # 2. SUPPORT
    elif state == 'waiting_support':
        if ADMIN_ID:
            try:
                # መልእክቱን ለአድሚኑ Forward ማድረግ
                user_info = f"🆘 **New Support!**\nUser: {update.effective_user.first_name} (ID: `{user_id}`)"
                await context.bot.send_message(chat_id=ADMIN_ID, text=user_info, parse_mode='Markdown')
                await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=update.message.message_id)
                
                await update.message.reply_text("✅ መልእክትዎ ተልኳል። እናመሰግናለን!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]]))
            except Exception as e:
                await update.message.reply_text(f"❌ Error sending to admin: {e}")
        else:
            await update.message.reply_text("❌ Admin ID አልተሞላም።")
            
        context.user_data['state'] = None

async def setup_application():
    application = ApplicationBuilder().token(TOKEN).build()
    await application.initialize()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_id)) # ID ማወቂያ
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    
    return application

@app.route('/', methods=['GET', 'POST'])
@app.route('/api/index', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET': return "Bot Running! 🚀"
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
