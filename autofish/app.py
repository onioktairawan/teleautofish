"""
Fish It Auto Bot v1.5

"""

import asyncio
import contextvars
import html
import itertools
import json
import logging
import os
import random
import re
import signal
import sys
import tempfile
import threading
import time
import traceback
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from pyrogram import Client, enums, filters, idle
from pyrogram.errors import FloodWait, PhoneCodeInvalid, SessionPasswordNeeded
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    ContextTypes,
)

from .config import *
from . import admin as admin_module
from . import accounts as account_module
from . import backup as backup_module
from . import broadcast as broadcast_module
from . import notifications as notification_module
from . import reports as report_module
from . import runtime as runtime_module
from . import settings as settings_module
from .captcha.constants import CAPTCHA_KEYWORDS, QUICK_VERIFY_KEYWORDS
from .db import mongo_client, mongo_col, mongo_enabled
from .fishing import common as fishing_common_module
from .fishing import flow as fishing_flow_module
from .fishing import group_room as fishing_group_room_module
from .fishing import private as fishing_private_module
from .fishing import rare_catch as fishing_rare_catch_module
from .fishing import special_group as fishing_special_group_module
from .fishing import user_media as fishing_user_media_module
from .fishing.common import *
from .fishing.flow import *
from .fishing.group_room import *
from .fishing.private import *
from .fishing.rare_catch import *
from .fishing.special_group import *
from .fishing.user_media import *
from .inventory.constants import (
    ALWAYS_SELL_KEYWORDS,
    KNOWN_RARITY_KEYWORDS,
    NEVER_SELL_KEYWORDS,
    RARE_CATCH_NOTIFY_KEYWORDS,
)
from .inventory.parsing import extract_weight_kg, normalize_fish_name, split_rule_names
from .inventory import flow as inventory_flow_module
from .inventory import reader as inventory_reader_module
from .inventory import rules as inventory_rules_module
from .inventory import sell as inventory_sell_module
from .inventory import verification as inventory_verification_module
from .inventory.flow import *
from .inventory.reader import *
from .inventory.rules import *
from .inventory.sell import *
from .inventory.verification import *
from .logging_utils import Log, now_wib
from .maintenance import parse_hhmm, parse_maintenance_schedule_input
from .state import *
from .telegram_bot import keyboards as keyboard_module
from .telegram_bot import handlers as handler_module
from .telegram_bot import callbacks as callback_module
from .telegram_bot import commands as command_module
from .telegram_bot import messages as message_module
from .telegram_bot import restore as restore_module
from .telegram_bot import texts as text_module
from .telegram_bot import premium as premium_module
from .telegram_bot import actions as action_module
from .telegram_bot.buttons import infer_button_style
from .telegram_bot.effects import (
    ALL_MESSAGE_EFFECT_IDS,
    DAILY_BROADCAST_MESSAGE_EFFECT_ID,
    FREE_MESSAGE_EFFECT_IDS,
    PREMIUM_MESSAGE_EFFECT_IDS,
)
from .telegram_bot.setup import build_telegram_bot
from .telegram_bot.keyboards import *
from .telegram_bot.premium import *
from .telegram_bot.texts import *
from .telegram_bot.handlers import *
from .telegram_bot.callbacks import *
from .telegram_bot.commands import *
from .telegram_bot.messages import *
from .telegram_bot.restore import *
from .telegram_bot.actions import *
from .backup import *
from .broadcast import *
from .notifications import *
from .reports import *
from .runtime import *
from .settings import *
from .accounts import *
from .admin import *
from .utils import format_wib_time, json_safe, load_json_file, parse_chat_target, split_chat_targets
from .userbot.client import app
from .userbot import login as login_module
from .userbot import commands as userbot_commands_module
from .userbot.commands import *
from .userbot.login import *
from .userbot.sessions import remove_session_files, session_files_for_name

# ==========================================
# PREMIUM TELEGRAM EMOJI
# ==========================================

# ==========================================
# NOTIFIKASI KE OWNER VIA BOT
# ==========================================

# ==========================================
# STATS + RUNTIME HEALTH
# ==========================================

AUDIT_ISSUE_EVENTS = {
    "captcha_failed",
    "restore_failed",
    "backup_failed",
    "login_failed",
    "special_open_failed",
    "error",
}

