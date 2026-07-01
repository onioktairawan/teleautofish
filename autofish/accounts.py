from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def ctx_label(label: str = None) -> str:
    return (label or _current_account_label.get() or "main").strip() or "main"


def safe_label(label: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (label or "").strip().lower())
    return label or "main"


def load_account_state(label: str = "main") -> dict:
    label = safe_label(label)
    if not ACCOUNT_STATE_FILE.exists():
        return {}
    try:
        data = json.loads(ACCOUNT_STATE_FILE.read_text(encoding="utf-8"))
        state = data.get(label, {})
        return state if isinstance(state, dict) else {}
    except Exception as e:
        Log.p("WARN", f"Gagal baca fish_account_state.json: {e}")
        return {}


def default_account_doc(label: str = "main") -> dict:
    label = safe_label(label)
    doc = {
        "type": "account",
        "label": label,
        "session_name": "fishbot_session" if label == "main" else f"fishbot_session_{label}",
        "owner_ids": [OWNER_ID],
        "enabled": True,
        "auto_start": AUTO_START_FISHING if label == "main" else False,
        "mode": FISH_MODE if FISH_MODE in VALID_FISH_MODES else "private",
        "groups": split_chat_targets(FISH_GROUP_CHAT) if label == "main" else [],
        "special_group": "",
        "special_auto_open": True,
        "special_auto_boost": True,
        "private_auto_boost": True,
        "private_boost_paused": False,
        "private_bot_username": "",
        "verification_required": False,
        "verification_url": "",
        "verification_message": "",
        "verification_detected_at": "",
        "poseidon_favorite_enabled": True,
        "special_open_delay_min": int(SPECIAL_OPEN_DELAY_MIN),
        "special_open_delay_max": int(SPECIAL_OPEN_DELAY_MAX),
        "inventory_slots_used": 0,
        "inventory_slots_total": 0,
        "last_login_error": "",
        "created_at": now_wib(),
        "updated_at": now_wib(),
    }
    state = load_account_state(label)
    if "auto_start" in state:
        doc["auto_start"] = bool(state.get("auto_start"))
    for key in ("last_login_error", "private_auto_boost", "private_boost_paused", "private_bot_username", "verification_required", "verification_url", "verification_message", "verification_detected_at", "poseidon_favorite_enabled"):
        if key in state:
            doc[key] = state.get(key)
    return doc


def db_get_doc(doc_type: str, label: str = "main") -> dict | None:
    if not mongo_enabled():
        return None
    try:
        return mongo_col.find_one({"type": doc_type, "label": ctx_label(label)})
    except PyMongoError as e:
        Log.p("WARN", f"Mongo read {doc_type}/{label} gagal: {e}")
        return None


def db_upsert_doc(doc_type: str, label: str, update: dict) -> dict | None:
    if not mongo_enabled():
        return None
    now = now_wib()
    payload = {"$set": {**update, "updated_at": now}, "$setOnInsert": {"type": doc_type, "label": ctx_label(label), "created_at": now}}
    try:
        result = mongo_col.find_one_and_update(
            {"type": doc_type, "label": ctx_label(label)},
            payload,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc_type == "account":
            invalidate_accounts_cache()
        if doc_type == "config" and ctx_label(label) == "admins":
            invalidate_admin_cache()
        return result
    except PyMongoError as e:
        Log.p("WARN", f"Mongo upsert {doc_type}/{label} gagal: {e}")
        return None


def db_delete_docs(query: dict) -> int:
    if not mongo_enabled():
        return 0
    try:
        result = mongo_col.delete_many(query)
        if query.get("type") == "account":
            invalidate_accounts_cache()
        return int(result.deleted_count or 0)
    except PyMongoError as e:
        Log.p("WARN", f"Mongo delete gagal: {e}")
        return 0


def ensure_default_account() -> dict:
    if not mongo_enabled():
        return default_account_doc("main")
    existing = db_get_doc("account", "main")
    if existing:
        return existing
    doc = default_account_doc("main")
    db_upsert_doc("account", "main", {k: v for k, v in doc.items() if k not in {"type", "label", "created_at"}})
    return db_get_doc("account", "main") or doc


def load_account(label: str = "main") -> dict:
    label = ctx_label(label)
    if mongo_enabled():
        doc = db_get_doc("account", label)
        if doc:
            return doc
        if label == "main":
            return ensure_default_account()
    return default_account_doc(label)


def load_accounts_for_user(user_id: int) -> list[dict]:
    user_id = int(user_id or 0)
    if mongo_enabled():
        try:
            if user_id == OWNER_ID:
                docs = list(mongo_col.find({"type": "account"}).sort("label", 1))
            else:
                docs = list(mongo_col.find({"type": "account", "owner_ids": user_id}).sort("label", 1))
            if docs:
                return docs
        except PyMongoError as e:
            Log.p("WARN", f"Mongo list account gagal: {e}")
    return [default_account_doc("main")] if user_id == OWNER_ID else []


def load_all_accounts() -> list[dict]:
    global _all_accounts_cache, _all_accounts_cache_ts
    now = time.monotonic()
    if _all_accounts_cache and (now - _all_accounts_cache_ts) < _ALL_ACCOUNTS_CACHE_TTL:
        return [doc.copy() for doc in _all_accounts_cache]

    if mongo_enabled():
        ensure_default_account()
        try:
            result = list(mongo_col.find({"type": "account"}).sort("label", 1))
        except PyMongoError as e:
            Log.p("WARN", f"Mongo list semua account gagal: {e}")
            result = [doc.copy() for doc in _all_accounts_cache] or [default_account_doc("main")]
    else:
        result = [default_account_doc("main")]

    _all_accounts_cache = [doc.copy() for doc in result]
    _all_accounts_cache_ts = now
    return [doc.copy() for doc in result]


def configured_account_labels(enabled_only: bool = True) -> list[str]:
    if mongo_enabled():
        ensure_default_account()
        try:
            query = {"type": "account"}
            if enabled_only:
                query["enabled"] = True
            labels = [doc["label"] for doc in mongo_col.find(query, {"label": 1}).sort("label", 1)]
            return labels or ["main"]
        except PyMongoError as e:
            Log.p("WARN", f"Mongo account labels gagal: {e}")
    return ["main"]


