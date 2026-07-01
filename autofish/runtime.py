from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def inc_stat(key: str, amount: int = 1, label: str = None):
    label = ctx_label(label)
    if mongo_enabled():
        try:
            mongo_col.update_one(
                {"type": "stats", "label": label},
                {"$inc": {key: int(amount)}, "$set": {"updated_at": now_wib()}, "$setOnInsert": {"created_at": now_wib()}},
                upsert=True,
            )
            return
        except PyMongoError as e:
            Log.p("WARN", f"Mongo inc stats gagal: {e}")
    with _stats_file_lock:
        stats = load_stats(label)
        stats[key] = int(stats.get(key, 0)) + amount
        save_stats(stats, label=label)


def seconds_since_activity(label: str = "main") -> int | None:
    last_activity = _account_last_activity.get(label) or _last_activity_at
    if not last_activity:
        return None
    return int((now_wib() - last_activity).total_seconds())


def running_labels() -> list[str]:
    return sorted(label for label, running in _account_running.items() if running)


def is_any_running() -> bool:
    return any(_account_running.values())


def set_command_mode(label: str, enabled: bool):
    _account_command_mode[label] = enabled


def is_command_mode(label: str) -> bool:
    return bool(_account_command_mode.get(label, False))


def alloc_handler_group() -> int:
    return next(_handler_group_seq)


def ttl_dict_mark(store: dict, label: str, key: tuple, ttl: float) -> bool:
    label = ctx_label(label)
    now = time.monotonic()
    bucket = store.setdefault(label, {})
    for old_key, expires_at in list(bucket.items()):
        if expires_at <= now:
            bucket.pop(old_key, None)
    if key in bucket:
        return False
    bucket[key] = now + ttl
    return True


def message_event_key(message, event_type: str = "event") -> tuple:
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) or getattr(chat, "username", None) or "unknown"
    msg_id = int(getattr(message, "id", 0) or 0)
    edit_date = getattr(message, "edit_date", None)
    edit_key = int(edit_date.timestamp()) if hasattr(edit_date, "timestamp") else 0
    return (event_type, str(chat_id), msg_id, edit_key)


def mark_event_once(label: str, message, event_type: str = "event", ttl: float = 600) -> bool:
    return ttl_dict_mark(_account_seen_events, label, message_event_key(message, event_type), ttl)


def mark_action_once(label: str, message, action: str, ttl: float = 900) -> bool:
    return ttl_dict_mark(_account_action_guard, label, message_event_key(message, action), ttl)


def private_wait_age(label: str) -> float | None:
    started = _account_private_wait_started.get(ctx_label(label))
    if not started:
        return None
    return max(0.0, time.monotonic() - started)


def clear_private_wait_state(label: str, stale_only: bool = False):
    label = ctx_label(label)
    if stale_only:
        age = private_wait_age(label)
        if age is not None and age < PRIVATE_WAIT_STALE_SECONDS:
            return False
    _account_private_session_waiting.pop(label, None)
    _account_private_wait_started.pop(label, None)
    _account_private_session_active.pop(label, None)
    _account_waiting_confirmation.pop(label, None)
    return True


async def health_watchdog():
    while not _shutdown_event.is_set():
        await asyncio.sleep(60)
        for label, running in list(_account_running.items()):
            label = ctx_label(label)
            if not running:
                continue
            inactive = seconds_since_activity(label)
            if inactive is None or inactive < WATCHDOG_TIMEOUT:
                continue
            mode = current_fish_mode(label)
            fish_app = await account_client_or_none(label)
            if not fish_app:
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog skip: userbot belum siap")
                await log_event("WATCHDOG_WARN", label, "Userbot belum siap, watchdog tidak bisa recovery.")
                touch_activity(action="watchdog client unavailable", label=label)
                continue
            if not getattr(fish_app, "is_connected", False):
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: userbot disconnect, coba recovery")
                recovered = await recover_account_client_connection(fish_app=fish_app, label=label, reason="watchdog disconnected")
                if recovered:
                    fish_app = recovered
            if mode in {"group_room", "all"}:
                if _account_group_active.get(label):
                    Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: grup aktif tapi idle {inactive}s, tunggu loop utama")
                    inc_stat("watchdog_pokes", label=label)
                    touch_activity(action=f"watchdog {mode} active wait", label=label)
                    continue
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: tidak ada aktivitas {inactive}s, paksa cek room/loop ulang")
                inc_stat("watchdog_pokes", label=label)
                await notify(f"⚠️ [{label}] Watchdog: tidak ada aktivitas {inactive}s. Mode {mode} dipaksa cek ulang.", label=label)
                _account_group_active[label] = False
                clear_active_group_chat(label)
                clear_pending_group_join(label)
                touch_activity(action=f"watchdog {mode} reset", label=label)
                continue
            if mode == "private" and _account_private_session_waiting.get(label):
                if clear_private_wait_state(label, stale_only=True):
                    Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: Sesi private wait nyangkut terlalu lama, di-reset.")
                    await notify(f"⚠️ [{label}] Watchdog: Sesi private wait nyangkut terlalu lama, di-reset.", label=label)
                else:
                    Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: sesi private masih menunggu pesan selesai dari bot")
                    inc_stat("watchdog_pokes", label=label)
                    touch_activity(action="watchdog private wait", event="menunggu sesi selesai", label=label)
                    continue

            if _account_waiting_confirmation.get(label):
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog skip: Sedang menunggu konfirmasi /mancing")
                continue

            if _account_private_session_active.get(label):
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog skip: Sesi private sedang berjalan")
                continue

            if label in _account_sell_locks and _account_sell_locks[label].locked():
                Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog skip: Sedang proses sell/inventory clean")
                continue

            Log.p("WARN", f"{fish_log_ctx(label, mode)} Watchdog: tidak ada aktivitas {inactive}s, kirim /mancing ulang")
            inc_stat("watchdog_pokes", label=label)
            await notify(f"⚠️ [{label}] Watchdog: tidak ada aktivitas {inactive}s. Kirim /mancing ulang.", label=label)
            await send_private_mancing(fish_app=fish_app, label=label)
            touch_activity(action="watchdog /mancing", label=label)


async def maintenance_schedule_watchdog():
    while not _shutdown_event.is_set():
        try:
            await apply_maintenance_schedule_once()
        except Exception as e:
            Log.p("WARN", f"Maintenance schedule watchdog error: {e}")
            await send_traceback_log(e, label="main", mode="maintenance_schedule")
        await asyncio.sleep(30)


async def apply_maintenance_schedule_once():
    schedule_enabled, _, _ = maintenance_schedule_settings()
    if not schedule_enabled:
        return
    config = load_maintenance_config()
    active_now, schedule_key = maintenance_schedule_active_now()
    if active_now:
        if str(config.get("schedule_last_start_key", "") or "") == schedule_key:
            return
        save_maintenance_schedule_marker(schedule_last_start_key=schedule_key)
        if not maintenance_enabled():
            resume_labels = await enable_maintenance_runtime(user_id=0, source=f"schedule {schedule_key}")
            save_maintenance_schedule_marker(schedule_active_key=schedule_key)
            await log_event(
                "MAINTENANCE",
                "main",
                f"Maintenance ON otomatis jadwal {schedule_key}.\nResume nanti: {', '.join(resume_labels) or '-'}",
            )
        else:
            save_maintenance_schedule_marker(schedule_active_key=schedule_key)
        return

    active_key = str(config.get("schedule_active_key", "") or "")
    if not active_key:
        return
    if str(config.get("schedule_last_end_key", "") or "") == active_key:
        return
    save_maintenance_schedule_marker(schedule_last_end_key=active_key)
    if maintenance_enabled():
        started, failed = await disable_maintenance_runtime(user_id=0, source=f"schedule {active_key}")
        await log_event(
            "MAINTENANCE",
            "main",
            f"Maintenance OFF otomatis jadwal {active_key}.\nResume: {', '.join(started) or '-'}\nGagal: {', '.join(failed) or '-'}",
        )
    save_maintenance_schedule_marker(schedule_active_key="")


async def ensure_required_channel_joined(fish_app: Client, label: str = "main") -> bool:
    label = ctx_label(label)
    target = REQUIRED_CHANNEL_USERNAME
    if not target or label in _account_required_channel_joined:
        return True
    try:
        await fish_app.join_chat(target)
        _account_required_channel_joined.add(label)
        _account_required_channel_status[label] = "joined"
        Log.p("BOT", f"[{label}] Join channel wajib OK: {target}")
        await log_event("REQUIRED_CHANNEL_JOINED", label, f"Berhasil join channel wajib: {target}")
        return True
    except FloodWait as e:
        wait = int(getattr(e, "value", 5)) + 1
        Log.p("WARN", f"[{label}] FloodWait join channel wajib {wait}s")
        await asyncio.sleep(wait)
        return await ensure_required_channel_joined(fish_app, label=label)
    except Exception as e:
        msg = str(e)
        if "USER_ALREADY_PARTICIPANT" in msg or "already" in msg.lower():
            _account_required_channel_joined.add(label)
            _account_required_channel_status[label] = "already"
            Log.p("BOT", f"[{label}] Sudah join channel wajib: {target}")
            return True
        _account_required_channel_status[label] = "failed"
        Log.p("WARN", f"[{label}] Gagal join channel wajib {target}: {e}")
        await log_event("REQUIRED_CHANNEL_FAIL", label, f"Target: {target}\nError: {msg[:300]}")
        return False


