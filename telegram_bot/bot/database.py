# bot/database.py
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from config import DATA_FILE, DEFAULT_ADMINS, DEFAULT_TAG


class Database:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self, filepath: str = DATA_FILE):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.filepath = filepath
        self.data = self._load()
        self._ensure_default_admins()
        self._initialized = True

    def _load(self) -> Dict:
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            return {"users": {}}
        with open(self.filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _ensure_default_admins(self):
        for uid in DEFAULT_ADMINS:
            uid_str = str(uid)
            if uid_str not in self.data["users"]:
                self.data["users"][uid_str] = {
                    "type": "admin",
                    "expiry": None,
                    "name": "Admin",
                    "username": "",
                    "tag": DEFAULT_TAG,          # give admins the default tag
                }
                self._write_user_json(uid_str)
        self._save()

    def get_user(self, user_id: Union[int, str]) -> Optional[Dict]:
        return self.data["users"].get(str(user_id))

    def add_user(self, user_id: int, user_type: str, expiry_days: Optional[int] = None,
                 name: str = "", username: str = "", tag: str = ""):
        uid = str(user_id)
        expiry = None
        if expiry_days:
            expiry = (datetime.now() + timedelta(days=expiry_days)).isoformat()
        self.data["users"][uid] = {
            "type": user_type,
            "expiry": expiry,
            "name": name,
            "username": username,
            "tag": tag,
        }
        self._save()
        self._write_user_json(uid)

    def remove_user(self, user_id: int) -> bool:
        uid = str(user_id)
        if uid in self.data["users"]:
            user_data = self.data["users"][uid]
            del self.data["users"][uid]
            self._save()
            type_folder = user_data.get("type", "unknown")
            filepath = os.path.join(os.path.dirname(self.filepath), type_folder, f"{uid}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        return False

    def update_user(self, user_id: int, **kwargs):
        uid = str(user_id)
        if uid in self.data["users"]:
            self.data["users"][uid].update(kwargs)
            self._save()
            self._write_user_json(uid)
            return True
        return False

    def is_admin(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return user is not None and user["type"] == "admin"

    def is_premium(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False
        if user["type"] == "premium":
            if user["expiry"]:
                exp = datetime.fromisoformat(user["expiry"])
                if exp > datetime.now():
                    return True
                else:
                    self.remove_user(user_id)
            else:
                return True
        return False

    def is_permanent(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return user is not None and user["type"] == "permanent"

    def get_all_users_by_type(self) -> Dict[str, List[str]]:
        result = {"admin": [], "premium": [], "permanent": []}
        for uid, data in self.data["users"].items():
            if data["type"] in result:
                result[data["type"]].append(uid)
        return result

    def _write_user_json(self, uid: str):
        user = self.data["users"].get(uid)
        if not user:
            return
        type_folder = user["type"]
        folder_path = os.path.join(os.path.dirname(self.filepath), type_folder)
        os.makedirs(folder_path, exist_ok=True)
        filepath = os.path.join(folder_path, f"{uid}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(user, f, indent=2, ensure_ascii=False)


# Singleton instance
db = Database()


# -------------------------------------------------------------------
# Module‑level functions used by the rest of the bot
# -------------------------------------------------------------------
def get_user_tag(user_id: Union[int, str]) -> str:
    """Return the user's tag, or the default tag if none is set."""
    user = db.get_user(str(user_id))
    if user and user.get("tag"):
        return user["tag"]
    return DEFAULT_TAG


def is_premium(user_id: Union[int, str]) -> bool:
    """Check if user is premium (or admin)."""
    # Admins are considered premium
    if is_admin(user_id):
        return True
    return db.is_premium(int(user_id))


def is_admin(user_id: Union[int, str]) -> bool:
    """Check if user is an admin."""
    return db.is_admin(int(user_id))