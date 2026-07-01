from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def backup_account_doc(account: dict) -> dict:
    doc = json_safe(account)
    doc.pop("_id", None)
    doc.pop("created_at", None)
    doc.pop("updated_at", None)
    if doc.get("label") != "main":
        doc["enabled"] = False
        doc["auto_start"] = False
        doc["restored_needs_login"] = True
    return doc


def full_backup_file_specs() -> list[tuple[Path, str]]:
    return [
        (ENV_FILE, f"{BACKUP_FILES_DIR}/.env"),
        (RULES_FILE, f"{BACKUP_FILES_DIR}/{RULES_FILE.name}"),
        (STATS_FILE, f"{BACKUP_FILES_DIR}/{STATS_FILE.name}"),
        (ADMINS_FILE, f"{BACKUP_FILES_DIR}/{ADMINS_FILE.name}"),
        (MODE_FILE, f"{BACKUP_FILES_DIR}/{MODE_FILE.name}"),
        (MAINTENANCE_FILE, f"{BACKUP_FILES_DIR}/{MAINTENANCE_FILE.name}"),
        (GROUPS_FILE, f"{BACKUP_FILES_DIR}/{GROUPS_FILE.name}"),
        (SPECIAL_GROUP_FILE, f"{BACKUP_FILES_DIR}/{SPECIAL_GROUP_FILE.name}"),
        (ACCOUNT_STATE_FILE, f"{BACKUP_FILES_DIR}/{ACCOUNT_STATE_FILE.name}"),
        (BROADCAST_USERS_FILE, f"{BACKUP_FILES_DIR}/{BROADCAST_USERS_FILE.name}"),
        (BROADCAST_MESSAGES_FILE, f"{BACKUP_FILES_DIR}/{BROADCAST_MESSAGES_FILE.name}"),
        (DAILY_BROADCAST_FILE, f"{BACKUP_FILES_DIR}/{DAILY_BROADCAST_FILE.name}"),
        (RESTART_FLAG_FILE, f"{BACKUP_FILES_DIR}/{RESTART_FLAG_FILE.name}"),
    ]


def collect_backup_session_names() -> list[str]:
    names: list[str] = []
    seen = set()
    for account in load_all_accounts():
        session_name = str(account.get("session_name") or "").strip()
        if not session_name:
            continue
        if session_name in seen:
            continue
        seen.add(session_name)
        names.append(session_name)
    if "fishbot_session" not in seen:
        names.insert(0, "fishbot_session")
    return names


def collect_backup_session_paths() -> list[Path]:
    paths: list[Path] = []
    seen = set()
    for session_name in collect_backup_session_names():
        for path in session_files_for_name(session_name):
            if path in seen:
                continue
            seen.add(path)
            if path.exists() and path.is_file():
                paths.append(path)
    return paths


def create_backup_payload() -> tuple[dict, dict]:
    accounts = [backup_account_doc(account) for account in load_all_accounts()]
    labels = sorted({account.get("label", "main") for account in accounts})

    if mongo_enabled():
        rules = []
        stats = []
        configs = []
    else:
        rules_data = load_json_file(RULES_FILE, {"keep": [], "sell": []})
        stats_data = load_json_file(STATS_FILE, {})
        groups_data = load_json_file(GROUPS_FILE, {"groups": []})
        mode_data = load_json_file(MODE_FILE, {})
        special_group_data = load_json_file(SPECIAL_GROUP_FILE, {"special_group": ""})
        account_state_data = load_json_file(ACCOUNT_STATE_FILE, {})
        rules = [{"type": "rules", "label": "main", **rules_data}]
        stats = [{"type": "stats", "label": "main", **stats_data}] if stats_data else []
        configs = [
            {"type": "config", "label": "admins", "admins": sorted(load_admin_ids())},
            {"type": "config", "label": "groups_file", **groups_data},
            {"type": "config", "label": "mode_file", **mode_data},
            {"type": "config", "label": "special_group_file", **special_group_data},
            {"type": "config", "label": "account_state_file", "state": account_state_data},
        ]

    payload = {
        "schema": FULL_BACKUP_SCHEMA,
        "version": BACKUP_SCHEMA_VERSION,
        "created_at": now_wib().isoformat(),
        "source": {
            "mongo": mongo_enabled(),
            "db": MONGO_DB if mongo_enabled() else None,
            "collection": MONGO_COLLECTION if mongo_enabled() else None,
        },
        "data": {
            "accounts": accounts,
            "rules": rules,
            "stats": stats,
            "configs": configs,
            "gallery": [],
        },
        "files": [arcname for source_path, arcname in full_backup_file_specs() if source_path.exists() and source_path.is_file()],
        "sessions": [path.name for path in collect_backup_session_paths()],
        "notes": "Full backup includes local config, session files, and .env only.",
    }
    summary = {
        "files": len(payload["files"]),
        "sessions": len(payload["sessions"]),
        "accounts": len(accounts),
        "rules": len(rules),
        "stats": len(stats),
        "configs": len(configs),
        "labels": len(labels),
    }
    return payload, summary


