# bot/handlers/profile.py
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from bot.database import db
from config import CONTACT_BOT

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = db.get_user(user_id)

    if not user_data:
        await update.message.reply_text(
            "🔒 Access Restricted\n\n"
            "This bot is exclusively available for:\n"
            "• Premium Users\n\n"
            "To get access:\n"
            "1. Contact admin for access\n\n"
            f"Contact: {CONTACT_BOT}"
        )
        return

    user_type = user_data["type"]
    name = user_data.get("name") or user.full_name

    if user_type in ["admin", "premium", "permanent"]:
        expiry_str = "Never"
        if user_data.get("expiry"):
            expiry_date = datetime.fromisoformat(user_data["expiry"])
            expiry_str = expiry_date.strftime("%d-%m-%Y")

        tag = user_data.get("tag", "")
        if tag:
            tag_line = f"🏷️ Tag: {tag}\n"
        else:
            tag_line = ""

        message = (
            "✅ Subscription Profile\n\n"
            f"👤 User: {name}\n"
            f"{tag_line}"
            f"🆔 User ID: {user_id}\n"
            f"🤖 Type: {user_type.capitalize()}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Expiry Date: {expiry_str}\n"
            "⏳ Status: Active\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Features:\n"
            "• ✅ Download Content From Many Ott's\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📞 Need Help?\n"
            f"Contact {CONTACT_BOT} for:\n"
            "• 🔄 Renewal\n"
            "• ⬆️ Upgrade\n"
            "• 📝 New Subscription\n"
            "• ❓ Support"
        )
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Access restricted.")