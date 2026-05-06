from telegram import Update
from telegram.ext import ContextTypes
from bot.utils import premium_or_admin
from bot.handlers.dl import active_tasks
import time
import psutil


@premium_or_admin
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_tasks = active_tasks.get(user_id, [])

    if not user_tasks:
        await update.message.reply_text("📭 No active downloads.")
        return

    lines = [f"┏━━━━━━━━━━━━━━━━━┓", f"⌬ Active Tasks: {len(user_tasks)}"]
    for task in user_tasks:
        lines.append("")
        lines.append(f"{task['title']}")
        lines.append(f"Platform: {task['service']}")
        lines.append("   ┏━━━━━━━━━━━━━━━━┛")
        status_icon = {"starting": "⏳", "downloading": "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.time()*10)%10],
                       "completed": "✅", "failed": "❌"}.get(task['status'], "❓")
        lines.append(f"   ┃ {status_icon} {task['status']} {task.get('progress', '')}")
        lines.append(f"   ┖ User: {task['user_name']} | ID: {task['user_id']}")

    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        lines.append("")
        lines.append("⌬ Bot Stats")
        lines.append(f"┖ ⌬ CPU: {cpu:.1f}%  ⌬ RAM: {ram:.1f}%  ⌬")
    except:
        pass

    await update.message.reply_text("\n".join(lines))