# bot/handlers/start.py
from telegram import Update
from telegram.ext import ContextTypes
from bot.utils import premium_or_admin

@premium_or_admin
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /help to see commands.")