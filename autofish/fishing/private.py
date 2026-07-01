from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def private_fish_bot_targets(label: str = None) -> list[str]:
    targets = [private_command_bot_username(label), FISH_BOT_USERNAME]
    if PRIVATE_FISH_BOT_USERNAMES:
        targets.extend(split_chat_targets(PRIVATE_FISH_BOT_USERNAMES))

    cleaned = []
    seen = set()
    for target in targets:
        target = (target or "").strip()
        if not target:
            continue
        key = target.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(target)
    return cleaned or [FISH_BOT_USERNAME]


def private_fish_bot_filter(label: str = None):
    return filters.chat(private_fish_bot_targets(label))


def is_private_fish_bot_message(message, label: str = None) -> bool:
    chat = getattr(message, "chat", None)
    if not chat:
        return False
    targets = {str(target).strip().lower().lstrip("@") for target in private_fish_bot_targets(label)}
    username = str(getattr(chat, "username", "") or "").strip().lower().lstrip("@")
    if username and username in targets:
        return True
    chat_id = str(getattr(chat, "id", "") or "").strip().lower()
    return chat_id in targets


async def send_private_mancing(fish_app: Client = None, label: str = "main", allow_all_fallback: bool = False) -> bool:
    label = ctx_label(label)
    mode = current_fish_mode(label)
    if _account_private_session_active.get(label):
        Log.p("FISH", f"{fish_log_ctx(label, mode)} BLOCK /mancing private: sesi private masih aktif")
        touch_activity(action="block private /mancing", event="sesi private masih aktif", label=label)
        return False
    if mode == "group_room":
        Log.p("WARN", f"{fish_log_ctx(label, mode)} BLOCK /mancing private: mode group_room")
        touch_activity(action="block private /mancing", event="mode group_room", label=label)
        return False
    if mode == "special_group":
        Log.p("WARN", f"{fish_log_ctx(label, mode)} BLOCK /mancing private: mode special_group")
        touch_activity(action="block private /mancing", event="mode special_group", label=label)
        return False
    if mode == "all" and not allow_all_fallback:
        Log.p("WARN", f"{fish_log_ctx(label, mode)} BLOCK /mancing private: all mode tanpa fallback eksplisit")
        touch_activity(action="block private /mancing", event="all mode guarded", label=label)
        return False

    target_bot = private_command_bot_username(label)
    sent = await safe_send(target_bot, "/mancing", fish_app=fish_app, label=label)
    if not sent:
        return False
    inc_stat("mancing_sent", label=label)
    return True


def is_captcha_text(text: str) -> bool:
    tl = normalize_fish_name(text)
    return any(k in tl for k in QUICK_VERIFY_KEYWORDS)


def is_private_fishing_active_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        "auto mancing dimulai" in tl
        or "auto mancing akan dimulai" in tl
        or ("auto mancing" in tl and "sisa:" in tl)
        or "kamu sedang memancing" in tl
        or "waktu berjalan" in tl
        or "cast ke-" in tl
    )


def is_private_fishing_done_text(text: str) -> bool:
    raw = text or ""
    tl = normalize_fish_name(raw)
    return (
        "SESI MANCING SELESAI!" in raw.upper()
        or "sesi mancing selesai" in tl
        or "waktu habis" in tl
        or "hasil tangkapan sudah dikirim" in tl
        or ("terima kasih sudah memancing" in tl and "total coins" in tl)
    )


def classify_private_fish_event_text(text: str) -> str | None:
    tl = (text or "").lower()
    if is_private_fishing_done_text(text):
        return "done"
    if "inventory penuh" in tl:
        return "full"
    if is_captcha_text(text):
        return "captcha"
    return None


def parse_private_remaining_seconds(text: str) -> int | None:
    match = re.search(r"Sisa:\s*(\d{1,2}):(\d{2})", text or "", re.I)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def parse_boost_remaining_seconds(text: str) -> int | None:
    match = re.search(r"Sisa waktu:\s*(\d+)\s*menit\s*(\d+)\s*detik", text or "", re.I)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