def write_backup_file(payload: dict) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_wib().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"fishit_backup_{ts}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(BACKUP_MANIFEST_NAME, json.dumps(payload, indent=2, ensure_ascii=False))
        for source_path, arcname in full_backup_file_specs():
            if source_path.exists() and source_path.is_file():
                zf.write(source_path, arcname)
        for session_path in collect_backup_session_paths():
            zf.write(session_path, f"{BACKUP_SESSIONS_DIR}/{session_path.name}")
    return path


async def send_backup_file(chat_id: int, path: Path, summary: dict, context: ContextTypes.DEFAULT_TYPE):
    size_kb = path.stat().st_size / 1024
    caption = (
        "✅ <b>Full Backup selesai</b>\n\n"
        + expandable_blockquote(
            f"File: {path.name}\n"
            f"Files: {summary.get('files', 0)}\n"
            f"Sessions: {summary.get('sessions', 0)}\n"
            f"Ukuran: {size_kb:.1f} KB\n\n"
            "Bundle ini mencakup config lokal, .env, dan session. Mongo dan gallery tidak ikut."
        )
    )
    with path.open("rb") as fh:
        await context.bot.send_document(
            chat_id=chat_id,
            document=fh,
            filename=path.name,
            caption=caption,
            parse_mode="HTML",
            reply_markup=back_keyboard("owner:backup"),
        )


def validate_backup_payload(payload: dict) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "File backup bukan JSON object."
    if payload.get("schema") not in {"fishit_backup", FULL_BACKUP_SCHEMA}:
        return False, "Schema backup tidak dikenal."
    if int(payload.get("version", 0) or 0) > BACKUP_SCHEMA_VERSION:
        return False, "Versi backup lebih baru dari kode bot ini."
    data = payload.get("data")
    if not isinstance(data, dict):
        return False, "Data backup kosong atau rusak."
    for key in ("accounts", "rules", "configs"):
        if not isinstance(data.get(key, []), list):
            return False, f"Data {key} tidak valid."
    return True, "OK"


