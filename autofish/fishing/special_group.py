from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def wait_for_special_room_seen(target, timeout: float, fish_app: Client = None, label: str = "main"):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu room special")
    if not fish_app:
        return None
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()

    async def _handler(client, message):
        if is_command_mode(label) or result_queue.full():
            return
        text = message.text or message.caption or ""
        if message.chat:
            observe_special_boost_message(message.chat.id, text, label=label)
        if is_special_group_active_text(text):
            await result_queue.put(message)
            return
        if not message.reply_markup or not is_group_room_message(message):
            return
        for row in (message.reply_markup.inline_keyboard or []):
            for btn in row:
                if "daftar mancing" in normalize_button_text(btn.text or ""):
                    await result_queue.put(message)
                    return

    handler = MessageHandler(_handler, filters.chat(target) & filters.incoming)
    fish_app.add_handler(handler, group=handler_group)
    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        safe_remove_handler(handler, group=handler_group, fish_app=fish_app)


def special_open_command() -> str:
    username = FISH_BOT_USERNAME.lstrip("@")
    return f"/open_mancing@{username}" if username else "/open_mancing"


def special_boost_command() -> str:
    username = FISH_BOT_USERNAME.lstrip("@")
    return f"/boost_grup@{username}" if username else "/boost_grup"


def is_special_boost_expired_text(text: str) -> bool:
    tl = normalize_fish_name(text)
    return "boost grup berakhir" in tl and "boost_grup" in tl


def is_special_boost_active_text(text: str) -> bool:
    tl = normalize_fish_name(text)
    return (
        "boost grup aktif" in tl
        or "boost sudah aktif" in tl
        or ("contributors" in tl and "trisula fragment" in tl)
    )


def special_group_write_block_key(target, label: str) -> tuple[str, str]:
    return special_group_key(target), ctx_label(label)


def special_group_write_block_reason(target, label: str) -> str:
    key = special_group_write_block_key(target, label)
    until = _special_group_write_blocked_until.get(key, 0.0)
    if until != float("inf") and time.monotonic() >= until:
        return ""
    return _special_group_write_blocked_reason.get(key, "tidak bisa kirim pesan ke grup")


def is_special_group_write_blocked(target, label: str) -> bool:
    return bool(special_group_write_block_reason(target, label))


def is_group_write_restricted_error(error: Exception | str) -> bool:
    text = str(error or "").lower()
    markers = [
        "chat_write_forbidden",
        "chat_send_messages_forbidden",
        "user_banned_in_channel",
        "user_restricted",
        "forbidden",
        "banned",
        "restricted",
        "muted",
        "can't write",
        "cannot write",
        "not enough rights",
        "you don't have rights",
    ]
    return any(marker in text for marker in markers)