async def wait_for_fish_event(
    timeout: int = 180,
    fish_app: Client = None,
    label: str = "main",
    chat_filter=None,
):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu event mancing")
    if not fish_app:
        return None
    chat_filter = chat_filter or filters.chat(FISH_BOT_USERNAME)
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()

    async def _handler(client, message):
        text = message.text or message.caption or ""
        tl   = text.lower()

        if result_queue.full() or not mark_event_once(label, message, "group_fish_event"):
            return
        preview = text.replace("\n", " ")[:60]
        Log.p("FISH", f"{fish_log_ctx(label)} [BOT] {preview}")
        touch_activity(event=preview, label=label)
        asyncio.create_task(maybe_notify_rare_catch(message, fish_app, label, "group"))
        if is_special_group_mode(label) and message.chat:
            observe_special_boost_message(message.chat.id, text, label=label)

        if is_command_mode(label):
            return

        if "sesi mancing selesai" in tl or "waktu habis" in tl or "hasil tangkapan sudah dikirim" in tl:
            await result_queue.put(("done", text, message))
        elif "perahu siap berangkat" in tl or "mulai mancing" in tl or "mulai sesi" in tl:
            if is_special_group_mode(label) and message.chat:
                log_special_join_summary(message.chat.id, getattr(message, "id", 0))
            await result_queue.put(("group_active", text, message))
        elif "sedang memancing di grup" in tl or "tunggu sesi grup selesai" in tl:
            await result_queue.put(("group_active", text, message))
        elif "inventory penuh" in tl:
            await result_queue.put(("full", text, message))
        elif is_captcha_text(text):
            await result_queue.put(("captcha", text, message))

    handler = MessageHandler(
        _handler,
        chat_filter & filters.incoming,
    )
    edit_handler = EditedMessageHandler(
        _handler,
        chat_filter,
    )
    fish_app.add_handler(handler, group=handler_group)
    fish_app.add_handler(edit_handler, group=handler_group)

    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        await remove_handler_now(handler, group=handler_group, fish_app=fish_app)
        await remove_handler_now(edit_handler, group=handler_group, fish_app=fish_app)


