# bot/handlers/admin.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from bot.database import db
from bot.utils import admin_only
import os

ASK_USER_ID, ASK_TYPE, ASK_DURATION, ASK_REMOVE_ID = range(4)

@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")],
        [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("➕ Add User", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Remove User", callback_data="admin_remove")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Admin Panel:", reply_markup=reply_markup)

async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_analytics":
        counts = db.get_all_users_by_type()
        text = (
            "📊 Analytics:\n"
            f"• Admins: {len(counts['admin'])}\n"
            f"• Permanent: {len(counts['permanent'])}\n"
            f"• Premium: {len(counts['premium'])}"
        )
        await query.edit_message_text(text)
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        await query.message.reply_text("Back to menu?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_users":
        file_path = db.filepath
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await context.bot.send_document(chat_id=query.message.chat_id, document=f, filename="data.json")
            await query.edit_message_text("data.json uploaded.")
        else:
            await query.edit_message_text("File not found.")
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        await query.message.reply_text("Back to menu?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_add":
        await query.edit_message_text("Send the user ID to add:")
        return ASK_USER_ID

    elif data == "admin_remove":
        await query.edit_message_text("Send the user ID to remove:")
        return ASK_REMOVE_ID

    elif data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics")],
            [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
            [InlineKeyboardButton("➕ Add User", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Remove User", callback_data="admin_remove")],
        ]
        await query.edit_message_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

    return ConversationHandler.END

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_text = update.message.text.strip()
    try:
        user_id = int(user_id_text)
    except ValueError:
        await update.message.reply_text("Invalid user ID. Operation cancelled.")
        return ConversationHandler.END
    context.user_data["add_user_id"] = user_id

    try:
        chat = await context.bot.get_chat(user_id)
        first = chat.first_name or ""
        last = chat.last_name or ""
        full_name = f"{first} {last}".strip()
        username = chat.username or ""
        context.user_data["add_name"] = full_name
        context.user_data["add_username"] = username
    except Exception:
        context.user_data["add_name"] = str(user_id)
        context.user_data["add_username"] = ""

    keyboard = [
        [InlineKeyboardButton("Admin", callback_data="type_admin")],
        [InlineKeyboardButton("Premium", callback_data="type_premium")],
        [InlineKeyboardButton("Permanent", callback_data="type_permanent")],
    ]
    await update.message.reply_text("Select user type:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_TYPE

async def receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_type = query.data.replace("type_", "")
    context.user_data["add_type"] = user_type

    if user_type == "premium":
        await query.edit_message_text("Enter number of days for premium subscription:")
        return ASK_DURATION
    else:
        user_id = context.user_data["add_user_id"]
        name = context.user_data.get("add_name", "")
        username = context.user_data.get("add_username", "")
        db.add_user(user_id, user_type, name=name, username=username, tag="")   # ← tag empty
        await query.edit_message_text(f"User {user_id} added as {user_type}.")
        return ConversationHandler.END

async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days_text = update.message.text.strip()
    try:
        days = int(days_text)
    except ValueError:
        await update.message.reply_text("Invalid number. Operation cancelled.")
        return ConversationHandler.END
    user_id = context.user_data["add_user_id"]
    name = context.user_data.get("add_name", "")
    username = context.user_data.get("add_username", "")
    db.add_user(user_id, "premium", expiry_days=days, name=name, username=username, tag="")   # ← tag empty
    await update.message.reply_text(f"User {user_id} added as premium for {days} days.")
    return ConversationHandler.END

async def receive_remove_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_text = update.message.text.strip()
    try:
        user_id = int(user_id_text)
    except ValueError:
        await update.message.reply_text("Invalid user ID. Operation cancelled.")
        return ConversationHandler.END
    if db.remove_user(user_id):
        await update.message.reply_text(f"User {user_id} removed.")
    else:
        await update.message.reply_text("User not found.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def admin_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_button_handler, pattern="^admin_")],
        states={
            ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
            ASK_TYPE: [CallbackQueryHandler(receive_type, pattern="^type_")],
            ASK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_duration)],
            ASK_REMOVE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )