# config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8475347826:AAHI7ufHnqWAlfpbCxykn2FvdDp6HA84Zws")
DEFAULT_ADMINS = [7477843431, 7651599279]
CONTACT_BOT = "@GKYFILEHOSTAdminbot"
DATA_FILE = "bot/data.json"   # path relative to project root

# Default tag for users without a custom tag
DEFAULT_TAG = "MGK"

# Maximum concurrent downloads per user
MAX_CONCURRENT_DOWNLOADS = 2

# Base download directory (will be overridden per service/user)
DEFAULT_DOWNLOAD_DIR = "downloads"