def mark_special_group_write_blocked(target, label: str, reason: str):
    key = special_group_write_block_key(target, label)
    clean_reason = (reason or "tidak bisa kirim pesan ke grup").replace("\n", " ")[:200]
    stage = _special_group_write_blocked_stage.get(key, -1) + 1
    _special_group_write_blocked_stage[key] = stage
    if stage < len(SPECIAL_GROUP_WRITE_BLOCK_RETRY_DELAYS):
        delay = SPECIAL_GROUP_WRITE_BLOCK_RETRY_DELAYS[stage]
        _special_group_write_blocked_until[key] = time.monotonic() + delay
        delay_minutes = max(1, delay // 60)
        if delay_minutes >= 1440:
            retry_text = f"cek lagi dalam {delay_minutes // 1440} hari"
        elif delay_minutes >= 60:
            retry_text = f"cek lagi dalam {delay_minutes // 60} jam"
        else:
            retry_text = f"cek lagi dalam {delay_minutes} menit"
    else:
        _special_group_write_blocked_until[key] = float("inf")
        retry_text = "tidak dipilih lagi sampai bot restart/status dibersihkan"
    _special_group_write_blocked_reason[key] = f"{clean_reason}; {retry_text}"
    Log.p("WARN", f"[{ctx_label(label)}] Skip tugas grup khusus: {_special_group_write_blocked_reason[key]}")


def clear_special_group_write_blocked(target, label: str):
    key = special_group_write_block_key(target, label)
    _special_group_write_blocked_until.pop(key, None)
    _special_group_write_blocked_reason.pop(key, None)
    _special_group_write_blocked_stage.pop(key, None)


async def send_special_group_command(target, command: str, fish_app: Client, label: str, action: str) -> bool:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action=action)
    if not fish_app:
        return False
    if is_special_group_write_blocked(target, label):
        Log.p("WARN", f"[{label}] Skip {action}: {special_group_write_block_reason(target, label)}")
        return False
    try:
        await fish_app.send_message(target, command)
        clear_special_group_write_blocked(target, label)
        touch_activity(action=action, label=label)
        return True
    except FloodWait as e:
        wait = int(getattr(e, "value", 5)) + 1
        Log.p("WARN", f"[{label}] FloodWait {wait}s saat {action}, tunggu...")
        await asyncio.sleep(wait)
        try:
            await fish_app.send_message(target, command)
            clear_special_group_write_blocked(target, label)
            touch_activity(action=action, label=label)
            return True
        except Exception as e2:
            if is_group_write_restricted_error(e2):
                mark_special_group_write_blocked(target, label, f"{action} gagal: {e2}")
            else:
                Log.p("WARN", f"[{label}] {action} gagal setelah FloodWait: {e2}")
            return False
    except Exception as e:
        if is_group_write_restricted_error(e):
            mark_special_group_write_blocked(target, label, f"{action} gagal: {e}")
        else:
            Log.p("WARN", f"[{label}] {action} gagal: {e}")
        return False


def choose_special_group_opener(target, excluded_labels: set[str] = None) -> tuple[str | None, Client | None]:
    excluded_labels = {ctx_label(label) for label in (excluded_labels or set())}
    candidates: list[tuple[str, Client]] = []
    for account in load_all_accounts():
        label = safe_label(account.get("label", "main"))
        if label in excluded_labels:
            continue
        if current_fish_mode(label) != "special_group":
            continue
        if str(special_group_chat_target(label)) != str(target):
            continue
        if not special_auto_open_enabled(label):
            continue
        if not _account_running.get(label):
            continue
        if is_special_group_write_blocked(target, label):
            continue
        client = _account_clients.get(label)
        if not client:
            continue
        if is_command_mode(label) or _account_group_active.get(label):
            continue
        sell_lock = _account_sell_locks.get(label)
        if sell_lock and sell_lock.locked():
            continue
        candidates.append((label, client))
    return random.choice(candidates) if candidates else (None, None)


def special_group_key(target) -> str:
    return str(target or "")


def expected_special_group_labels(target) -> list[str]:
    labels = []
    for account in load_all_accounts():
        label = safe_label(account.get("label", "main"))
        if current_fish_mode(label) != "special_group":
            continue
        if str(special_group_chat_target(label)) != str(target):
            continue
        if not _account_running.get(label):
            continue
        labels.append(label)
    return sorted(labels)


def active_special_group_labels(target) -> list[str]:
    labels = []
    for label in expected_special_group_labels(target):
        if not _account_running.get(label):
            continue
        if label not in _account_clients:
            continue
        if is_command_mode(label):
            continue
        if is_special_group_write_blocked(target, label):
            continue
        if not special_auto_boost_enabled(label):
            continue
        labels.append(label)
    return labels


async def special_group_has_recent_boost_active(target, fish_app: Client, label: str = "main", limit: int = 15) -> bool:
    try:
        async for message in fish_app.get_chat_history(target, limit=limit):
            text = message.text or message.caption or ""
            if is_special_boost_active_text(text):
                Log.p("FISH", f"{fish_log_ctx(label)} Boost grup sudah aktif dari history")
                return True
            if is_special_boost_expired_text(text):
                return False
    except Exception as e:
        Log.p("WARN", f"{fish_log_ctx(label)} Gagal cek history boost grup khusus: {e}")
    return False


async def run_special_boost_sequence(target, trigger_label: str):
    key = special_group_key(target)
    event = _special_boost_active_events.setdefault(key, asyncio.Event())
    event.clear()
    try:
        initial_delay = random.uniform(SPECIAL_BOOST_INITIAL_DELAY_MIN, SPECIAL_BOOST_INITIAL_DELAY_MAX)
        Log.p("FISH", f"[{trigger_label}] Boost grup berakhir, tunggu {initial_delay:.1f}s sebelum boost")
        await asyncio.sleep(initial_delay)

        labels = active_special_group_labels(target)
        random.shuffle(labels)
        if not labels:
            Log.p("WARN", f"[{trigger_label}] Tidak ada userbot aktif untuk boost grup khusus")
            return

        first_client = _account_clients.get(labels[0])
        if first_client and await special_group_has_recent_boost_active(target, first_client, label=labels[0]):
            event.set()
            Log.p("FISH", f"[{trigger_label}] Boost sudah aktif, sequence boost batal")
            return

        for index, boost_label in enumerate(labels, start=1):
            if event.is_set():
                Log.p("FISH", f"[{boost_label}] Boost grup sudah aktif, stop sequence")
                return
            client = _account_clients.get(boost_label)
            if client and await special_group_has_recent_boost_active(target, client, label=boost_label, limit=6):
                event.set()
                Log.p("FISH", f"[{boost_label}] Boost sudah aktif, sequence boost dihentikan")
                return
            if not _account_running.get(boost_label):
                Log.p("FISH", f"[{boost_label}] Skip boost, loop sudah stop")
                continue
            if not client:
                Log.p("WARN", f"[{boost_label}] Skip boost, client tidak aktif")
                continue
            if is_special_group_write_blocked(target, boost_label):
                Log.p("WARN", f"[{boost_label}] Skip boost, {special_group_write_block_reason(target, boost_label)}")
                continue

            sent = await send_special_group_command(
                target,
                special_boost_command(),
                fish_app=client,
                label=boost_label,
                action="boost grup khusus",
            )
            if sent:
                Log.p("FISH", f"[{boost_label}] Kirim boost grup khusus ({index}/{len(labels)})")
            else:
                Log.p("WARN", f"[{boost_label}] Gagal kirim boost grup khusus")

            if event.is_set():
                return
            if index < len(labels):
                await asyncio.sleep(random.uniform(SPECIAL_BOOST_USER_DELAY_MIN, SPECIAL_BOOST_USER_DELAY_MAX))
    finally:
        _special_boost_tasks.pop(key, None)


def observe_special_boost_message(target, text: str, label: str = "main"):
    if not target:
        return
    if not special_auto_boost_enabled(label):
        return
    key = special_group_key(target)
    if is_special_boost_active_text(text):
        event = _special_boost_active_events.setdefault(key, asyncio.Event())
        already_active = event.is_set()
        event.set()
        if not already_active:
            Log.p("FISH", f"{fish_log_ctx(label)} Boost grup aktif terdeteksi, stop boost tambahan")
        return
    if not is_special_boost_expired_text(text):
        return
    task = _special_boost_tasks.get(key)
    if task and not task.done():
        Log.p("FISH", f"{fish_log_ctx(label)} Sequence boost grup sudah berjalan")
        return
    _special_boost_tasks[key] = asyncio.create_task(run_special_boost_sequence(target, label))


def mark_special_join_success(target, label: str):
    key = special_group_key(target)
    if not key:
        return
    _special_join_success.setdefault(key, set()).add(ctx_label(label))
    _special_join_failed.setdefault(key, {}).pop(ctx_label(label), None)


def mark_special_join_failed(target, label: str, reason: str):
    key = special_group_key(target)
    if not key:
        return
    clean_reason = (reason or "gagal/tidak jelas").replace("\n", " ")[:100]
    if ctx_label(label) not in _special_join_success.setdefault(key, set()):
        _special_join_failed.setdefault(key, {})[ctx_label(label)] = clean_reason


def clear_special_join_state(target):
    key = special_group_key(target)
    if not key:
        return
    _special_join_success.pop(key, None)
    _special_join_failed.pop(key, None)
    for item in list(_special_join_reported):
        if item[0] == key:
            _special_join_reported.discard(item)


def special_join_missing_reason(target, label: str) -> str:
    label = ctx_label(label)
    key = special_group_key(target)
    explicit_reason = (_special_join_failed.get(key, {}) if key else {}).get(label)
    if explicit_reason:
        return explicit_reason
    if verification_required(label):
        return "menunggu verifikasi manual"
    pending = _account_pending_group_join.get(label) or {}
    if pending:
        saved_at = pending.get("saved_at")
        age = int(time.monotonic() - float(saved_at)) if saved_at else 0
        return f"pending join tersimpan {age}s"
    if _account_group_active.get(label):
        return "masih aktif di sesi grup"
    if _account_private_session_active.get(label) or _account_private_session_waiting.get(label):
        return "sedang sesi private"
    if is_special_group_write_blocked(target, label):
        return special_group_write_block_reason(target, label)
    if not _account_running.get(label):
        return "loop akun tidak berjalan"
    if not _account_clients.get(label):
        return "client akun tidak aktif"
    return "belum ada status join"


def log_special_join_summary(target, message_id: int = 0):
    key = special_group_key(target)
    if not key:
        return
    marker = (key, int(message_id or 0))
    if marker in _special_join_reported:
        return
    _special_join_reported.add(marker)

    expected = expected_special_group_labels(target)
    joined = sorted(_special_join_success.get(key, set()))
    missing = [label for label in expected if label not in joined]
    failed_lines = [f"{label} ({special_join_missing_reason(target, label)})" for label in missing]

    Log.p("FISH", f"[JOIN SUMMARY] Grup khusus {target}")
    Log.p("FISH", f"[JOIN OK] {', '.join(joined) if joined else '-'}")
    Log.p("WARN", f"[JOIN GAGAL/BELUM] {', '.join(failed_lines) if failed_lines else '-'}")


def is_special_group_done_text(text: str) -> bool:
    tl = (text or "").lower()
    return "waktu habis" in tl or "hasil tangkapan sudah dikirim" in tl or "sesi mancing selesai" in tl


def is_special_group_active_text(text: str) -> bool:
    tl = (text or "").lower()
    active_keywords = [
        "perahu siap berangkat",
        "pendaftaran dibuka",
        "mulai mancing",
        "mulai sesi",
        "sesi mancing sudah aktif",
        "sesi sudah aktif",
        "tunggu sesi selesai",
        "sedang memancing di grup",
        "pendaftaran berhasil",
        "peserta ke-",
        "pendaftaran penuh",
    ]
    return any(keyword in tl for keyword in active_keywords)


def has_group_room_join_button(message) -> bool:
    if not getattr(message, "reply_markup", None):
        return False
    if not is_group_room_message(message):
        return False
    for row in (message.reply_markup.inline_keyboard or []):
        for btn in row:
            if "daftar mancing" in normalize_button_text(btn.text or ""):
                return True
    return False


async def special_group_has_recent_active_session(target, fish_app: Client, label: str = "main", limit: int = 25) -> bool:
    try:
        async for message in fish_app.get_chat_history(target, limit=limit):
            text = message.text or message.caption or ""
            if is_special_group_done_text(text):
                return False
            if has_group_room_join_button(message) or is_special_group_active_text(text):
                preview = text.replace("\n", " ")[:80] or "room dengan tombol daftar"
                Log.p("FISH", f"{fish_log_ctx(label)} Grup khusus masih aktif dari history: {preview}")
                return True
    except Exception as e:
        Log.p("WARN", f"{fish_log_ctx(label)} Gagal cek history grup khusus sebelum open: {e}")
    return False


async def maybe_open_special_group_room(label: str, fish_app: Client = None, reason: str = "session_done"):
    label = ctx_label(label)
    target = special_group_chat_target(label)
    if not target:
        Log.p("WARN", f"{fish_log_ctx(label)} Mode grup khusus aktif tapi target belum diset")
        return
    if verification_required(label):
        Log.p("FISH", f"{fish_log_ctx(label)} Skip open grup khusus: akun sedang menunggu verifikasi manual")
        return
    if _account_group_active.get(label):
        Log.p("FISH", f"{fish_log_ctx(label)} Skip open grup khusus: sesi grup masih aktif")
        return
    if _account_pending_group_join.get(label):
        Log.p("FISH", f"{fish_log_ctx(label)} Skip open grup khusus: masih ada join room pending")
        return
    if not special_auto_open_enabled(label):
        Log.p("FISH", f"{fish_log_ctx(label)} Auto open grup khusus OFF")
        return
    group_key = str(target)
    lock = _special_open_locks.setdefault(group_key, asyncio.Lock())
    if lock.locked():
        Log.p("FISH", f"{fish_log_ctx(label)} Open room grup khusus sudah dijadwalkan akun lain")
        return

    async with lock:
        delay_min, delay_max = special_open_delay_range(label)
        delay = random.uniform(delay_min, delay_max)
        Log.p("FISH", f"{fish_log_ctx(label)} Tunggu {delay:.1f}s sebelum open room grup khusus")
        room_msg = await wait_for_special_room_seen(target, delay, fish_app=fish_app, label=label)
        if not _account_running.get(label):
            Log.p("FISH", f"{fish_log_ctx(label)} Auto open grup khusus dibatalkan karena loop sudah stop")
            return
        if room_msg:
            if has_group_room_join_button(room_msg):
                if not _account_running.get(label):
                    Log.p("FISH", f"{fish_log_ctx(label)} Room muncul saat stop, skip daftar dan batal open")
                    return
                Log.p("FISH", f"{fish_log_ctx(label)} Room grup khusus muncul saat menunggu, ikut daftar dan batal open otomatis")
                join_status = await wait_and_join_group_room(
                    timeout=0,
                    fish_app=fish_app,
                    label=label,
                    group_targets=[target],
                    source_name="grup khusus",
                    initial_room_msg=room_msg,
                )
                Log.p("FISH", f"{fish_log_ctx(label)} Join room saat tunggu open: {join_status or 'gagal/tidak jelas'}")
                return
            Log.p("FISH", f"{fish_log_ctx(label)} Sinyal grup khusus aktif muncul saat menunggu, batal open otomatis")
            return

        tried_openers = set()
        while True:
            opener_label, opener_client = choose_special_group_opener(target, excluded_labels=tried_openers)
            if not opener_label or not opener_client:
                Log.p("WARN", f"{fish_log_ctx(label)} Tidak ada userbot aktif untuk open room grup khusus")
                return
            tried_openers.add(opener_label)
            if not _account_running.get(opener_label):
                Log.p("FISH", f"[{opener_label}] Skip open room, opener sudah stop")
                continue
            if is_special_group_write_blocked(target, opener_label):
                Log.p("FISH", f"[{opener_label}] Skip open room, {special_group_write_block_reason(target, opener_label)}")
                continue

            if await special_group_has_recent_active_session(target, opener_client, label=opener_label):
                Log.p("FISH", f"[{opener_label}] Batal open room, grup khusus masih punya sesi/room aktif")
                return

            sent = await send_special_group_command(
                target,
                special_open_command(),
                fish_app=opener_client,
                label=opener_label,
                action="open room grup khusus",
            )
            if not sent:
                audit_log(opener_label, "special_open_failed", f"group={target}, reason={reason}", user_id=0)
                Log.p("WARN", f"[{opener_label}] Gagal kirim open room grup khusus ke {target}, coba opener lain")
                continue
            touch_activity(action="open special group room", event=reason, label=opener_label)
            audit_log(opener_label, "special_open_room", f"group={target}, reason={reason}", user_id=0)
            Log.p("FISH", f"[{opener_label}] Kirim open room grup khusus ke {target}")
            return


