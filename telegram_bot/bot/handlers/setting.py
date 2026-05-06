# bot/handlers/setting.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from bot.utils import premium_or_admin
from bot.database import db

# State for conversation
WAITING_FOR_TAG = 1

@premium_or_admin
async def setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current tag and option to change it."""
    user = update.effective_user
    user_id = user.id
    user_data = db.get_user(user_id)

    if not user_data:
        await update.message.reply_text("User data not found.")
        return

    current_tag = user_data.get("tag", "")
    if current_tag == "":
        current_tag = "Not set"

    keyboard = [[InlineKeyboardButton("✏️ Change Tag", callback_data="change_tag")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"⚙️ Settings\n\n"
        f"Your current tag: {current_tag}\n\n"
        "Use the button below to change it.",
        reply_markup=reply_markup
    )

async def change_tag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Change Tag' button press."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your new tag (text only):")
    return WAITING_FOR_TAG

async def receive_new_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the new tag and saves it."""
    user = update.effective_user
    user_id = user.id
    new_tag = update.message.text.strip()

    # Update the tag in database
    db.update_user(user_id, tag=new_tag)

    await update.message.reply_text(f"✅ Your tag has been updated to: {new_tag}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tag change cancelled.")
    return ConversationHandler.END

def setting_conversation_handler():
    """Creates conversation handler for changing tag."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(change_tag_callback, pattern="^change_tag$")],
        states={
            WAITING_FOR_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_tag)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )