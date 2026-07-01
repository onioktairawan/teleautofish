from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def touch_activity(action: str = None, event: str = None, label: str = "main"):
    global _last_activity_at, _last_action, _last_fish_event
    now = now_wib()
    _last_activity_at = now
    _account_last_activity[label] = now
    if action:
        _last_action = action
        _account_last_action[label] = action
    if event:
        _last_fish_event = event
        _account_last_event[label] = event


def load_stats(label: str = None) -> dict:
    label = ctx_label(label)
    default = {
        "mancing_sent": 0,
        "sessions_done": 0,
        "inventory_full": 0,
        "sell_success": 0,
        "captcha_solved": 0,
        "captcha_failed": 0,
        "watchdog_pokes": 0,
    }
    doc = db_get_doc("stats", label)
    if doc:
        default.update({k: int(doc.get(k, v)) for k, v in default.items()})
        return default
    if not STATS_FILE.exists():
        return default
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        default.update({k: int(data.get(k, v)) for k, v in default.items()})
    except Exception as e:
        Log.p("WARN", f"Gagal baca fish_stats.json: {e}")
    return default


def save_stats(stats: dict, label: str = None):
    label = ctx_label(label)
    if mongo_enabled():
        db_upsert_doc("stats", label, {k: int(v) for k, v in stats.items()})
        return
    STATS_FILE.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")


def load_admin_ids() -> set[int]:
    global _admin_ids_cache, _admin_ids_cache_ts
    now = time.monotonic()
    if _admin_ids_cache and (now - _admin_ids_cache_ts) < _ADMIN_CACHE_TTL:
        return set(_admin_ids_cache)

    admins = {OWNER_ID}
    if mongo_enabled():
        doc = db_get_doc("config", "admins") or {}
        for raw_id in doc.get("admins", []):
            try:
                admins.add(int(raw_id))
            except (TypeError, ValueError):
                continue

    if ADMINS_FILE.exists():
        try:
            data = json.loads(ADMINS_FILE.read_text(encoding="utf-8"))
            for raw_id in data.get("admins", []):
                try:
                    admins.add(int(raw_id))
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            Log.p("WARN", f"Gagal baca bot_admins.json: {e}")

    _admin_ids_cache = set(admins)
    _admin_ids_cache_ts = now
    return set(admins)


def save_admin_ids(admins: set[int]):
    cleaned = sorted({int(admin_id) for admin_id in admins if int(admin_id) > 0})
    if mongo_enabled():
        db_upsert_doc("config", "admins", {"admins": cleaned})
    ADMINS_FILE.write_text(json.dumps({"admins": cleaned}, indent=2, ensure_ascii=False), encoding="utf-8")
    invalidate_admin_cache()


def is_admin_user(user_id: int) -> bool:
    user_id = int(user_id or 0)
    return user_id in load_admin_ids()


def can_manage_admins(user_id: int) -> bool:
    return int(user_id or 0) == OWNER_ID


def load_maintenance_config() -> dict:
    if mongo_enabled():
        doc = db_get_doc("config", "maintenance")
        if doc is not None:
            return doc
    if MAINTENANCE_FILE.exists():
        try:
            data = json.loads(MAINTENANCE_FILE.read_text(encoding="utf-8"))
            return data or {}
        except Exception as e:
            Log.p("WARN", f"Gagal baca bot_maintenance.json: {e}")
    return {}


def maintenance_enabled() -> bool:
    return bool(load_maintenance_config().get("enabled", False))


def maintenance_blocks_account(label: str = "main") -> bool:
    return maintenance_enabled() and ctx_label(label) != "main"


def maintenance_resume_labels() -> list[str]:
    data = load_maintenance_config()
    labels = data.get("resume_labels") or []
    if not isinstance(labels, list):
        return []
    return [ctx_label(label) for label in labels if str(label or "").strip()]


def maintenance_schedule_settings() -> tuple[bool, str, str]:
    data = load_maintenance_config()
    enabled = bool(data.get("schedule_enabled", False))
    start = parse_hhmm(data.get("schedule_start", "18:00")) or "18:00"
    end = parse_hhmm(data.get("schedule_end", "20:00")) or "20:00"
    return enabled, start, end


