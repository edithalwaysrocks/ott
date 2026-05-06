# bot/utils.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.database import db
from config import CONTACT_BOT

def access_required(allowed_types: list = None):
    """Decorator to check if user has allowed access."""
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user:
                return
            user_id = user.id
            user_data = db.get_user(user_id)

            if allowed_types is None:
                return await func(update, context)

            if not user_data or user_data["type"] not in allowed_types:
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

            return await func(update, context)
        return wrapper
    return decorator

def premium_or_admin(func):
    return access_required(["premium", "admin", "permanent"])(func)

def admin_only(func):
    return access_required(["admin"])(func)