USER_LOG_MEDIA_ATTRS = (
    "photo",
    "video",
    "voice",
    "audio",
    "document",
    "animation",
    "video_note",
    "sticker",
)

# ==========================================
# HELPER UMUM
# ==========================================

# ==========================================
# HELPER: TUNGGU REPLY DARI BOT FISHING
# ==========================================

# ==========================================
# HELPER: TUNGGU EVENT MANCING
# ==========================================

# ==========================================
# RULES: WHITELIST / BLACKLIST IKAN
# ==========================================

# ==========================================
# VERIFIKASI: KLIK TOMBOL CEPAT
# ==========================================

# ==========================================
# INVENTORY: BACA SEMUA HALAMAN
# ==========================================

# ==========================================
# HELPER: TUNGGU PESAN BOT
# ==========================================

# ==========================================
# HELPER: KLIK TOMBOL KONFIRMASI JUAL SEMUA
# ==========================================

# ==========================================
# SELL FLOW
# ==========================================

# ==========================================
# LOOP UTAMA MANCING
# ==========================================

# ==========================================
# AKSES TELEGRAM BOT
# ==========================================

# ==========================================
# TELEGRAM BOT — COMMAND HANDLERS
# ==========================================

# ==========================================
# SETUP TELEGRAM BOT
# ==========================================
async def setup_telegram_bot() -> Application:
    return await build_telegram_bot(BOT_TOKEN, PremiumEmojiBot, {
        "tg_start": tg_start,
        "tg_menu": tg_menu,
        "tg_mancing": tg_mancing,
        "tg_inventory": tg_inventory,
        "tg_status": tg_status,
        "tg_settings": tg_settings,
        "tg_help": tg_help,
        "tg_lapor": tg_lapor,
        "tg_button_handler": tg_button_handler,
        "handle_userbot_login_contact": handle_userbot_login_contact,
        "tg_owner_text_handler": tg_owner_text_handler,
        "tg_error_handler": tg_error_handler,
    })

def bind_runtime_modules():
    namespace = globals()
    account_module.bind_runtime(namespace)
    admin_module.bind_runtime(namespace)
    notification_module.bind_runtime(namespace)
    keyboard_module.bind_runtime(namespace)
    handler_module.bind_runtime(namespace)
    callback_module.bind_runtime(namespace)
    command_module.bind_runtime(namespace)
    message_module.bind_runtime(namespace)
    restore_module.bind_runtime(namespace)
    action_module.bind_runtime(namespace)
    text_module.bind_runtime(namespace)
    premium_module.bind_runtime(namespace)
    backup_module.bind_runtime(namespace)
    broadcast_module.bind_runtime(namespace)
    report_module.bind_runtime(namespace)
    login_module.bind_runtime(namespace)
    userbot_commands_module.bind_runtime(namespace)
    runtime_module.bind_runtime(namespace)
    inventory_flow_module.bind_runtime(namespace)
    inventory_reader_module.bind_runtime(namespace)
    inventory_rules_module.bind_runtime(namespace)
    inventory_sell_module.bind_runtime(namespace)
    inventory_verification_module.bind_runtime(namespace)
    fishing_common_module.bind_runtime(namespace)
    fishing_group_room_module.bind_runtime(namespace)
    fishing_private_module.bind_runtime(namespace)
    fishing_rare_catch_module.bind_runtime(namespace)
    fishing_special_group_module.bind_runtime(namespace)
    fishing_user_media_module.bind_runtime(namespace)
    fishing_flow_module.bind_runtime(namespace)
    settings_module.bind_runtime(namespace)

bind_runtime_modules()
app.on_message(filters.me & filters.text & filters.regex(r"(?i)^(addprem|rmprem)(?:\s+(.+))?$"))(userbot_premium_command)
app.on_message(filters.me & filters.text & filters.regex(r"(?i)^restart$"))(userbot_restart_command)

