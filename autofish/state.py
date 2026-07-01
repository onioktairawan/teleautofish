import asyncio
import contextvars
import itertools
import threading
from datetime import datetime

from pyrogram import Client
from telegram.ext import Application


_shutdown_event = asyncio.Event()
_sell_flow_lock = asyncio.Lock()
_stats_file_lock = threading.Lock()
_admin_ids_cache: set[int] = set()
_admin_ids_cache_ts: float = 0.0
_ADMIN_CACHE_TTL = 45.0
_callback_rate: dict[int, float] = {}
_CALLBACK_MIN_INTERVAL = 0.4
_all_accounts_cache: list[dict] = []
_all_accounts_cache_ts: float = 0.0
_ALL_ACCOUNTS_CACHE_TTL = 12.0
_is_running = False
_tg_app: Application = None
_pending_owner_inputs: dict[int, str] = {}
_pending_input_tasks: dict[int, asyncio.Task] = {}
_pending_broadcast: dict[int, dict] = {}
_pending_restore_upload: set[int] = set()
_owner_reply_targets: dict[int, dict] = {}
_selected_account_by_user: dict[int, str] = {}
_login_flows: dict[int, dict] = {}
_login_flow_tasks: dict[int, asyncio.Task] = {}
_last_activity_at: datetime | None = None
_last_action: str = "startup"
_last_fish_event: str = "-"
_last_sell_summary: str = "-"
_last_captcha_response_text: str = ""
_last_notify_message_id: int | None = None
_account_clients: dict[str, Client] = {}
_account_tasks: dict[str, asyncio.Task] = {}
_account_private_boost_tasks: dict[str, asyncio.Task] = {}
_account_running: dict[str, bool] = {}
_account_last_activity: dict[str, datetime] = {}
_account_last_action: dict[str, str] = {}
_account_last_event: dict[str, str] = {}
_account_last_sell: dict[str, str] = {}
_account_last_captcha_response_text: dict[str, str] = {}
_account_captcha_locks: dict[str, asyncio.Lock] = {}
_account_captcha_seen: dict[str, set[tuple[int | str, int]]] = {}
_account_captcha_handlers: dict[str, list[tuple[object, int]]] = {}
_account_user_log_handlers: dict[str, tuple[object, int]] = {}
_account_user_log_identity: dict[str, dict] = {}
_account_group_sessions_done: dict[str, int] = {}
_account_command_mode: dict[str, bool] = {}
_account_group_active: dict[str, bool] = {}
_account_active_group_chat: dict[str, int | str] = {}
_account_pending_group_join: dict[str, dict] = {}
_account_private_session_waiting: dict[str, bool] = {}
_account_private_wait_started: dict[str, float] = {}
_account_private_session_active: dict[str, bool] = {}
_account_waiting_confirmation: dict[str, bool] = {}
_account_mancing_attempts: dict[str, int] = {}
_account_private_boost_until: dict[str, datetime] = {}
_account_private_boost_last: dict[str, str] = {}
_account_sell_locks: dict[str, asyncio.Lock] = {}
_account_lifecycle_locks: dict[str, asyncio.Lock] = {}
_account_inventory_clean_locks: dict[str, asyncio.Lock] = {}
_account_required_channel_joined: set[str] = set()
_account_required_channel_status: dict[str, str] = {}
_account_last_inventory_read_summary: dict[str, dict] = {}
_rare_catch_notify_seen: set[str] = set()
_rare_catch_log_seen: set[str] = set()
_rare_catch_user_cache: dict[str, dict] = {}
_sell_flow_log_messages: dict[str, tuple[int, int]] = {}
_sell_flow_log_states: dict[str, dict] = {}
_special_open_locks: dict[str, asyncio.Lock] = {}
_special_boost_tasks: dict[str, asyncio.Task] = {}
_special_boost_active_events: dict[str, asyncio.Event] = {}
_special_group_write_blocked_until: dict[tuple[str, str], float] = {}
_special_group_write_blocked_reason: dict[tuple[str, str], str] = {}
_special_group_write_blocked_stage: dict[tuple[str, str], int] = {}
_special_join_success: dict[str, set[str]] = {}
_special_join_failed: dict[str, dict[str, str]] = {}
_special_join_reported: set[tuple[str, int]] = set()
_daily_broadcast_fallback_task: asyncio.Task | None = None
_account_notify_message_ids: dict[tuple[str, int], int] = {}
_account_notify_locks: dict[tuple[str, int], asyncio.Lock] = {}
_log_chat_lock = asyncio.Lock()
_last_log_chat_sent_at: float = 0.0
_reply_keyboard_sent: set[int] = set()
_handler_group_seq = itertools.count(1000)
_current_account_label = contextvars.ContextVar("current_account_label", default="main")
_main_premium_active: bool | None = None
_main_premium_checked_at: datetime | None = None
ERROR_LOG_COOLDOWN = 600
_error_log_last_sent: dict[tuple[str, str, str], float] = {}
_account_seen_events: dict[str, dict[tuple, float]] = {}
_account_action_guard: dict[str, dict[tuple, float]] = {}
_account_mode_switch_pending: dict[str, str] = {}
GROUP_LOG_ERROR_EVENT_KINDS = {
    "USERBOT_LOGIN_REQUIRED",
    "USERBOT_START_FAIL",
    "LOOP_ERROR",
    "FAVORITE_ABORT",
    "FAVORITE_FULL",
    "FAVORITE_FAIL",
    "WATCHDOG_WARN",
    "REQUIRED_CHANNEL_FAIL",
}
GROUP_LOG_ERROR_MARKERS = (
    "error",
    "traceback",
    "exception",
    "gagal",
    "fail",
    "failed",
    "warning",
    "warn",
)

__all__ = [
    name
    for name in globals()
    if (name.startswith("_") or name.isupper())
    and not (name.startswith("__") and name.endswith("__"))
]
