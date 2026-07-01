from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def register_broadcast_user(user, source: str = "start"):
    user_id = safe_user_id(getattr(user, "id", user if isinstance(user, int) else 0))
    if not user_id:
        return
    payload = {
        "user_id": user_id,
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "username": getattr(user, "username", None),
        "source": source,
        "is_admin_snapshot": user_id in load_admin_ids(),
        "blocked": False,
        "last_seen": now_wib(),
    }
    if mongo_enabled():
        try:
            mongo_col.update_one(
                {"type": "broadcast_user", "user_id": user_id},
                {"$set": payload, "$setOnInsert": {"type": "broadcast_user", "created_at": now_wib()}},
                upsert=True,
            )
        except PyMongoError as e:
            Log.p("WARN", f"Mongo simpan broadcast user gagal: {e}")
        return

    data = {}
    if BROADCAST_USERS_FILE.exists():
        try:
            loaded = json.loads(BROADCAST_USERS_FILE.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            Log.p("WARN", f"Gagal baca broadcast_users.json: {e}")
    payload["last_seen"] = payload["last_seen"].isoformat()
    data[str(user_id)] = {**data.get(str(user_id), {}), **payload}
    BROADCAST_USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def mark_broadcast_user_blocked(user_id: int, blocked: bool = True):
    user_id = safe_user_id(user_id)
    if not user_id:
        return
    if mongo_enabled():
        try:
            mongo_col.update_one(
                {"type": "broadcast_user", "user_id": user_id},
                {"$set": {"blocked": bool(blocked), "updated_at": now_wib()}},
            )
        except PyMongoError as e:
            Log.p("WARN", f"Mongo update blocked broadcast user gagal: {e}")
        return
    if not BROADCAST_USERS_FILE.exists():
        return
    try:
        data = json.loads(BROADCAST_USERS_FILE.read_text(encoding="utf-8"))
        key = str(user_id)
        if key in data:
            data[key]["blocked"] = bool(blocked)
            data[key]["updated_at"] = now_wib().isoformat()
            BROADCAST_USERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal update broadcast_users.json: {e}")


def backfill_broadcast_users():
    class _User:
        def __init__(self, user_id: int):
            self.id = user_id
            self.first_name = None
            self.last_name = None
            self.username = None

    ids = set(load_admin_ids())
    for account in load_all_accounts():
        ids.update(account_owner_ids(account))
    for user_id in sorted(ids):
        register_broadcast_user(_User(user_id), source="backfill")


def broadcast_user_ids(kind: str = "public") -> list[int]:
    kind = (kind or "public").strip().lower()
    if kind == "premium":
        allowed = set(admin_user_ids(include_owner=False))
    else:
        allowed = None

    ids: set[int] = set()
    if mongo_enabled():
        try:
            for doc in mongo_col.find({"type": "broadcast_user", "blocked": {"$ne": True}}, {"user_id": 1}):
                user_id = safe_user_id(doc.get("user_id"))
                if user_id and user_id != OWNER_ID and (allowed is None or user_id in allowed):
                    ids.add(user_id)
        except PyMongoError as e:
            Log.p("WARN", f"Mongo list broadcast user gagal: {e}")
    elif BROADCAST_USERS_FILE.exists():
        try:
            data = json.loads(BROADCAST_USERS_FILE.read_text(encoding="utf-8"))
            for raw_id, doc in data.items():
                user_id = safe_user_id((doc or {}).get("user_id") or raw_id)
                if user_id and user_id != OWNER_ID and not (doc or {}).get("blocked") and (allowed is None or user_id in allowed):
                    ids.add(user_id)
        except Exception as e:
            Log.p("WARN", f"Gagal baca broadcast_users.json: {e}")

    if allowed is not None:
        ids.update(allowed)
    return sorted(ids)


def broadcast_payload_preview(payload: dict) -> str:
    if not payload:
        return "-"
    if payload.get("type") == "forward":
        return f"Forward {payload.get('kind', 'message')} dari chat {payload.get('from_chat_id')} message {payload.get('message_id')}"
    if payload.get("type") == "copy":
        preview = (payload.get("caption") or "").strip().replace("\n", " ")
        suffix = f": {preview[:240]}" if preview else ""
        return f"Copy {payload.get('kind', 'message')} dari chat {payload.get('from_chat_id')} message {payload.get('message_id')}{suffix}"
    text = (payload.get("text") or "").strip()
    return text.replace("\n", " ")[:300] or "-"


def broadcast_message_kind(message) -> str:
    checks = (
        ("photo", "foto"),
        ("video", "video"),
        ("document", "dokumen"),
        ("animation", "animasi"),
        ("audio", "audio"),
        ("voice", "voice"),
        ("video_note", "video note"),
        ("sticker", "stiker"),
        ("location", "lokasi"),
        ("venue", "venue"),
        ("contact", "kontak"),
        ("poll", "poll"),
        ("dice", "dice"),
    )
    for attr, label in checks:
        if getattr(message, attr, None):
            return label
    if getattr(message, "caption", None):
        return "media"
    return "pesan"


def record_broadcast_message(user_id: int, message_id: int, payload: dict, target_kind: str, owner_id: int):
    user_id = safe_user_id(user_id)
    message_id = int(message_id or 0)
    if not user_id or not message_id:
        return
    key = f"{user_id}:{message_id}"
    doc = {
        "key": key,
        "user_id": user_id,
        "message_id": message_id,
        "target_kind": (target_kind or "premium").strip().lower(),
        "owner_id": safe_user_id(owner_id) or OWNER_ID,
        "payload_type": payload.get("type") if payload else "-",
        "preview": broadcast_payload_preview(payload),
        "created_at": now_wib(),
    }
    if mongo_enabled():
        try:
            mongo_col.update_one(
                {"type": "broadcast_message", "key": key},
                {"$set": doc, "$setOnInsert": {"type": "broadcast_message"}},
                upsert=True,
            )
        except PyMongoError as e:
            Log.p("WARN", f"Mongo simpan broadcast message gagal: {e}")
        return

    data = {}
    if BROADCAST_MESSAGES_FILE.exists():
        try:
            loaded = json.loads(BROADCAST_MESSAGES_FILE.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            Log.p("WARN", f"Gagal baca broadcast_messages.json: {e}")
    doc["created_at"] = doc["created_at"].isoformat()
    data[key] = doc
    try:
        BROADCAST_MESSAGES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal simpan broadcast_messages.json: {e}")


def find_broadcast_message(user_id: int, message_id: int) -> dict | None:
    user_id = safe_user_id(user_id)
    message_id = int(message_id or 0)
    if not user_id or not message_id:
        return None
    key = f"{user_id}:{message_id}"
    if mongo_enabled():
        try:
            return mongo_col.find_one({"type": "broadcast_message", "key": key})
        except PyMongoError as e:
            Log.p("WARN", f"Mongo baca broadcast message gagal: {e}")
            return None
    if not BROADCAST_MESSAGES_FILE.exists():
        return None
    try:
        data = json.loads(BROADCAST_MESSAGES_FILE.read_text(encoding="utf-8"))
        doc = data.get(key)
        return doc if isinstance(doc, dict) else None
    except Exception as e:
        Log.p("WARN", f"Gagal baca broadcast_messages.json: {e}")
        return None


def load_daily_broadcast_config() -> dict:
    return load_json_file(DAILY_BROADCAST_FILE, {"enabled": False, "time": "20:00", "target": "premium", "payload": None})


def save_daily_broadcast_config(data: dict):
    DAILY_BROADCAST_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_daily_broadcast_time(value: str) -> tuple[int, int] | None:
    match = re.match(r"^([01][0-9]|2[0-3]):([0-5][0-9])$", str(value or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _daily_broadcast_seconds_until_next_run(time_str: str) -> float | None:
    parsed = _parse_daily_broadcast_time(time_str)
    if not parsed:
        return None
    hour, minute = parsed
    now = now_wib()
    run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run_at <= now:
        run_at += timedelta(days=1)
    return max(0.0, (run_at - now).total_seconds())


def _cancel_daily_broadcast_fallback_task():
    global _daily_broadcast_fallback_task
    task = _daily_broadcast_fallback_task
    cancel_task_background(task, label="main", reason="cancel daily broadcast fallback")
    _daily_broadcast_fallback_task = None


def _remove_daily_broadcast_job_queue_job():
    if _tg_app and _tg_app.job_queue:
        jobs = _tg_app.job_queue.get_jobs_by_name("daily_broadcast_job")
        for job in jobs:
            job.schedule_removal()


async def _run_daily_broadcast_payload(bot, *, effect_id: str | None = None):
    config = load_daily_broadcast_config()
    if not config.get("enabled"):
        return
    payload = config.get("payload")
    if not payload:
        return
    
    target_kind = config.get("target", "premium")
    targets = broadcast_user_ids(target_kind)
    sent = 0
    failed = 0
    
    Log.p("NOTIF", f"Mulai auto daily broadcast ke {len(targets)} user {target_kind}")
    
    for target_id in targets:
        try:
            if payload.get("type") == "forward":
                sent_msg = await bot.forward_message(
                    chat_id=target_id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            elif payload.get("type") == "copy":
                sent_msg = await bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            else:
                send_kwargs = {"chat_id": target_id, "text": payload.get("text", ""), "parse_mode": "HTML"}
                if effect_id:
                    send_kwargs["message_effect_id"] = effect_id
                try:
                    sent_msg = await bot.send_message(**send_kwargs)
                except BadRequest as effect_error:
                    if effect_id and message_effect_error(effect_error):
                        send_kwargs.pop("message_effect_id", None)
                        Log.p("WARN", "Daily broadcast effect ditolak Telegram, retry tanpa effect")
                        sent_msg = await bot.send_message(**send_kwargs)
                    else:
                        raise
            
            record_broadcast_message(target_id, sent_msg.message_id, payload, target_kind, bot.id)
            sent += 1
            if target_kind == "public":
                mark_broadcast_user_blocked(target_id, False)
            await asyncio.sleep(0.08)
        except Exception as e:
            failed += 1
            if target_kind == "public":
                mark_broadcast_user_blocked(target_id, True)
    
    Log.p("NOTIF", f"Daily broadcast selesai. Terkirim: {sent}, Gagal: {failed}")


async def run_daily_broadcast(context):
    await _run_daily_broadcast_payload(context.bot, effect_id=DAILY_BROADCAST_MESSAGE_EFFECT_ID)


async def refresh_daily_broadcast_scheduler():
    global _daily_broadcast_fallback_task
    config = load_daily_broadcast_config()
    _remove_daily_broadcast_job_queue_job()
    _cancel_daily_broadcast_fallback_task()

    if not config.get("enabled"):
        return

    time_str = config.get("time", "20:00")
    if _tg_app and _tg_app.job_queue:
        parsed = _parse_daily_broadcast_time(time_str)
        if not parsed:
            Log.p("WARN", f"Format jam daily broadcast tidak valid: {time_str}")
            return
        hour, minute = parsed
        from datetime import time
        from zoneinfo import ZoneInfo
        run_time = time(hour=hour, minute=minute, tzinfo=ZoneInfo("Asia/Jakarta"))
        _tg_app.job_queue.run_daily(
            run_daily_broadcast,
            time=run_time,
            name="daily_broadcast_job",
        )
        Log.p("STARTUP", f"Daily broadcast terjadwal pada {time_str} WIB")
        return

    if not _tg_app or not _tg_app.bot:
        return

    async def fallback_loop():
        try:
            while not _shutdown_event.is_set():
                config_now = load_daily_broadcast_config()
                if not config_now.get("enabled"):
                    return
                delay = _daily_broadcast_seconds_until_next_run(config_now.get("time", "20:00"))
                if delay is None:
                    Log.p("WARN", f"Format jam daily broadcast tidak valid: {config_now.get('time', '20:00')}")
                    return
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    pass
                if _shutdown_event.is_set():
                    return
                await _run_daily_broadcast_payload(_tg_app.bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            Log.p("ERROR", f"Fallback daily broadcast gagal: {e}")

    _daily_broadcast_fallback_task = asyncio.create_task(fallback_loop())
    Log.p("STARTUP", f"Daily broadcast fallback aktif pada {time_str} WIB")


