from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def load_extra_group_chats(label: str = None) -> list[str]:
    label = ctx_label(label)
    account = db_get_doc("account", label)
    if account is not None:
        return split_chat_targets("\n".join(str(x) for x in account.get("groups", [])))
    if not GROUPS_FILE.exists():
        return []
    try:
        data = json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
        return split_chat_targets("\n".join(str(x) for x in data.get("groups", [])))
    except Exception as e:
        Log.p("WARN", f"Gagal baca fish_groups.json: {e}")
        return []


def save_extra_group_chats(groups: list[str], label: str = None):
    label = ctx_label(label)
    cleaned = split_chat_targets("\n".join(groups))
    if mongo_enabled():
        db_upsert_doc("account", label, {"groups": cleaned})
        return
    GROUPS_FILE.write_text(json.dumps({"groups": cleaned}, indent=2, ensure_ascii=False), encoding="utf-8")


def configured_group_chats(label: str = None) -> list[str]:
    label = ctx_label(label)
    if mongo_enabled():
        return load_extra_group_chats(label)
    return split_chat_targets("\n".join([FISH_GROUP_CHAT, *load_extra_group_chats(label)]))


def fish_group_chat_targets(label: str = None) -> list[int | str]:
    return [parse_chat_target(chat) for chat in configured_group_chats(label)]


def load_special_group_chat(label: str = None) -> str:
    label = ctx_label(label)
    account = db_get_doc("account", label)
    if account is not None:
        chats = split_chat_targets(str(account.get("special_group", "") or ""))
        return chats[0] if chats else ""
    if not SPECIAL_GROUP_FILE.exists():
        return ""
    try:
        data = json.loads(SPECIAL_GROUP_FILE.read_text(encoding="utf-8"))
        chats = split_chat_targets(str(data.get("special_group", "") or ""))
        return chats[0] if chats else ""
    except Exception as e:
        Log.p("WARN", f"Gagal baca fish_special_group.json: {e}")
        return ""


def save_special_group_chat(chat: str, label: str = None):
    label = ctx_label(label)
    chats = split_chat_targets(chat)
    target = chats[0] if chats else ""
    if mongo_enabled():
        db_upsert_doc("account", label, {"special_group": target})
        return
    data = load_json_file(SPECIAL_GROUP_FILE, {})
    data["special_group"] = target
    SPECIAL_GROUP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def special_auto_open_enabled(label: str = None) -> bool:
    label = ctx_label(label)
    if not mongo_enabled() and SPECIAL_GROUP_FILE.exists():
        data = load_json_file(SPECIAL_GROUP_FILE, {})
        return bool(data.get("special_auto_open", True))
    account = load_account(label)
    return bool(account.get("special_auto_open", True))


def save_special_auto_open(label: str, enabled: bool):
    label = ctx_label(label)
    if mongo_enabled():
        db_upsert_doc("account", label, {"special_auto_open": bool(enabled)})
        return
    data = load_json_file(SPECIAL_GROUP_FILE, {})
    data["special_auto_open"] = bool(enabled)
    SPECIAL_GROUP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def special_auto_boost_enabled(label: str = None) -> bool:
    label = ctx_label(label)
    if not mongo_enabled() and SPECIAL_GROUP_FILE.exists():
        data = load_json_file(SPECIAL_GROUP_FILE, {})
        return bool(data.get("special_auto_boost", True))
    account = load_account(label)
    return bool(account.get("special_auto_boost", True))


def save_special_auto_boost(label: str, enabled: bool):
    label = ctx_label(label)
    if mongo_enabled():
        db_upsert_doc("account", label, {"special_auto_boost": bool(enabled)})
        return
    data = load_json_file(SPECIAL_GROUP_FILE, {})
    data["special_auto_boost"] = bool(enabled)
    SPECIAL_GROUP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def special_open_delay_range(label: str = None) -> tuple[float, float]:
    label = ctx_label(label)
    account = load_json_file(SPECIAL_GROUP_FILE, {}) if not mongo_enabled() and SPECIAL_GROUP_FILE.exists() else load_account(label)
    try:
        low = float(account.get("special_open_delay_min", SPECIAL_OPEN_DELAY_MIN))
        high = float(account.get("special_open_delay_max", SPECIAL_OPEN_DELAY_MAX))
    except (TypeError, ValueError):
        low, high = SPECIAL_OPEN_DELAY_MIN, SPECIAL_OPEN_DELAY_MAX
    low = max(1, min(300, low))
    high = max(1, min(300, high))
    if high < low:
        low, high = high, low
    return low, high


def save_special_open_delay(label: str, low: int, high: int):
    label = ctx_label(label)
    low = max(1, min(300, int(low)))
    high = max(1, min(300, int(high)))
    if high < low:
        low, high = high, low
    update = {"special_open_delay_min": low, "special_open_delay_max": high}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    data = load_json_file(SPECIAL_GROUP_FILE, {})
    data.update(update)
    SPECIAL_GROUP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def special_group_chat_target(label: str = None):
    chat = load_special_group_chat(label)
    return parse_chat_target(chat) if chat else None


def special_group_filter(label: str = "main"):
    target = special_group_chat_target(label)
    return filters.chat(target) if target else None


def add_group_chat(chat: str, label: str = None) -> tuple[bool, str]:
    label = ctx_label(label)
    target = (chat or "").strip()
    if not target:
        return False, "Group kosong."
    groups = load_extra_group_chats(label)
    if target in configured_group_chats(label):
        return False, f"`{target}` sudah ada di daftar grup."
    groups.append(target)
    save_extra_group_chats(groups, label)
    return True, f"`{target}` ditambahkan ke daftar grup."


def remove_group_chat(chat: str, label: str = None) -> tuple[bool, str]:
    label = ctx_label(label)
    target = (chat or "").strip()
    if not target:
        return False, "Group kosong."
    groups = load_extra_group_chats(label)
    if target not in groups:
        if not mongo_enabled() and target in split_chat_targets(FISH_GROUP_CHAT):
            return False, f"`{target}` berasal dari .env, hapus dari FISH_GROUP_CHAT jika ingin dihilangkan."
        return False, f"`{target}` tidak ada di daftar tambahan."
    groups = [group for group in groups if group != target]
    save_extra_group_chats(groups, label)
    return True, f"`{target}` dihapus dari daftar grup."


def active_group_chat_target(label: str = "main"):
    return _account_active_group_chat.get(label)


def set_active_group_chat(label: str, chat):
    if chat:
        _account_active_group_chat[label] = chat


def clear_active_group_chat(label: str):
    _account_active_group_chat.pop(label, None)


def group_room_filter(label: str = "main"):
    active_chat = active_group_chat_target(label)
    if active_chat:
        return filters.chat(active_chat)
    targets = fish_group_chat_targets(label)
    if not targets:
        return None
    return filters.chat(targets)


def load_runtime_mode(label: str = None) -> str:
    label = ctx_label(label)
    account = db_get_doc("account", label)
    if account:
        mode = str(account.get("mode", "")).strip().lower()
        if mode in VALID_FISH_MODES:
            return mode
    if MODE_FILE.exists():
        try:
            data = json.loads(MODE_FILE.read_text(encoding="utf-8"))
            mode = str(data.get("mode", "")).strip().lower()
            if mode in VALID_FISH_MODES:
                return mode
        except Exception as e:
            Log.p("WARN", f"Gagal baca bot_mode.json: {e}")

    return FISH_MODE if FISH_MODE in VALID_FISH_MODES else "private"


def save_runtime_mode(mode: str, label: str = None):
    label = ctx_label(label)
    mode = (mode or "").strip().lower()
    if mode not in VALID_FISH_MODES:
        raise ValueError(f"Mode tidak valid: {mode}")
    if mongo_enabled():
        db_upsert_doc("account", label, {"mode": mode})
        return
    MODE_FILE.write_text(json.dumps({"mode": mode}, indent=2, ensure_ascii=False), encoding="utf-8")


def current_fish_mode(label: str = None) -> str:
    return load_runtime_mode(label)


def mode_log_name(mode: str = None) -> str:
    return {
        "private": "private",
        "group_room": "grup",
        "all": "hybrid",
        "special_group": "grup khusus",
    }.get(str(mode or "").strip().lower(), str(mode or "-"))


def fish_log_ctx(label: str = None, mode: str = None) -> str:
    label = ctx_label(label)
    mode = mode or current_fish_mode(label)
    return f"[{label}] [{mode_log_name(mode)}]"


