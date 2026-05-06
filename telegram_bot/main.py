# main.py
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN

from bot.handlers.start import start
from bot.handlers.profile import profile
from bot.handlers.admin import admin_panel, admin_conversation_handler
from bot.handlers.dl import dl
from bot.handlers.tasks import tasks
from bot.handlers.setting import setting, setting_conversation_handler
from bot.handlers.help import help_command
from bot.handlers.message_handler import handle_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dl", dl))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("setting", setting))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_panel))

    # Conversation handlers (for multi-step interactions)
    app.add_handler(admin_conversation_handler())
    app.add_handler(setting_conversation_handler())

    # Non-command message handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()