import logging
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)
WIB = timezone(timedelta(hours=7), "WIB")

for _logger in [
    "pyrogram", "pyrogram.client", "pyrogram.session",
    "pyrogram.dispatcher", "pyrogram.connection",
    "pyrogram.crypto", "pyrogram.storage",
    "httpx", "telegram", "telegram.ext",
    "apscheduler",
]:
    logging.getLogger(_logger).setLevel(logging.CRITICAL)
    logging.getLogger(_logger).propagate = False

logging.basicConfig(level=logging.CRITICAL)


API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
FISH_BOT_USERNAME = os.getenv("FISH_BOT_USERNAME", "")
PRIVATE_FISH_BOT_USERNAMES = os.getenv(
    "PRIVATE_FISH_BOT_USERNAMES",
    "@fish_it_vip_bot,@fish_it_vip4_bot,@fish_it_vip5_bot",
).strip()
REQUIRED_CHANNEL_USERNAME = os.getenv("REQUIRED_CHANNEL_USERNAME", "@srpaid").strip()
FISH_MODE = os.getenv("FISH_MODE", "private").strip().lower()
FISH_GROUP_CHAT = os.getenv("FISH_GROUP_CHAT", "").strip()
PYRO_DEVICE_MODEL = os.getenv("PYRO_DEVICE_MODEL", "FishIt Client")
PYRO_SYSTEM_VERSION = os.getenv("PYRO_SYSTEM_VERSION", "Linux")
PYRO_APP_VERSION = os.getenv("PYRO_APP_VERSION", "FishIt Bot 1.0")
MONGO_URL = os.getenv("MONGO_URL", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "fishit").strip()
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "fishtele").strip()
ACTION_DELAY = float(os.getenv("ACTION_DELAY", "1.5"))
ACTION_DELAY_MIN = float(os.getenv("ACTION_DELAY_MIN", "3"))
ACTION_DELAY_MAX = float(os.getenv("ACTION_DELAY_MAX", "7"))
HUMAN_CLICK_DELAY_MIN = float(os.getenv("HUMAN_CLICK_DELAY_MIN", "1"))
HUMAN_CLICK_DELAY_MAX = float(os.getenv("HUMAN_CLICK_DELAY_MAX", "3"))
POST_EVENT_DELAY = float(os.getenv("POST_EVENT_DELAY", "0.8"))
PRIVATE_DONE_DELAY_MIN = float(os.getenv("PRIVATE_DONE_DELAY_MIN", "3"))
PRIVATE_DONE_DELAY_MAX = float(os.getenv("PRIVATE_DONE_DELAY_MAX", "6"))
PRIVATE_EMPTY_DONE_GRACE = int(os.getenv("PRIVATE_EMPTY_DONE_GRACE", "6"))
PRIVATE_EVENT_TIMEOUT = int(os.getenv("PRIVATE_EVENT_TIMEOUT", "420"))
PRIVATE_WAIT_STALE_SECONDS = int(os.getenv("PRIVATE_WAIT_STALE_SECONDS", "180"))
CAPTCHA_CLICK_DELAY_MIN = float(os.getenv("CAPTCHA_CLICK_DELAY_MIN", "0"))
CAPTCHA_CLICK_DELAY_MAX = float(os.getenv("CAPTCHA_CLICK_DELAY_MAX", "0"))
CAPTCHA_RESUME_DELAY = float(os.getenv("CAPTCHA_RESUME_DELAY", "0"))
CAPTCHA_VERIFY_POLL_INTERVAL = float(os.getenv("CAPTCHA_VERIFY_POLL_INTERVAL", "0.25"))
SELL_RETRY_COUNT = int(os.getenv("SELL_RETRY_COUNT", "3"))
ALL_MODE_GROUP_WAIT = int(os.getenv("ALL_MODE_GROUP_WAIT", "120"))
SPECIAL_OPEN_DELAY_MIN = float(os.getenv("SPECIAL_OPEN_DELAY_MIN", "31"))
SPECIAL_OPEN_DELAY_MAX = float(os.getenv("SPECIAL_OPEN_DELAY_MAX", "35"))
SPECIAL_BOOST_INITIAL_DELAY_MIN = float(os.getenv("SPECIAL_BOOST_INITIAL_DELAY_MIN", "3"))
SPECIAL_BOOST_INITIAL_DELAY_MAX = float(os.getenv("SPECIAL_BOOST_INITIAL_DELAY_MAX", "5"))
SPECIAL_BOOST_USER_DELAY_MIN = float(os.getenv("SPECIAL_BOOST_USER_DELAY_MIN", "3"))
SPECIAL_BOOST_USER_DELAY_MAX = float(os.getenv("SPECIAL_BOOST_USER_DELAY_MAX", "6"))
SPECIAL_GROUP_WRITE_BLOCK_RETRY_DELAYS = (30 * 60, 24 * 60 * 60, 3 * 24 * 60 * 60)
BOT_LOG_CHAT = os.getenv("BOT_LOG_CHAT", "").strip()
CAPTCHA_LOG_CHAT = os.getenv("CAPTCHA_LOG_CHAT", "").strip()
LOG_BACKUP = os.getenv("LOG_BACKUP", "").strip()
LOG_CHAT_MIN_INTERVAL = float(os.getenv("LOG_CHAT_MIN_INTERVAL", "1.5"))
SELL_FLOW_GROUP_LOG = os.getenv("SELL_FLOW_GROUP_LOG", "0").lower() in {"1", "true", "yes", "on"}
AUTO_START_FISHING = os.getenv("AUTO_START_FISHING", "1").lower() not in {"0", "false", "no", "off"}
WATCHDOG_TIMEOUT = int(os.getenv("WATCHDOG_TIMEOUT", "600"))
MAX_FAVORITE_SLOTS = int(os.getenv("MAX_FAVORITE_SLOTS", "100"))
ACCOUNTS_PAGE_SIZE = 10
RULES_FILE = BASE_DIR / "fish_rules.json"
STATS_FILE = BASE_DIR / "fish_stats.json"
ADMINS_FILE = BASE_DIR / "bot_admins.json"
MODE_FILE = BASE_DIR / "bot_mode.json"
MAINTENANCE_FILE = BASE_DIR / "bot_maintenance.json"
GROUPS_FILE = BASE_DIR / "fish_groups.json"
SPECIAL_GROUP_FILE = BASE_DIR / "fish_special_group.json"
ACCOUNT_STATE_FILE = BASE_DIR / "fish_account_state.json"
BROADCAST_USERS_FILE = BASE_DIR / "broadcast_users.json"
BROADCAST_MESSAGES_FILE = BASE_DIR / "broadcast_messages.json"
DAILY_BROADCAST_FILE = BASE_DIR / "daily_broadcast.json"
ENV_FILE = BASE_DIR / ".env"
RESTART_FLAG_FILE = BASE_DIR / ".bot2_restart_pending"
BACKUP_DIR = BASE_DIR / "backups"
RARE_GALLERY_FILE = BASE_DIR / "rare_gallery.json"
BACKUP_SCHEMA_VERSION = 1
FULL_BACKUP_SCHEMA = "fishit_full_backup"
BACKUP_MANIFEST_NAME = "manifest.json"
BACKUP_FILES_DIR = "files"
BACKUP_SESSIONS_DIR = "sessions"
RARE_GALLERY_LIMIT = int(os.getenv("RARE_GALLERY_LIMIT", "500"))
LOGIN_FLOW_TIMEOUT = int(os.getenv("LOGIN_FLOW_TIMEOUT", "300"))
PENDING_INPUT_TIMEOUT = int(os.getenv("PENDING_INPUT_TIMEOUT", "600"))

VALID_FISH_MODES = {"private", "group_room", "all", "special_group"}

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))


def validate_required_config():
    if not API_ID or API_ID == 0:
        raise RuntimeError("API_ID belum diisi di .env")
    if not API_HASH:
        raise RuntimeError("API_HASH belum diisi di .env")
    if not FISH_BOT_USERNAME:
        raise RuntimeError("FISH_BOT_USERNAME belum diisi di .env")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN belum diisi di .env")
    if not OWNER_ID:
        raise RuntimeError("OWNER_ID belum diisi di .env")


validate_required_config()
