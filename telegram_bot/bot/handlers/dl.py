# bot/handlers/dl.py

import re
import subprocess
import threading
import time
import os
import shutil
import yaml
import html  # <-- Eta add kora hoyeche NameError fix korar jonno
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from telegram.constants import ParseMode

from config import DEFAULT_DOWNLOAD_DIR, MAX_CONCURRENT_DOWNLOADS
from bot.database import get_user_tag
from bot.utils import premium_or_admin


# -------------------------------------------------------------------
# In-memory storage
# -------------------------------------------------------------------
active_tasks: Dict[str, List[Dict]] = {}
user_sessions: Dict[str, Dict] = {}
config_lock = threading.Lock()  # Prevents multiple downloads from corrupting the YAML


# -------------------------------------------------------------------
# Path utilities
# -------------------------------------------------------------------
def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def get_vinetrimmer_dir() -> Path:
    return get_project_root() / "vinetrimmer"


def get_python_executable() -> Optional[str]:
    """
    Return the Python executable that should be used to run vinetrimmer.py.
    Prefers the virtual environment Python if present, falls back to system Python.
    """
    vinetrimmer_dir = get_vinetrimmer_dir()
    venv_dir = vinetrimmer_dir / ".venv"

    # Check for venv Python (Windows)
    for candidate in [
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)

    # Fall back: poetry run python, then plain python
    poetry = shutil.which("poetry")
    if poetry:
        return None  # Signal to use poetry run python

    return shutil.which("python") or "python"


def get_vinetrimmer_entry() -> Path:
    """Return the path to vinetrimmer.py (the main CLI entry point)."""
    return get_vinetrimmer_dir() / "vinetrimmer.py"


def build_command(args: List[str]) -> List[str]:
    """
    Build the full command list to invoke vinetrimmer.py with the given args.

    Produces one of:
      python vinetrimmer.py dl ...          (venv or system Python)
      poetry run python vinetrimmer.py dl ... (fallback via poetry)
    """
    vinetrimmer_py = get_vinetrimmer_entry()
    python_exe = get_python_executable()

    if python_exe is None:
        # Use poetry run python
        poetry = shutil.which("poetry") or "poetry"
        return [poetry, "run", "python", str(vinetrimmer_py)] + args
    else:
        return [python_exe, str(vinetrimmer_py)] + args