async def wait_for_private_fish_event(
    timeout: int = None,
    fish_app: Client = None,
    label: str = "main",
):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu event private")
    if not fish_app:
        return None
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()
    chat_filter = private_fish_bot_filter(label)
    history_targets = private_fish_bot_targets(label)
    started_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    log_ctx = fish_log_ctx(label)
    last_remaining_seconds: int | None = None
    Log.p("FISH", f"{log_ctx} Menunggu selesai private dari: {', '.join(history_targets)}")

    async def _handler(client, message):
        nonlocal last_remaining_seconds
        if not is_private_fish_bot_message(message, label=label):
            return
        if result_queue.full() or not mark_event_once(label, message, "private_fish_event"):
            return
        text = await resolve_message_text(message, fish_app=fish_app)

        preview = text.replace("\n", " ")[:60] if text else "<kosong>"
        Log.p("FISH", f"{log_ctx} [BOT] {preview}")
        touch_activity(event=preview, label=label)
        asyncio.create_task(maybe_notify_rare_catch(message, fish_app, label, "private"))

        if not text:
            if last_remaining_seconds is not None and last_remaining_seconds <= PRIVATE_EMPTY_DONE_GRACE:
                Log.p("FISH", f"{log_ctx} Update kosong setelah countdown habis, anggap sesi private selesai")
                await result_queue.put(("done", "", message))
            return

        event = classify_private_fish_event_text(text)
        if event == "done":
            Log.p("FISH", f"{log_ctx} Pesan selesai private terdeteksi")
            await result_queue.put((event, text, message))
        elif event in {"full", "captcha"}:
            await result_queue.put((event, text, message))
        elif not is_command_mode(label) and is_private_fishing_active_text(text):
            _account_private_session_active[label] = True
            remaining = parse_private_remaining_seconds(text)
            if remaining is not None:
                last_remaining_seconds = remaining
            touch_activity(action="private session active", event=preview, label=label)

    async def _history_poll():
        warned_targets = set()
        while not result_queue.full():
            await asyncio.sleep(3)
            for target in history_targets:
                try:
                    async for message in fish_app.get_chat_history(target, limit=8):
                        if not message_is_after(message, started_at):
                            continue
                        if not mark_event_once(label, message, "private_history_event"):
                            continue
                        text = await resolve_message_text(message, fish_app=fish_app)
                        event = classify_private_fish_event_text(text)
                        preview = text.replace("\n", " ")[:60] if text else "<kosong>"
                        if not event:
                            if not is_command_mode(label) and is_private_fishing_active_text(text):
                                _account_private_session_active[label] = True
                                remaining = parse_private_remaining_seconds(text)
                                if remaining is not None:
                                    last_remaining_seconds = remaining
                                touch_activity(action="private session active (history)", event=preview, label=label)
                            continue
                        Log.p("FISH", f"{log_ctx} Event private dari history {target}: {preview}")
                        touch_activity(event=preview, label=label)
                        if not result_queue.full():
                            await result_queue.put((event, text, message))
                        return
                except Exception as e:
                    if target not in warned_targets:
                        warned_targets.add(target)
                        Log.p("WARN", f"{log_ctx} Gagal cek history private {target}: {e}")

    handlers = [
        MessageHandler(_handler, chat_filter & filters.incoming),
        EditedMessageHandler(_handler, chat_filter),
    ]
    for handler in handlers:
        fish_app.add_handler(handler, group=handler_group)

    poll_task = asyncio.create_task(_history_poll())
    try:
        _account_private_session_waiting[label] = True
        _account_private_wait_started[label] = time.monotonic()
        if timeout is None:
            timeout = PRIVATE_EVENT_TIMEOUT
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        Log.p("WARN", f"{log_ctx} Timeout tunggu event private {timeout}s, reset state private")
        clear_private_wait_state(label)
        return None
    finally:
        _account_private_session_waiting.pop(label, None)
        _account_private_wait_started.pop(label, None)
        _account_private_session_active.pop(label, None)
        _account_waiting_confirmation.pop(label, None)
        await cancel_task_safely(poll_task, label=label, reason="stop private history poll")
        await remove_handlers_now(handlers, group=handler_group, fish_app=fish_app)


async def wait_for_private_boost_reply(fish_app: Client = None, label: str = "main", timeout: int = 18) -> str | None:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu reply boost")
    if not fish_app:
        return None
    target_bot = private_command_bot_username(label)
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()
    keywords = [
        "boost personal aktif",
        "boost kamu sudah aktif",
        "tidak punya cukup trisula fragment",
        "trisula fragment",
    ]

    async def _handler(client, message):
        if result_queue.full():
            return
        text = await resolve_message_text(message, fish_app=fish_app)
        tl = normalize_fish_name(text)
        if any(keyword in tl for keyword in keywords):
            await result_queue.put(text)

    handlers = [
        MessageHandler(_handler, filters.chat(target_bot) & filters.incoming),
        EditedMessageHandler(_handler, filters.chat(target_bot)),
    ]
    for handler in handlers:
        fish_app.add_handler(handler, group=handler_group)

    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        remove_handlers(handlers, group=handler_group, fish_app=fish_app)


def classify_private_boost_reply(text: str) -> tuple[str, int | None]:
    tl = normalize_fish_name(text or "")
    if "tidak punya cukup trisula fragment" in tl:
        return "no_fragment", None
    if "boost personal aktif" in tl:
        return "active", 304
    if "boost kamu sudah aktif" in tl:
        remaining = parse_boost_remaining_seconds(text)
        return "already_active", remaining
    return "unknown", None