# ==========================================
# MAIN — STARTUP + GRACEFUL SHUTDOWN
# ==========================================
async def main():
    global _tg_app, _is_running

    Log.p("STARTUP", "─" * 45)
    Log.p("STARTUP", "Fish Bot v1.4 | Pyrogram + Bot")
    Log.p("STARTUP", f"Target bot  : {FISH_BOT_USERNAME}")
    Log.p("STARTUP", f"Owner ID    : {OWNER_ID}")
    Log.p("STARTUP", "Verifikasi  : manual-assisted")
    Log.p("STARTUP", f"Action Delay: {ACTION_DELAY_MIN:g}-{ACTION_DELAY_MAX:g}s")
    Log.p("STARTUP", f"Sell Retry  : {SELL_RETRY_COUNT}x")
    Log.p("STARTUP", f"Auto Start  : {AUTO_START_FISHING}")
    Log.p("STARTUP", f"Maintenance : {'ON' if maintenance_enabled() else 'OFF'}")
    Log.p("STARTUP", f"Watchdog    : {WATCHDOG_TIMEOUT}s")
    Log.p("STARTUP", "─" * 45)

    backfill_broadcast_users()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(asyncio_exception_handler)

    def handle_signal():
        Log.p("SHUTDOWN", "Signal diterima, graceful shutdown...")
        _shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    Log.p("STARTUP", "Menghubungkan Telegram bot...")
    _tg_app = await setup_telegram_bot()
    bind_runtime_modules()
    await _tg_app.initialize()
    await _tg_app.start()
    await _tg_app.updater.start_polling(drop_pending_updates=True)
    Log.p("STARTUP", "✅ Telegram bot terhubung")
    asyncio.create_task(health_watchdog())
    asyncio.create_task(maintenance_schedule_watchdog())
    
    daily_config = load_daily_broadcast_config()
    if daily_config.get("enabled"):
        try:
            await refresh_daily_broadcast_scheduler()
        except Exception as e:
            Log.p("ERROR", f"Gagal jadwalkan daily broadcast: {e}")

    Log.p("STARTUP", "Menghubungkan userbot Pyrogram...")
    connected = False
    if session_files_for_name("fishbot_session")[0].exists():
        for attempt in range(1, 4):
            try:
                await app.start()
                connected = True
                break
            except Exception as e:
                wait = 2 ** attempt
                Log.p("WARN", f"Koneksi gagal (attempt {attempt}/3), retry {wait}s: {e}")
                await asyncio.sleep(wait)
    else:
        Log.p("WARN", "Session main belum ada. Telegram bot tetap online; login userbot lewat Settings → Userbot.")

    if connected:
        me = await app.get_me()
        set_main_premium_status_from_user(me, "main")
        _account_clients["main"] = app
        _account_running["main"] = False
        ensure_private_captcha_watcher("main", app)
        ensure_user_media_log_watcher("main", app)
        Log.p("STARTUP", f"✅ Userbot    : {me.first_name} (@{me.username})")
    else:
        Log.p("WARN", "Main userbot belum terhubung. Fitur kontrol tetap tersedia untuk login ulang.")
    Log.p("STARTUP", "─" * 45)
    await start_user_media_log_clients()
    Log.p("STARTUP", "Semua siap! Cara pakai:")
    Log.p("STARTUP", "  • Chat bot Telegram → /start")
    Log.p("STARTUP", "  • Kontrol mancing   → /mancing")
    Log.p("STARTUP", "─" * 45)

    if AUTO_START_FISHING and not is_any_running() and not maintenance_enabled():
        asyncio.create_task(start_all_accounts(auto_start_only=True))
        Log.p("STARTUP", "Loop mancing auto-start aktif untuk semua akun")
    elif maintenance_enabled():
        Log.p("STARTUP", "Auto-start dilewati karena maintenance aktif")

    await complete_pending_restart_notification()

    await idle()

    _shutdown_event.set()

    Log.p("SHUTDOWN", "Menghentikan Telegram bot...")
    await _tg_app.updater.stop()
    await _tg_app.stop()
    await _tg_app.shutdown()

    Log.p("SHUTDOWN", "Menghentikan userbot...")
    await stop_account_clients()
    if _account_clients.get("main") is app:
        remove_private_captcha_watcher("main", app)
        remove_user_media_log_watcher("main", app)
        await app.stop()

    Log.p("SHUTDOWN", "✅ Bot berhenti dengan bersih.")
