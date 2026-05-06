# bot/handlers/help.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils import premium_or_admin

@premium_or_admin
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Welcome\n"
        "/dl - Download (under construction)\n"
        "/tasks - View tasks (under construction)\n"
        "/profile - Your profile\n"
        "/setting - Settings (under construction)\n"
        "/help - This help\n"
        "/admin - Admin panel (admin only)"
    )