async def account_client_or_none(label: str = "main") -> Client | None:
    label = ctx_label(label)
    client = await start_account_client(label)
    if not client:
        return None
    return client


async def stop_account_loop_runtime(label: str, persist_auto_start: bool = False):
    global _is_running
    label = ctx_label(label)
    _account_running[label] = False
    _account_private_session_active.pop(label, None)
    _account_private_session_waiting.pop(label, None)
    _account_waiting_confirmation.pop(label, None)
    _account_group_active[label] = False
    clear_active_group_chat(label)
    task = _account_tasks.pop(label, None)
    await cancel_task_safely(task, label=label, reason="stop fishing loop")
    boost_task = _account_private_boost_tasks.pop(label, None)
    await cancel_task_safely(boost_task, label=label, reason="stop private boost loop")
    if persist_auto_start:
        save_account_auto_start(label, False)
    Log.p("BOT", f"[{label}] Stop runtime loop | {runtime_state_summary(label)}")
    _is_running = is_any_running()


async def start_account_client(label: str) -> Client | None:
    label = ctx_label(label)
    async with get_lifecycle_lock(label):
        if label in _account_clients:
            client = _account_clients[label]
            if not getattr(client, "is_connected", False):
                Log.p("WARN", f"[{label}] Cached userbot terputus, coba start ulang")
                try:
                    await client.start()
                except Exception as e:
                    Log.p("WARN", f"[{label}] Start ulang cached userbot gagal: {e}")
                    remove_private_captcha_watcher(label, client)
                    remove_user_media_log_watcher(label, client)
                    _account_clients.pop(label, None)
                    try:
                        await client.stop()
                    except Exception:
                        pass
                    client = None
            if client is not None:
                ensure_private_captcha_watcher(label, client)
                ensure_user_media_log_watcher(label, client)
                return client

        try:
            account = load_account(label)
            if account.get("restored_needs_login"):
                Log.p("WARN", f"[{label}] Akun hasil restore perlu login userbot ulang sebelum bisa start")
                await log_error_event_once(
                    "USERBOT_LOGIN_REQUIRED",
                    label,
                    "Akun hasil restore perlu login userbot ulang sebelum bisa start.",
                    section="start_account_client",
                    fingerprint="restored_needs_login",
                )
                return None
            session_name = account.get("session_name") or ("fishbot_session" if label == "main" else f"fishbot_session_{label}")
            client = app if label == "main" else Client(
                session_name,
                api_id=API_ID,
                api_hash=API_HASH,
                device_model=PYRO_DEVICE_MODEL,
                system_version=PYRO_SYSTEM_VERSION,
                app_version=PYRO_APP_VERSION,
                workdir=BASE_DIR,
                sleep_threshold=60,
            )
            if label == "main":
                if not session_files_for_name(session_name)[0].exists():
                    Log.p("WARN", "[main] Session belum ada, perlu login userbot")
                    await log_error_event_once(
                        "USERBOT_LOGIN_REQUIRED",
                        label,
                        f"Session belum ada: {session_name}. Perlu login userbot.",
                        section="start_account_client",
                        fingerprint="main_session_missing",
                    )
                    return None
                if not getattr(client, "is_connected", False):
                    await client.start()
                me = await client.get_me()
                set_main_premium_status_from_user(me, label)
                Log.p("STARTUP", f"✅ [{label}] Userbot: {me.first_name} (@{me.username})")
            else:
                await client.start()
                me = await client.get_me()
                Log.p("STARTUP", f"✅ [{label}] Userbot: {me.first_name} (@{me.username})")
            _account_clients[label] = client
            ensure_private_captcha_watcher(label, client)
            ensure_user_media_log_watcher(label, client)
            _account_running.setdefault(label, False)
            if account.get("last_login_error"):
                if mongo_enabled():
                    db_upsert_doc("account", label, {"last_login_error": ""})
                else:
                    save_account_state_update(label, {"last_login_error": ""})
            return client
        except Exception as e:
            login_error = str(e)[:300]
            if mongo_enabled():
                db_upsert_doc("account", label, {"last_login_error": login_error})
            else:
                save_account_state_update(label, {"last_login_error": login_error})
            Log.p("ERROR", f"[{label}] Gagal start account client: {e}")
            if is_login_required_error(e):
                await log_error_event_once(
                    "USERBOT_LOGIN_REQUIRED",
                    label,
                    f"Gagal start userbot, kemungkinan session expired/perlu login ulang.\nError: {login_error}",
                    section="start_account_client",
                    fingerprint="login_required",
                )
            else:
                await log_error_event_once(
                    "USERBOT_START_FAIL",
                    label,
                    f"Gagal start userbot.\nError: {login_error}",
                    section="start_account_client",
                    fingerprint=type(e).__name__,
                )
            await notify(f"❌ [{label}] Gagal start account client: {e}")
            return None