def account_int_setting(label: str, key: str, default: int, min_value: int = 0, max_value: int = 999) -> int:
    account = load_account(label)
    try:
        value = int(account.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def save_account_auto_start(label: str, enabled: bool):
    label = ctx_label(label)
    if mongo_enabled():
        db_upsert_doc("account", label, {"auto_start": bool(enabled)})
        return
    save_account_state_update(label, {"auto_start": bool(enabled)})


def private_auto_boost_enabled(label: str = None) -> bool:
    account = load_account(ctx_label(label))
    return bool(account.get("private_auto_boost", True))


def private_boost_paused(label: str = None) -> bool:
    account = load_account(ctx_label(label))
    return bool(account.get("private_boost_paused", False))


def save_private_auto_boost(label: str, enabled: bool):
    label = ctx_label(label)
    update = {"private_auto_boost": bool(enabled)}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def save_private_boost_paused(label: str, paused: bool):
    label = ctx_label(label)
    update = {"private_boost_paused": bool(paused)}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def save_verification_state(label: str, required: bool, url: str = "", message: str = ""):
    label = ctx_label(label)
    update = {
        "verification_required": bool(required),
        "verification_url": (url or "")[:1000] if required else "",
        "verification_message": (message or "")[:1000] if required else "",
        "verification_detected_at": now_wib().isoformat() if required else "",
    }
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def verification_required(label: str = None) -> bool:
    account = load_account(ctx_label(label))
    return bool(account.get("verification_required", False))


def normalize_bot_username(value: str) -> str | None:
    username = (value or "").strip()
    if username.startswith("https://t.me/"):
        username = username.rsplit("/", 1)[-1]
    username = username.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return None
    return f"@{username}"


def saved_private_bot_username(label: str = None) -> str:
    account = load_account(ctx_label(label))
    return normalize_bot_username(account.get("private_bot_username")) or FISH_BOT_USERNAME


def private_command_bot_username(label: str = None) -> str:
    label = ctx_label(label)
    if current_fish_mode(label) == "private":
        return saved_private_bot_username(label)
    return FISH_BOT_USERNAME


def save_private_bot_username(label: str, username: str):
    label = ctx_label(label)
    normalized = normalize_bot_username(username)
    if not normalized:
        raise ValueError("Username bot tidak valid")
    update = {"private_bot_username": normalized}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def reset_private_bot_username(label: str):
    label = ctx_label(label)
    update = {"private_bot_username": ""}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def poseidon_favorite_enabled(label: str = None) -> bool:
    account = load_account(ctx_label(label))
    return bool(account.get("poseidon_favorite_enabled", True))


def save_poseidon_favorite_enabled(label: str, enabled: bool):
    label = ctx_label(label)
    update = {"poseidon_favorite_enabled": bool(enabled)}
    if mongo_enabled():
        db_upsert_doc("account", label, update)
        return
    save_account_state_update(label, update)


def save_account_state_update(label: str, update: dict):
    label = ctx_label(label)
    try:
        data = {}
        if ACCOUNT_STATE_FILE.exists():
            loaded = json.loads(ACCOUNT_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        state = data.get(label, {})
        if not isinstance(state, dict):
            state = {}
        state.update(update)
        data[label] = state
        ACCOUNT_STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal simpan state akun {label}: {e}")


def save_inventory_slots(label: str, used: int, total: int):
    label = ctx_label(label)
    if mongo_enabled():
        db_upsert_doc("account", label, {
            "inventory_slots_used": int(used or 0),
            "inventory_slots_total": int(total or 0),
        })


async def run_inventory_full_clean(fish_app: Client = None, label: str = "main") -> bool:
    label = ctx_label(label)
    lock = _account_inventory_clean_locks.setdefault(label, asyncio.Lock())
    if lock.locked():
        Log.p("WARN", f"{fish_log_ctx(label)} Inventory clean sedang berjalan di proses lain, tunggu selesai")
        async with lock:
            pass
        return True
        
    async with lock:
        audit_log(label, "inventory_full_clean", "inventory_full", user_id=0)
        await sell_flow(fish_app=fish_app, label=label)
        return True


def is_group_room_mode(label: str = None) -> bool:
    return current_fish_mode(label) == "group_room"


def is_all_mode(label: str = None) -> bool:
    return current_fish_mode(label) == "all"


def is_special_group_mode(label: str = None) -> bool:
    return current_fish_mode(label) == "special_group"


def uses_group_room(label: str = None) -> bool:
    return current_fish_mode(label) in {"group_room", "all", "special_group"}


def fish_group_chat_target(label: str = None):
    targets = fish_group_chat_targets(label)
    return targets[0] if targets else parse_chat_target(FISH_GROUP_CHAT)