async def try_private_boost(fish_app: Client = None, label: str = "main") -> None:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="boost personal")
    if not fish_app:
        _account_private_boost_last[label] = "userbot belum siap"
        return
    log_ctx = fish_log_ctx(label, "private")
    if not _account_private_session_active.get(label):
        _account_private_boost_last[label] = "skip - sesi private belum aktif"
        return
    Log.p("FISH", f"{log_ctx} Kirim /boost personal")
    reply_task = asyncio.create_task(wait_for_private_boost_reply(fish_app=fish_app, label=label))
    await asyncio.sleep(0)
    if not _account_private_session_active.get(label):
        await cancel_task_safely(reply_task, label=label, reason="cancel wait boost reply")
        _account_private_boost_last[label] = "skip - sesi private selesai"
        return
    target_bot = private_command_bot_username(label)
    sent = await safe_send(target_bot, "/boost", fish_app=fish_app, label=label)
    if not sent:
        await cancel_task_safely(reply_task, label=label, reason="cancel wait boost reply")
        _account_private_boost_last[label] = "gagal kirim /boost"
        Log.p("WARN", f"{log_ctx} Gagal kirim /boost, mancing tetap lanjut")
        return

    reply = await reply_task
    status, seconds = classify_private_boost_reply(reply or "")
    if status == "active":
        _account_private_boost_until[label] = now_wib() + timedelta(seconds=seconds or 304)
        _account_private_boost_last[label] = "aktif 5 menit 4 detik"
        save_private_boost_paused(label, False)
        Log.p("FISH", f"{log_ctx} Boost personal aktif, tahan retry 304s")
        return
    if status == "already_active":
        ttl = max(1, int(seconds or 60))
        _account_private_boost_until[label] = now_wib() + timedelta(seconds=ttl)
        _account_private_boost_last[label] = f"sudah aktif {ttl}s"
        save_private_boost_paused(label, False)
        Log.p("FISH", f"{log_ctx} Boost personal sudah aktif, sisa {ttl}s")
        return
    if status == "no_fragment":
        save_private_boost_paused(label, True)
        _account_private_boost_last[label] = "paused - fragment kurang"
        Log.p("WARN", f"{log_ctx} Fragment boost kurang, auto boost dipause sampai user coba lagi")
        return

    _account_private_boost_last[label] = "respons boost tidak jelas/timeout"
    _account_private_boost_until[label] = now_wib() + timedelta(seconds=90)
    Log.p("WARN", f"{log_ctx} Respons /boost tidak jelas, mancing tetap lanjut")


async def private_boost_loop(fish_app: Client = None, label: str = "main"):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="loop boost private")
    if not fish_app:
        _account_private_boost_last[label] = "userbot belum siap"
        return
    while not _shutdown_event.is_set() and _account_running.get(label, False):
        try:
            if maintenance_blocks_account(label):
                Log.p("FISH", f"{fish_log_ctx(label)} Maintenance aktif, loop dijeda")
                _account_running[label] = False
                break
            if verification_required(label):
                _account_private_boost_last[label] = "paused - menunggu verifikasi manual"
                await asyncio.sleep(5)
                continue
            if current_fish_mode(label) != "private" or not private_auto_boost_enabled(label):
                await asyncio.sleep(5)
                continue
            if private_boost_paused(label):
                await asyncio.sleep(5)
                continue
            if _account_waiting_confirmation.get(label):
                _account_private_boost_last[label] = "menunggu konfirmasi mancing"
                await asyncio.sleep(3)
                continue
            if not _account_private_session_active.get(label):
                _account_private_boost_last[label] = "menunggu sesi private aktif"
                await asyncio.sleep(3)
                continue
            boost_until = _account_private_boost_until.get(label)
            if boost_until and now_wib() < boost_until:
                remaining = max(1, int((boost_until - now_wib()).total_seconds()))
                await asyncio.sleep(min(remaining, 5))
                continue
            await try_private_boost(fish_app=fish_app, label=label)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            _account_private_boost_last[label] = f"error: {str(e)[:80]}"
            Log.p("WARN", f"{fish_log_ctx(label, 'private')} Error private boost loop: {e}")
            await log_error_event_once(
                "LOOP_ERROR",
                label,
                f"Error private boost loop: {str(e)[:500]}",
                section="private_boost_loop",
                fingerprint=f"private_boost_loop:{type(e).__name__}",
            )
            await asyncio.sleep(10)