async def start_account_loop(label: str, client: Client):
    global _is_running
    if maintenance_blocks_account(label):
        Log.p("WARN", f"[{ctx_label(label)}] Start loop dibatalkan: maintenance aktif")
        return
    if _account_running.get(label):
        ensure_private_captcha_watcher(label, client)
        return
    ensure_private_captcha_watcher(label, client)
    save_account_auto_start(label, True)
    _account_running[label] = True
    _is_running = True
    Log.p("BOT", f"[{label}] Start runtime loop | {runtime_state_summary(label)}")
    task = asyncio.create_task(fishing_loop(fish_app=client, label=label))
    _account_tasks[label] = task
    boost_task = _account_private_boost_tasks.get(label)
    if not boost_task or boost_task.done():
        _account_private_boost_tasks[label] = asyncio.create_task(private_boost_loop(fish_app=client, label=label))


async def start_all_accounts(auto_start_only: bool = False):
    if maintenance_enabled():
        Log.p("STARTUP", "Auto-start/Start semua dilewati: maintenance aktif")
        return
    _shutdown_event.clear()
    recovered = []
    skipped_login = []
    skipped_disabled = []
    for label in configured_account_labels(enabled_only=True):
        account = load_account(label)
        if not account.get("enabled", True):
            skipped_disabled.append(label)
            continue
        if auto_start_only and not account.get("auto_start", False):
            continue
        if account.get("restored_needs_login") or account.get("last_login_error"):
            skipped_login.append(label)
            Log.p("WARN", f"[{label}] Skip auto-start: perlu login Telegram ulang")
            reason = "restored_needs_login" if account.get("restored_needs_login") else str(account.get("last_login_error", ""))[:300]
            await log_error_event_once(
                "USERBOT_LOGIN_REQUIRED",
                label,
                f"Skip auto-start: perlu login Telegram ulang.\nReason: {reason}",
                section="start_all_accounts",
                fingerprint="auto_start_login_required",
            )
            continue
        client = await start_account_client(label)
        if client:
            await start_account_loop(label, client)
            recovered.append(label)
            if auto_start_only:
                Log.p("STARTUP", f"[{label}] Auto-start recovery OK")
        else:
            skipped_login.append(label)

    if auto_start_only and recovered:
        Log.p("STARTUP", f"Auto-start recovered: {', '.join(account_names_for_labels(recovered))}")
    if auto_start_only and skipped_login:
        Log.p("WARN", f"Skip auto-start (belum/gagal login): {', '.join(account_names_for_labels(skipped_login))}")
    if auto_start_only and skipped_disabled:
        Log.p("WARN", f"Skip auto-start disabled: {', '.join(account_names_for_labels(skipped_disabled))}")


async def start_account_labels(labels: list[str]) -> tuple[list[str], list[str]]:
    _shutdown_event.clear()
    started = []
    failed = []
    for raw_label in labels:
        label = ctx_label(raw_label)
        account = load_account(label)
        if not account.get("enabled", True):
            failed.append(f"{label} disabled")
            continue
        if account.get("restored_needs_login") or account.get("last_login_error") or not account_doc_exists(label):
            failed.append(f"{label} perlu login")
            continue
        client = await start_account_client(label)
        if client:
            await start_account_loop(label, client)
            started.append(label)
        else:
            failed.append(f"{label} gagal start")
    return started, failed


async def enable_maintenance_runtime(user_id: int = 0, source: str = "manual") -> list[str]:
    resume_labels = running_labels()
    save_maintenance_enabled(True, user_id=user_id, resume_labels=resume_labels)
    await stop_all_accounts(persist_auto_start=False)
    Log.p("BOT", f"Maintenance ON oleh {source}; resume nanti: {', '.join(resume_labels) or '-'}")
    return resume_labels


async def disable_maintenance_runtime(user_id: int = 0, source: str = "manual") -> tuple[list[str], list[str]]:
    resume_labels = maintenance_resume_labels()
    save_maintenance_enabled(False, user_id=user_id)
    started, failed = await start_account_labels(resume_labels)
    clear_maintenance_resume_labels(user_id=user_id)
    Log.p("BOT", f"Maintenance OFF oleh {source}; resume={', '.join(started) or '-'}; gagal={', '.join(failed) or '-'}")
    return started, failed


async def stop_all_accounts(persist_auto_start: bool = False):
    global _is_running
    for label in list(_account_running.keys()):
        await stop_account_loop_runtime(label, persist_auto_start=persist_auto_start)
    _is_running = False


async def stop_account_clients():
    for label, client in list(_account_clients.items()):
        if label == "main":
            continue
        await stop_account_client(label)


