# bot/handlers/message_handler.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from config import CONTACT_BOT

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    user_id = user.id
    user_data = db.get_user(user_id)

    if not user_data or user_data["type"] not in ["premium", "admin", "permanent"]:
        await update.message.reply_text(
            "🔒 Access Restricted\n\n"
            "This bot is exclusively available for:\n"
            "• Premium Users\n\n"
            "To get access:\n"
            "1. Contact admin for access\n\n"
            f"Contact: {CONTACT_BOT}"
        )
        return

    if user_data["type"] == "premium":
        if not db.is_premium(user_id):
            await update.message.reply_text(
                "⏳ Your premium subscription has expired.\n"
                "Contact admin to renew.\n\n"
                f"Contact: {CONTACT_BOT}"
            )
            return

    # Allowed users: you can respond or ignore.