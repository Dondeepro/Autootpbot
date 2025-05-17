from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from twilio.rest import Client
import datetime
import json
import re

# User data storage
user_credentials = {}
user_states = {}
user_numbers = {}
last_message_ids = {}
user_twilio_auth = {}

# Load allowed usernames
def load_allowed_usernames():
    with open('allowed_users.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Start command with reply keyboard
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🔐 Login")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Welcome! Please login below:", reply_markup=reply_markup)

# Reply-based logout
async def logout_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_credentials.pop(user.id, None)
    user_states.pop(user.id, None)
    user_numbers.pop(user.id, None)
    user_twilio_auth.pop(user.id, None)

    keyboard = [[KeyboardButton("🔐 Login")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("You have been logged out. Please log in again to continue.", reply_markup=reply_markup)

# Login flow and all inputs
async def receive_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

 # New part: detect 'number 🟡 Try later'
    match = re.search(r'(\d{10,11})\s*🟡\s*Try later', text)
    if match:
        raw_number = match.group(1)
        formatted_number = '+' + raw_number
        keyboard = [[InlineKeyboardButton("Buy", callback_data=f"manual_buy:{formatted_number}")]]
        await update.message.reply_text(f"{formatted_number}", reply_markup=InlineKeyboardMarkup(keyboard))
        return 
        
    # Step 0: Trigger login
    if text == "🔐 Login":
        await update.message.reply_text("👤 Enter your username:")
        user_states[user.id] = 'awaiting_username'
        return

    # Step 1: Handle username
    if user.id in user_states and user_states[user.id] == 'awaiting_username':
        allowed_usernames = load_allowed_usernames()
        if text in allowed_usernames:
            context.user_data['username'] = text
            user_states[user.id] = 'awaiting_sid_token'
            await update.message.reply_text("✅ Username approved.\n\nPlease send your Key 🔑:")
        else:
            await update.message.reply_text("❌ You are not authorized to login.")
        return

    # Step 2: Handle SID/Auth Token
    if user.id in user_states and user_states[user.id] == 'awaiting_sid_token' and len(text.splitlines()) == 2:
        lines = text.splitlines()
        sid, auth_token = lines[0], lines[1]
        user_credentials[user.id] = {'sid': sid, 'auth_token': auth_token}
        try:
            client = Client(sid, auth_token)
            account = client.api.accounts(sid).fetch()
            if account.status in ['suspended', 'closed']:
                await update.message.reply_text("Your Key is Invalid ❌")
                await show_logout_button(update)
            else:
                await update.message.reply_text("You are successfully logged in ✅")
                keyboard = [
                    ["📱 Buy Numbers", "🛒 Buy SID"],
                    ["📞 Contact Us", "🔓 Logout"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Choose an option below:", reply_markup=reply_markup)
        except:
            await update.message.reply_text("Your Key is Invalid ❌")
        return

    # Step 3: Handle Area Code input
    if user.id in user_states and user_states[user.id] == 'awaiting_area_code':
        area_code = text
        await show_numbers_by_area_code(update, context, area_code)
        user_states.pop(user.id, None)
        return

    # Step 4: Manual number input
    if text.startswith('+'):
        number = text
        keyboard = [[InlineKeyboardButton("Buy", callback_data=f"manual_buy:{number}")]]
        await update.message.reply_text(f"{number}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    # Menu actions from KeyboardButton
    if text == "📱 Buy Numbers":
        user_states[user.id] = 'awaiting_area_code'
        await update.message.reply_text("📍Enter Area Code:")
        return
    elif text == "🛒 Buy SID":
        await buy_sid(update, context)
        return
    elif text == "📞 Contact Us":
        await contact_us(update, context)
        return
    elif text == "🔓 Logout":
        await logout_from_text(update, context)
        return
    else:
        await update.message.reply_text("Please send your Key 🔑.")

# Logout button for suspended keys
async def show_logout_button(update: Update):
    keyboard = [[InlineKeyboardButton("🔓 Logout", callback_data="logout")]]
    await update.message.reply_text("Your key is suspended. You need to logout.", reply_markup=InlineKeyboardMarkup(keyboard))

# Logout from callback button
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_credentials.pop(user.id, None)
    user_states.pop(user.id, None)
    user_numbers.pop(user.id, None)
    user_twilio_auth.pop(user.id, None)
    await update.callback_query.message.reply_text("You have been logged out. Please log in again to continue.")
    keyboard = [[KeyboardButton("🔐 Login")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.callback_query.message.reply_text("Welcome back! Please login below:", reply_markup=reply_markup)

# Buy number menu
async def buy_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in user_credentials:
        await update.callback_query.message.reply_text("Please login first ✅.")
        return
    user_states[user.id] = 'awaiting_area_code'
    await update.callback_query.message.reply_text("📍Enter Area Code:")

# Show available numbers
async def show_numbers_by_area_code(update: Update, context: ContextTypes.DEFAULT_TYPE, area_code: str):
    user = update.effective_user
    creds = user_credentials[user.id]
    client = Client(creds['sid'], creds['auth_token'])
    try:
        numbers = client.available_phone_numbers('CA').local.list(area_code=area_code, limit=60)
        if not numbers:
            await update.message.reply_text("❌ No numbers found for this area code ❌.")
            return

        number_list = "\n".join([num.phone_number for num in numbers])
        await update.message.reply_text(f"*Available Numbers:*\n\n{number_list}\n\nChoose a phone number below ⬇️", parse_mode='Markdown')
        keyboard = []

        for i in range(0, len(numbers), 2):
            row = []
            for j in range(2):
                if i + j < len(numbers):
                    phone = numbers[i + j].phone_number
                    row.append(InlineKeyboardButton(phone, callback_data=f"buy:{phone}"))
            keyboard.append(row)

        await update.message.reply_text("Choose a number below:", reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text("❌ Failed to fetch numbers ❌")

# Buy number
async def buy_number(update: Update, context: ContextTypes.DEFAULT_TYPE, number: str):
    user = update.effective_user
    creds = user_credentials[user.id]
    client = Client(creds['sid'], creds['auth_token'])

    try:
        # ✅ Check if user already has a number purchased
        if user.id in user_numbers and user_numbers[user.id]:
            await update.callback_query.message.reply_text("🚫 You have already purchased a number 🚫. Please delete it first ✅.")
            return

        # ✅ Attempt to buy number
        incoming = client.incoming_phone_numbers.create(phone_number=number)
        user_numbers.setdefault(user.id, []).append(incoming.sid)

        # ✅ Delete old message if exists
        if update.callback_query.message:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=update.callback_query.message.message_id
                )
            except:
                pass

        # ✅ Show success message with Inbox & Delete buttons
        message = await update.callback_query.message.reply_text(
            f"Successfully Purchased ✅\n{number}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Show Inbox 📥", callback_data=f"inbox:{incoming.sid}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{incoming.sid}")
                ]
            ])
        )
        last_message_ids[user.id] = message.message_id

    except Exception as e:
        # ✅ Default fallback: suspended key or other error
        await update.callback_query.message.reply_text("🚫 Your key is suspended 🚫")
        await show_logout_button(update)

# Show OTP and auto-delete number
async def show_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE, number_sid: str):
    import re
    user = update.effective_user
    creds = user_credentials[user.id]
    client = Client(creds['sid'], creds['auth_token'])

    try:
        number_obj = client.incoming_phone_numbers(number_sid).fetch()
        messages = client.messages.list(to=number_obj.phone_number, limit=1)

        if not messages:
            await update.callback_query.message.reply_text("❌ Your Inbox Is Empty ❌.")
            return

        msg = messages[0]
        msg_body = msg.body.strip()

        # Extract 6-digit OTP from the message
        otp_match = re.search(r'\b\d{3}[-\s]?\d{3}\b', msg_body)
        otp = otp_match.group().replace('-', '').replace(' ', '') if otp_match else "N/A"

        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # OTP + message summary
        await update.callback_query.message.reply_text(
            f"📬 *New OTP Detected!*\n\n🔐 *OTP:* `{otp}`\n📱 *App:* WhatsApp\n📞 *Number:* {number_obj.phone_number}\n🌍 *Country:* Canada\n🕒 *Time:* {time_str}",
            parse_mode='Markdown'
        )

        # Show full message separately
        await update.callback_query.message.reply_text(
            f"*Full Message:*\n```\n{msg_body}\n```",
            parse_mode='Markdown'
        )

        # Delete number
        client.incoming_phone_numbers(number_sid).delete()
        await update.callback_query.message.reply_text(f"♻️ The number {number_obj.phone_number} has been deleted.")

        if user.id in last_message_ids:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_message_ids[user.id])
            except:
                pass

        if user.id in user_numbers and number_sid in user_numbers[user.id]:
            user_numbers[user.id].remove(number_sid)

    except:
        await update.callback_query.message.reply_text("🚫 Your key is suspended 🚫")
        await show_logout_button(update)

# Delete number manually
async def delete_number(update: Update, context: ContextTypes.DEFAULT_TYPE, number_sid: str):
    user = update.effective_user
    creds = user_credentials[user.id]
    client = Client(creds['sid'], creds['auth_token'])

    try:
        number_obj = client.incoming_phone_numbers(number_sid).fetch()
        client.incoming_phone_numbers(number_sid).delete()

        await update.callback_query.message.reply_text(f"🗑️ Number {number_obj.phone_number} has been deleted.")

        if user.id in user_numbers and number_sid in user_numbers[user.id]:
            user_numbers[user.id].remove(number_sid)

        if user.id in last_message_ids:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_message_ids[user.id])
            except:
                pass

    except:
        await update.callback_query.message.reply_text("🚫 Failed to delete the number. Maybe already deleted or invalid key.")

# Buy SID
async def buy_sid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wanna buy a Key ❓❓ Go here ⬇️: https://t.me/twiliokeyp2p_bot")

# Contact us
async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Contact Work Together Group's Mentors 🔔:\n@nisho_yeager\n@fahim322\n@don_dada09")

# Button handler
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == 'login':
        await update.callback_query.message.reply_text("👤 Enter your username:")
        user_states[update.effective_user.id] = 'awaiting_username'
    elif data == 'buy_sid':
        await buy_sid(update, context)
    elif data == 'contact_us':
        await contact_us(update, context)
    elif data == 'buy_numbers':
        await buy_numbers(update, context)
    elif data == 'logout':
        await logout(update, context)
    elif data.startswith('buy:'):
        await buy_number(update, context, data.split(":")[1])
    elif data.startswith('manual_buy:'):
        await buy_number(update, context, data.split(":")[1])
    elif data.startswith('inbox:'):
        await show_inbox(update, context, data.split(":")[1])
    elif data.startswith('delete:'):
        await delete_number(update, context, data.split(":")[1])

# /buy <area_code> command
async def show_numbers_by_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in user_credentials:
        await update.message.reply_text("Please login first ✅.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Please provide an area code. Example: /buy 416", parse_mode='Markdown')
        return

    area_code = context.args[0]
    await show_numbers_by_area_code(update, context, area_code)

# Run the bot
if __name__ == '__main__':
    print("Bot is running...")
    app = ApplicationBuilder().token("7162054580:AAGnk9ptPBkCrWP4KjgPlISs-6M8srq1OzI").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", show_numbers_by_command))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_credentials))
    app.run_polling()