def _safe_extract_zip_member(zip_file: zipfile.ZipFile, member: zipfile.ZipInfo, dest_dir: Path) -> Path:
    dest_path = (dest_dir / member.filename).resolve()
    if dest_dir.resolve() not in dest_path.parents and dest_path != dest_dir.resolve():
        raise ValueError(f"Zip entry path tidak aman: {member.filename}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with zip_file.open(member) as src, dest_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return dest_path


def _restore_full_backup_bundle(archive_path: Path) -> dict:
    extracted_dir = BACKUP_DIR / f"restore_extract_{now_wib().strftime('%Y%m%d_%H%M%S_%f')}"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            manifest_member = zf.getinfo(BACKUP_MANIFEST_NAME)
            _safe_extract_zip_member(zf, manifest_member, extracted_dir)
            for member in zf.infolist():
                if member.filename == BACKUP_MANIFEST_NAME or member.is_dir():
                    continue
                _safe_extract_zip_member(zf, member, extracted_dir)

        manifest_path = extracted_dir / BACKUP_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        ok, msg = validate_backup_payload(payload)
        if not ok:
            raise ValueError(msg)

        restored = {"files": 0, "sessions": 0, "mongo_docs": 0}
        for source_path, arcname in full_backup_file_specs():
            extracted = extracted_dir / arcname
            if extracted.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(extracted, source_path)
                restored["files"] += 1

        for session_name in collect_backup_session_names():
            for relative in session_files_for_name(session_name):
                extracted = extracted_dir / f"{BACKUP_SESSIONS_DIR}/{relative.name}"
                if extracted.exists():
                    relative.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(extracted, relative)
                    restored["sessions"] += 1
        return restored
    finally:
        try:
            shutil.rmtree(extracted_dir, ignore_errors=True)
        except Exception:
            pass


def restore_backup_payload(payload: dict) -> dict:
    ok, msg = validate_backup_payload(payload)
    if not ok:
        raise ValueError(msg)

    data = payload.get("data", {})
    accounts = [json_safe(x) for x in data.get("accounts", []) if isinstance(x, dict)]
    rules = [json_safe(x) for x in data.get("rules", []) if isinstance(x, dict)]
    stats = [json_safe(x) for x in data.get("stats", []) if isinstance(x, dict)]
    configs = [json_safe(x) for x in data.get("configs", []) if isinstance(x, dict)]
    gallery = [json_safe(x) for x in data.get("gallery", []) if isinstance(x, dict)]

    restored = {"accounts": 0, "rules": 0, "stats": 0, "configs": 0, "gallery": 0}

    if mongo_enabled():
        for account in accounts:
            label = safe_label(account.get("label", "main"))
            update = {k: v for k, v in account.items() if k not in {"_id", "type", "label", "created_at", "updated_at"}}
            if label != "main":
                update["enabled"] = False
                update["auto_start"] = False
                update["restored_needs_login"] = True
            db_upsert_doc("account", label, update)
            restored["accounts"] += 1

        for doc in rules:
            label = safe_label(doc.get("label", "main"))
            update = {k: v for k, v in doc.items() if k not in {"_id", "type", "label", "created_at", "updated_at"}}
            db_upsert_doc("rules", label, update)
            restored["rules"] += 1

        for doc in stats:
            label = safe_label(doc.get("label", "main"))
            update = {k: int(v) for k, v in doc.items() if k not in {"_id", "type", "label", "created_at", "updated_at"} and isinstance(v, (int, float, str)) and str(v).lstrip("-").isdigit()}
            if update:
                db_upsert_doc("stats", label, update)
                restored["stats"] += 1

        for doc in configs:
            label = str(doc.get("label", "")).strip() or "config"
            update = {k: v for k, v in doc.items() if k not in {"_id", "type", "label", "created_at", "updated_at"}}
            db_upsert_doc("config", label, update)
            restored["configs"] += 1
        if gallery:
            docs = []
            for doc in gallery:
                clean = {k: v for k, v in doc.items() if k != "_id"}
                clean["type"] = "rare_gallery"
                clean["label"] = safe_label(clean.get("label", "main"))
                docs.append(clean)
            try:
                mongo_col.delete_many({"type": "rare_gallery"})
                mongo_col.insert_many(docs)
                restored["gallery"] = len(docs)
            except PyMongoError as e:
                Log.p("WARN", f"Mongo restore gallery gagal: {e}")
    else:
        first_rules = next((doc for doc in rules if doc.get("label", "main") == "main"), None)
        if first_rules:
            save_fish_rules({"keep": first_rules.get("keep", []), "sell": first_rules.get("sell", [])}, label="main")
            restored["rules"] = 1
        for doc in configs:
            if doc.get("label") == "admins":
                save_admin_ids({int(x) for x in doc.get("admins", []) if str(x).isdigit()})
                restored["configs"] += 1
            elif doc.get("label") == "groups_file":
                save_extra_group_chats(doc.get("groups", []), label="main")
                restored["configs"] += 1
            elif doc.get("label") == "mode_file" and doc.get("mode") in VALID_FISH_MODES:
                save_runtime_mode(doc.get("mode"), label="main")
                restored["configs"] += 1
            elif doc.get("label") == "special_group_file":
                save_special_group_chat(doc.get("special_group", ""), label="main")
                restored["configs"] += 1
            elif doc.get("label") == "account_state_file" and isinstance(doc.get("state"), dict):
                ACCOUNT_STATE_FILE.write_text(json.dumps(doc.get("state", {}), indent=2, ensure_ascii=False), encoding="utf-8")
                restored["configs"] += 1
        first_stats = next((doc for doc in stats if doc.get("label", "main") == "main"), None)
        if first_stats:
            save_stats({k: v for k, v in first_stats.items() if k not in {"type", "label"}}, label="main")
            restored["stats"] = 1
        if gallery:
            RARE_GALLERY_FILE.write_text(
                json.dumps({"items": gallery[-RARE_GALLERY_LIMIT:]}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            restored["gallery"] = min(len(gallery), RARE_GALLERY_LIMIT)

    return restored