def maintenance_schedule_active_now(current: datetime = None) -> tuple[bool, str]:
    enabled, start, end = maintenance_schedule_settings()
    if not enabled:
        return False, ""
    now = current or now_wib()
    start_hour, start_minute = [int(part) for part in start.split(":", 1)]
    end_hour, end_minute = [int(part) for part in end.split(":", 1)]
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    now_minutes = now.hour * 60 + now.minute
    today = now.date().isoformat()
    yesterday = (now - timedelta(days=1)).date().isoformat()
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes, today
    if now_minutes >= start_minutes:
        return True, today
    if now_minutes < end_minutes:
        return True, yesterday
    return False, ""


def save_maintenance_enabled(enabled: bool, user_id: int = 0, resume_labels: list[str] = None):
    current = load_maintenance_config()
    saved_resume_labels = current.get("resume_labels") or []
    payload = {
        "enabled": bool(enabled),
        "updated_at": now_wib(),
        "updated_by": safe_user_id(user_id),
        "resume_labels": saved_resume_labels if resume_labels is None else sorted({ctx_label(label) for label in resume_labels}),
        "schedule_enabled": bool(current.get("schedule_enabled", False)),
        "schedule_start": parse_hhmm(current.get("schedule_start", "18:00")) or "18:00",
        "schedule_end": parse_hhmm(current.get("schedule_end", "20:00")) or "20:00",
        "schedule_active_key": str(current.get("schedule_active_key", "") or ""),
        "schedule_last_start_key": str(current.get("schedule_last_start_key", "") or ""),
        "schedule_last_end_key": str(current.get("schedule_last_end_key", "") or ""),
    }
    if mongo_enabled():
        db_upsert_doc("config", "maintenance", payload)
    file_payload = {**payload, "updated_at": payload["updated_at"].isoformat()}
    try:
        MAINTENANCE_FILE.write_text(json.dumps(file_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal simpan bot_maintenance.json: {e}")


def clear_maintenance_resume_labels(user_id: int = 0):
    save_maintenance_enabled(False, user_id=user_id, resume_labels=[])


def save_maintenance_schedule(enabled: bool, start: str = None, end: str = None, user_id: int = 0):
    current = load_maintenance_config()
    payload = {
        "enabled": bool(current.get("enabled", False)),
        "resume_labels": current.get("resume_labels") or [],
        "schedule_enabled": bool(enabled),
        "schedule_start": parse_hhmm(start or current.get("schedule_start", "18:00")) or "18:00",
        "schedule_end": parse_hhmm(end or current.get("schedule_end", "20:00")) or "20:00",
        "schedule_active_key": str(current.get("schedule_active_key", "") or ""),
        "schedule_last_start_key": str(current.get("schedule_last_start_key", "") or ""),
        "schedule_last_end_key": str(current.get("schedule_last_end_key", "") or ""),
        "updated_at": now_wib(),
        "updated_by": safe_user_id(user_id),
    }
    if not enabled:
        payload["schedule_active_key"] = ""
    if mongo_enabled():
        db_upsert_doc("config", "maintenance", payload)
    file_payload = {**payload, "updated_at": payload["updated_at"].isoformat()}
    try:
        MAINTENANCE_FILE.write_text(json.dumps(file_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal simpan jadwal maintenance: {e}")


def save_maintenance_schedule_marker(**updates):
    current = load_maintenance_config()
    payload = {
        "enabled": bool(current.get("enabled", False)),
        "resume_labels": current.get("resume_labels") or [],
        "schedule_enabled": bool(current.get("schedule_enabled", False)),
        "schedule_start": parse_hhmm(current.get("schedule_start", "18:00")) or "18:00",
        "schedule_end": parse_hhmm(current.get("schedule_end", "20:00")) or "20:00",
        "schedule_active_key": str(current.get("schedule_active_key", "") or ""),
        "schedule_last_start_key": str(current.get("schedule_last_start_key", "") or ""),
        "schedule_last_end_key": str(current.get("schedule_last_end_key", "") or ""),
        "updated_at": now_wib(),
        "updated_by": safe_user_id(updates.pop("user_id", 0)),
    }
    payload.update(updates)
    if mongo_enabled():
        db_upsert_doc("config", "maintenance", payload)
    file_payload = {**payload, "updated_at": payload["updated_at"].isoformat()}
    try:
        MAINTENANCE_FILE.write_text(json.dumps(file_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal simpan marker jadwal maintenance: {e}")


def maintenance_message_text() -> str:
    return (
        "🛠 <b>Maintenance</b>\n\n"
        + blockquote("Bot sedang maintenance sementara. Semua fitur user dijeda sampai owner membuka akses lagi.")
    )


def maintenance_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("🐞 Lapor", "report:start", "danger")]])


def safe_user_id(value, default: int = 0) -> int:
    try:
        user_id = int(value or 0)
    except (TypeError, ValueError):
        return int(default or 0)
    return user_id if user_id > 0 else int(default or 0)


def account_owner_ids(account: dict, fallback: int = 0) -> list[int]:
    ids = []
    for raw_id in (account or {}).get("owner_ids", []):
        user_id = safe_user_id(raw_id)
        if user_id:
            ids.append(user_id)
    fallback_id = safe_user_id(fallback)
    if fallback_id:
        ids.append(fallback_id)
    return sorted(set(ids))


def account_primary_owner_id(account: dict, fallback: int = 0) -> int:
    owner_ids = account_owner_ids(account, fallback)
    return owner_ids[0] if owner_ids else safe_user_id(fallback)


def account_notification_owner_ids(account: dict, label: str = None) -> list[int]:
    label = ctx_label(label or (account or {}).get("label") or "main")
    owner_ids = account_owner_ids(account)
    if not owner_ids:
        return [OWNER_ID]
    non_owner_ids = [user_id for user_id in owner_ids if user_id != OWNER_ID]
    if label != "main" and non_owner_ids:
        return non_owner_ids
    return owner_ids


def can_access_account(user_id: int, label: str) -> bool:
    user_id = int(user_id or 0)
    if user_id == OWNER_ID:
        return True
    account = load_account(label)
    return user_id in set(account_owner_ids(account))


def selected_account_label(user_id: int) -> str:
    user_id = int(user_id or 0)
    selected = _selected_account_by_user.get(user_id, "main")
    if can_access_account(user_id, selected):
        return selected
    accounts = load_accounts_for_user(user_id)
    if accounts:
        label = accounts[0]["label"]
        _selected_account_by_user[user_id] = label
        return label
    return "main" if int(user_id or 0) == OWNER_ID else default_user_account_label(user_id)


def default_user_account_label(user_id: int) -> str:
    return safe_label(f"user_{int(user_id or 0)}")


def preferred_login_label(user_id: int) -> str:
    accounts = load_accounts_for_user(user_id)
    if accounts:
        return selected_account_label(user_id)
    return default_user_account_label(user_id)


def add_admin_id(admin_id: int) -> bool:
    admins = load_admin_ids()
    before = len(admins)
    admins.add(int(admin_id))
    save_admin_ids(admins)
    return len(admins) > before


def remove_admin_id(admin_id: int) -> bool:
    admin_id = int(admin_id or 0)
    if admin_id == OWNER_ID:
        return False
    admins = load_admin_ids()
    before = len(admins)
    admins.discard(admin_id)
    save_admin_ids(admins)
    return len(admins) < before


def audit_log(label: str, event: str, message: str = "", user_id: int = None):
    label = ctx_label(label)
    if not mongo_enabled():
        return
    try:
        mongo_col.insert_one({
            "type": "audit",
            "label": label,
            "event": event,
            "message": str(message or "")[:800],
            "user_id": int(user_id or 0),
            "created_at": now_wib(),
        })
    except PyMongoError as e:
        Log.p("WARN", f"Mongo audit gagal: {e}")


def load_audit_logs(limit: int = 10, label: str = None, issues_only: bool = False) -> list[dict]:
    if not mongo_enabled():
        return []
    try:
        query = {"type": "audit"}
        if label:
            query["label"] = ctx_label(label)
        if issues_only:
            query["event"] = {"$in": sorted(AUDIT_ISSUE_EVENTS)}
        return list(mongo_col.find(query).sort("created_at", -1).limit(int(limit)))
    except PyMongoError as e:
        Log.p("WARN", f"Mongo audit list gagal: {e}")
        return []


def admin_user_ids(include_owner: bool = False) -> list[int]:
    ids = sorted(load_admin_ids())
    if include_owner:
        return ids
    return [user_id for user_id in ids if user_id != OWNER_ID]