def run_vt_command(args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """
    Run vinetrimmer.py with the given args.
    Returns the CompletedProcess object.
    """
    cmd = build_command(args)
    vinetrimmer_dir = get_vinetrimmer_dir()

    env = dict(os.environ)
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONPATH"] = str(get_project_root())

    return subprocess.run(
        cmd,
        cwd=str(vinetrimmer_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
        shell=(os.name == 'nt' and cmd[0] == 'poetry') # Resolve poetry if used
    )


# -------------------------------------------------------------------
# Helper: Parse user command
# -------------------------------------------------------------------
def parse_service_and_id(text: str) -> Tuple[Optional[str], Optional[str]]:
    text = re.sub(r"^/dl\s*", "", text).strip()
    if not text:
        return None, None

    explicit_match = re.match(r"^-([a-zA-Z0-9]+)\s+(.+)$", text)
    if explicit_match:
        alias = explicit_match.group(1).lower()
        rest = explicit_match.group(2).strip()
        id_match = re.search(r"(?:title/|watch/|jbv=)?(\d+)", rest)
        if id_match:
            return alias, id_match.group(1)
        if rest.isdigit():
            return alias, rest
        return alias, None

    nf_match = re.search(r"netflix\.com/.*?(?:title/|watch/|jbv=)(\d+)", text)
    if nf_match:
        return "nf", nf_match.group(1)

    return None, None


# -------------------------------------------------------------------
# Fetch tracks using vinetrimmer.py dl --list
# -------------------------------------------------------------------
def fetch_title_and_tracks_via_cli(
    service_alias: str, content_id: str
) -> Tuple[Optional[str], List[Dict], List[Dict], str]:
    try:
        # vinetrimmer.py strips the leading "dl" from sys.argv itself,
        # so we pass: dl --list <service> <id>
        result = run_vt_command(["dl", "--list", service_alias, content_id])
    except Exception as e:
        print(f"ERROR: vinetrimmer.py command failed: {e}")
        return None, [], [], f"System Execution Error: {str(e)}"

    stdout_text = result.stdout if result.stdout else ""
    stderr_text = result.stderr if result.stderr else ""
    output = stdout_text + stderr_text

    # ANSI codes strip kora (color output er jonno regex jate fail na kore)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', output)

    if result.returncode != 0 or "VID |" not in clean_output:
        print("=== VT OUTPUT ERROR ===")
        print(clean_output)
        print("=== END ===")
        return None, [], [], clean_output.strip()

    title_match = re.search(r"Title:\s*(.+?)(?:\s*\(\d{4}\))?", clean_output)
    title_name = title_match.group(1).strip() if title_match else "Unknown Title"

    videos = []
    audios = []
    for line in clean_output.splitlines():
        line = line.strip()
        if "|" not in line:
            continue

        if "VID |" in line and "kb/s" in line:
            parts = [p.strip() for p in line.split("|")]

            codec_raw = parts[1] if len(parts) > 1 else "Unknown"
            codec = (
                "H264"
                if "h264" in codec_raw.lower()
                else ("H265" if "h265" in codec_raw.lower() else codec_raw.split("-")[0].upper())
            )

            height = "0"
            bitrate = 0
            for p in parts:
                res_match = re.search(r"(\d+)x(\d+)", p)
                if res_match:
                    height = res_match.group(2)
                if "kb/s" in p:
                    b_str = re.sub(r"[^\d]", "", p)
                    if b_str:
                        bitrate = int(b_str)

            videos.append(
                {
                    "id": f"vid_{len(videos)}",
                    "height": height,
                    "bitrate": bitrate,
                    "codec": codec,
                    "raw": line,
                }
            )

        elif "AUD |" in line and "kb/s" in line:
            parts = [p.strip() for p in line.split("|")]

            lang_code = "und"
            lang_display = "Unknown"
            bitrate = 0

            codec_raw = parts[1] if len(parts) > 1 else "Unknown"
            codec = "Dolby" if "ddplus" in codec_raw.lower() else "AAC"

            for i, p in enumerate(parts):
                if "kb/s" in p:
                    b_str = re.sub(r"[^\d]", "", p)
                    if b_str:
                        bitrate = int(b_str)
                if re.match(r"^[a-z]{2,3}(-[A-Z]{2})?$", p):
                    lang_code = p
                    if i + 1 < len(parts):
                        lang_display = parts[i + 1].split(" [")[0]

            audios.append(
                {
                    "id": f"aud_{len(audios)}",
                    "language_code": lang_code,
                    "language_display": lang_display,
                    "bitrate": bitrate,
                    "codec": codec,
                    "raw": line,
                }
            )

    return title_name, videos, audios, ""


# -------------------------------------------------------------------
# Download thread
# -------------------------------------------------------------------
def run_download_thread(
    task_id: str,
    user_id: str,
    service_alias: str,
    content_id: str,
    title_name: str,
    selected_video: Dict,
    selected_audios: List[Dict],
    download_dir: Path,
):
    user_tag = get_user_tag(str(user_id))

    # 1. Update task info for /tasks tracking
    filename_formatted = (
        f"{title_name.replace(' ', '.')}.{selected_video['height']}p"
        f".{service_alias.upper()}.WEB-DL.{selected_video['codec']}-{user_tag}"
    )
    for task in active_tasks.get(user_id, []):
        if task["id"] == task_id:
            task["status"] = "downloading"
            task["filename"] = filename_formatted
            break

    vinetrimmer_dir = get_vinetrimmer_dir()
    yaml_path = vinetrimmer_dir / "vinetrimmer.yml"

    # 2. Edit vinetrimmer.yml dynamically for this user
    with config_lock:
        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                vt_config = yaml.safe_load(f) or {}

            vt_config["tag"] = user_tag
            if "directories" not in vt_config:
                vt_config["directories"] = {}
            vt_config["directories"]["downloads"] = str(download_dir)

            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(vt_config, f)
        time.sleep(0.5)

    # 3. Build command args for vinetrimmer.py
    #    vinetrimmer.py main() pops "dl" from sys.argv itself, so we pass it here.
    vt_args = [
        "dl",
        "-q", str(selected_video["height"]),
        "-vb", str(selected_video["bitrate"]),
    ]
    if selected_audios:
        ab_vals = [str(a["bitrate"]) for a in selected_audios]
        vt_args.extend(["-ab", ",".join(ab_vals)])
        langs = list(set(a["language_code"] for a in selected_audios))
        vt_args.extend(["-al", ",".join(langs)])
    vt_args.extend([service_alias, content_id])

    cmd = build_command(vt_args)

    env = {
        **os.environ,
        "VT_TAG": user_tag,
        "VT_DOWNLOAD_DIR": str(download_dir),
        "PYTHONSAFEPATH": "1",
        "PYTHONPATH": str(get_project_root()),
    }

    # 4. Execute
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(vinetrimmer_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        for task in active_tasks.get(user_id, []):
            if task["id"] == task_id:
                task["process"] = process
                break
        for line in process.stdout:
            line = line.strip()
            # Clean output for bot display
            clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
            if clean_line:
                for task in active_tasks.get(user_id, []):
                    if task["id"] == task_id:
                        task["progress"] = clean_line[:80]
                        break
        process.wait()
        for task in active_tasks.get(user_id, []):
            if task["id"] == task_id:
                task["status"] = "completed" if process.returncode == 0 else "failed"
                break
    except Exception as e:
        for task in active_tasks.get(user_id, []):
            if task["id"] == task_id:
                task["status"] = f"error: {str(e)}"
                break


# -------------------------------------------------------------------
# Start download
# -------------------------------------------------------------------
async def start_download(
    user_id: str,
    service_alias: str,
    content_id: str,
    title_name: str,
    selected_video: Dict,
    selected_audios: List[Dict],
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    task_id = f"{user_id}_{int(time.time())}"

    folder_name = "netflix" if service_alias.lower() == "nf" else service_alias.lower()
    download_dir = get_project_root() / DEFAULT_DOWNLOAD_DIR / folder_name / user_id
    download_dir.mkdir(parents=True, exist_ok=True)

    user_name = update.effective_user.full_name or update.effective_user.username or "User"
    platform_name = "Netflix" if service_alias.lower() == "nf" else service_alias.upper()

    task_info = {
        "id": task_id,
        "user_id": user_id,
        "user_name": user_name,
        "service": platform_name,
        "title": title_name,
        "status": "starting",
        "progress": "Preparing Download...",
        "start_time": time.time(),
        "download_dir": str(download_dir),
        "process": None,
        "filename": "Processing...",
    }

    if user_id not in active_tasks:
        active_tasks[user_id] = []
    active_tasks[user_id].append(task_info)

    msg = (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"⌬ User: {user_name}\n"
        f"Platform: {platform_name}\n"
        f"   ┏━━━━━━━━━━━━━━━━┛\n"
        f"   ┠ Download Initiated\n"
        f"   ┠ Resolution: {selected_video['height']}p\n"
        f"   ┗ Audio Tracks: {len(selected_audios)}\n\n"
        f"⌬ Bot Stats\n"
        f"┖ Monitor Progress with /tasks"
    )
    await update.effective_message.reply_text(msg)

    thread = threading.Thread(
        target=run_download_thread,
        args=(
            task_id,
            user_id,
            service_alias,
            content_id,
            title_name,
            selected_video,
            selected_audios,
            download_dir,
        ),
        daemon=True,
    )
    thread.start()


# -------------------------------------------------------------------
# Main /dl command handler
# -------------------------------------------------------------------
@premium_or_admin
async def dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    service_alias, content_id = parse_service_and_id(text)
    if not service_alias or not content_id:
        await update.message.reply_text(
            "❌ Invalid format.\n"
            "Usage: <code>/dl -nf https://www.netflix.com/title/82070758</code>\n"
            "or <code>/dl https://www.netflix.com/title/82070758</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(active_tasks.get(user_id, [])) >= MAX_CONCURRENT_DOWNLOADS:
        await update.message.reply_text("⚠️ Maximum concurrent downloads reached.")
        return

    msg = await update.message.reply_text("🔍 Fetching title information...")

    title_name, videos, audios, err_msg = fetch_title_and_tracks_via_cli(service_alias, content_id)
    
    if not videos:
        # Ebar properly escape hobe ar crash korbe na
        error_display = f"❌ <b>Failed to retrieve track information.</b>\n\n<b>Terminal Error Log:</b>\n<pre>{html.escape(err_msg[-1500:])}</pre>"
        await msg.edit_text(error_display, parse_mode=ParseMode.HTML)
        return

    user_sessions[user_id] = {
        "service_alias": service_alias,
        "content_id": content_id,
        "title_name": title_name,
        "videos": videos,
        "audios": audios,
        "selected_video": None,
        "selected_audios": [],
        "stage": "video_selection",
        "msg_id": msg.message_id,
        "chat_id": update.effective_chat.id,
    }

    user_name = update.effective_user.full_name or update.effective_user.username or "User"
    platform_name = "Netflix" if service_alias.lower() == "nf" else service_alias.upper()

    text_content = (
        f"👤 <b>User:</b> {user_name}\n"
        f"<b>Platform:</b> {platform_name}\n"
        f"<b>Title:</b> {title_name}\n"
        f"<b>Upload Method:</b> Drive (Forced)\n\n"
        f"Please select video resolution:"
    )

    buttons = []
    for idx, v in enumerate(videos[:30]):
        label = f"{v['height']}p ({v['bitrate']}K)"
        buttons.append(InlineKeyboardButton(label, callback_data=f"video:{idx}"))

    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close_dl")])

    try:
        await msg.edit_text(
            text_content,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        print(f"Error editing message: {e}")


# -------------------------------------------------------------------
# Callback query handler
# -------------------------------------------------------------------
async def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data

    if data == "close_dl":
        if user_id in user_sessions:
            del user_sessions[user_id]
        await query.message.delete()
        return

    session = user_sessions.get(user_id)
    if not session:
        await query.edit_message_text("⏳ Session expired. Please start again with /dl.")
        return

    user_name = query.from_user.full_name or query.from_user.username or "User"
    platform_name = (
        "Netflix" if session["service_alias"].lower() == "nf" else session["service_alias"].upper()
    )

    if data.startswith("video:"):
        idx = int(data.split(":")[1])
        session["selected_video"] = session["videos"][idx]
        session["stage"] = "audio_selection"
        await render_audio_ui(query, session, user_name, platform_name)

    elif data.startswith("toggle_audio:"):
        audio_id = data.split(":")[1]
        audio_track = next((a for a in session["audios"] if a["id"] == audio_id), None)
        if not audio_track:
            return

        selected = session.get("selected_audios", [])
        existing = next((a for a in selected if a["id"] == audio_id), None)
        if existing:
            selected.remove(existing)
        else:
            selected.append(audio_track)
        session["selected_audios"] = selected
        await render_audio_ui(query, session, user_name, platform_name)

    elif data == "back_to_video":
        session["stage"] = "video_selection"
        session["selected_audios"] = []
        videos = session["videos"]

        buttons = []
        for idx, v in enumerate(videos[:30]):
            label = f"{v['height']}p ({v['bitrate']}K)"
            buttons.append(InlineKeyboardButton(label, callback_data=f"video:{idx}"))

        keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close_dl")])

        text_content = (
            f"👤 <b>User:</b> {user_name}\n"
            f"<b>Platform:</b> {platform_name}\n"
            f"<b>Title:</b> {session['title_name']}\n"
            f"<b>Upload Method:</b> Drive (Forced)\n\n"
            f"Please select video resolution:"
        )
        try:
            await query.edit_message_text(
                text_content,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            print(f"Error editing message: {e}")

    elif data == "done_audio":
        if not session.get("selected_video"):
            await query.answer("Please select a video first.", show_alert=True)
            return
        if not session.get("selected_audios"):
            await query.answer("Select at least one audio track.", show_alert=True)
            return

        del user_sessions[user_id]
        await query.edit_message_text("⏳ Starting download...")

        await start_download(
            user_id=user_id,
            service_alias=session["service_alias"],
            content_id=session["content_id"],
            title_name=session["title_name"],
            selected_video=session["selected_video"],
            selected_audios=session["selected_audios"],
            update=update,
            context=context,
        )


async def render_audio_ui(query, session, user_name, platform_name):
    selected_vid = session["selected_video"]
    selected = session.get("selected_audios", [])
    audios = session["audios"]

    text = (
        f"👤 <b>User:</b> {user_name}\n"
        f"<b>Platform:</b> {platform_name}\n"
        f"<b>Title:</b> {session['title_name']}\n"
        f"<b>Upload Method:</b> Drive (Forced)\n\n"
        f"<b>Selected Video:</b>\n"
        f"• {selected_vid['height']}p ({selected_vid['bitrate']}K) - {selected_vid['codec']}\n\n"
        f"🎧 <b>Select One Or More Audio Tracks:</b>\n"
    )

    if selected:
        text += "\n<b>Selected Tracks:</b>\n"
        for i, a in enumerate(selected, 1):
            text += f"{i}. {a['language_display']} ({a['bitrate']}K) - {a['codec']}\n"

    buttons = []
    for a in audios:
        lang_display = f"{a['language_display']} ({a['bitrate']}K)"
        if any(s["id"] == a["id"] for s in selected):
            lang_display = "✅ " + lang_display
        buttons.append(InlineKeyboardButton(lang_display, callback_data=f"toggle_audio:{a['id']}"))

    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    keyboard.append(
        [
            InlineKeyboardButton("✅ Done", callback_data="done_audio"),
            InlineKeyboardButton("🔙 Back", callback_data="back_to_video"),
        ]
    )

    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Error editing message: {e}")