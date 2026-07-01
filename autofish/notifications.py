from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def should_send_group_log(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if "rare catch" in lowered:
        return True
    return any(marker in lowered for marker in GROUP_LOG_ERROR_MARKERS)


def set_pending_input(user_id: int, mode: str):
    user_id = int(user_id)
    _pending_owner_inputs[user_id] = mode
    task = _pending_input_tasks.pop(user_id, None)
    cancel_task_background(task, label="main", reason="replace pending input timer")
    try:
        _pending_input_tasks[user_id] = asyncio.create_task(expire_pending_input(user_id, mode))
    except RuntimeError:
        pass


def invalidate_admin_cache():
    global _admin_ids_cache_ts
    _admin_ids_cache_ts = 0.0


def invalidate_accounts_cache():
    global _all_accounts_cache_ts
    _all_accounts_cache_ts = 0.0


def is_callback_rate_limited(user_id: int) -> bool:
    user_id = int(user_id or 0)
    now = time.monotonic()
    last = _callback_rate.get(user_id, 0.0)
    if now - last < _CALLBACK_MIN_INTERVAL:
        return True
    _callback_rate[user_id] = now
    if len(_callback_rate) > 1000:
        cutoff = now - 60.0
        for uid, ts in list(_callback_rate.items()):
            if ts < cutoff:
                _callback_rate.pop(uid, None)
    return False


def get_lifecycle_lock(label: str) -> asyncio.Lock:
    label = ctx_label(label)
    lock = _account_lifecycle_locks.get(label)
    if lock is None:
        lock = asyncio.Lock()
        _account_lifecycle_locks[label] = lock
    return lock


def get_pending_input(user_id: int) -> str | None:
    return _pending_owner_inputs.get(int(user_id))


def clear_pending_input(user_id: int):
    user_id = int(user_id)
    _pending_owner_inputs.pop(user_id, None)
    task = _pending_input_tasks.pop(user_id, None)
    cancel_task_background(task, label="main", reason="clear pending input timer")


async def expire_pending_input(user_id: int, mode: str):
    await asyncio.sleep(PENDING_INPUT_TIMEOUT)
    if _pending_owner_inputs.get(int(user_id)) == mode:
        _pending_owner_inputs.pop(int(user_id), None)
        _pending_input_tasks.pop(int(user_id), None)


async def notify(text: str, label: str = None):
    global _last_notify_message_id
    label = ctx_label(label)
    account = load_account(label)
    owner_ids = account_notification_owner_ids(account, label)
    display_name = account_display_name(account, owner_ids[0] if owner_ids else OWNER_ID)
    text = (text or "").replace(f"[{label}]", display_name)
    ts  = now_wib().strftime("%d/%m %H:%M")
    msg = f"🤖 [{ts}]\n{text}"
    try:
        if _tg_app and _tg_app.bot:
            for owner_id in owner_ids:
                key = (label, owner_id)
                lock = _account_notify_locks.setdefault(key, asyncio.Lock())
                async with lock:
                    last_message_id = _account_notify_message_ids.get(key)
                    if last_message_id:
                        try:
                            await _tg_app.bot.edit_message_text(
                                chat_id=owner_id,
                                message_id=last_message_id,
                                text=msg,
                                parse_mode=None,
                            )
                            continue
                        except Exception as e:
                            if "message is not modified" in str(e).lower():
                                continue
                            _account_notify_message_ids.pop(key, None)
                            pass
                    sent = await _tg_app.bot.send_message(
                        chat_id=owner_id,
                        text=msg,
                        parse_mode=None,
                    )
                    _account_notify_message_ids[key] = sent.message_id
                    if label == "main" and owner_id == OWNER_ID:
                        _last_notify_message_id = sent.message_id
        else:
            _last_notify_message_id = None
        Log.p("NOTIF", text[:80])
    except Exception as e:
        Log.p("ERROR", f"notify gagal: {e}")


async def notify_owner_direct(text: str):
    global _last_log_chat_sent_at
    if not _tg_app or not _tg_app.bot:
        return
    target = BOT_LOG_CHAT or CAPTCHA_LOG_CHAT
    target_chat = parse_chat_target(target) if target else OWNER_ID
    if not target_chat:
        return
    async with _log_chat_lock:
        elapsed = time.monotonic() - _last_log_chat_sent_at
        wait = max(0.0, LOG_CHAT_MIN_INTERVAL - elapsed)
        if wait:
            await asyncio.sleep(wait)
        try:
            await _tg_app.bot.send_message(
                chat_id=target_chat,
                text=(text or "")[:4000],
                parse_mode="HTML",
            )
            _last_log_chat_sent_at = time.monotonic()
        except RetryAfter as e:
            retry_after = int(getattr(e, "retry_after", 5) or 5) + 1
            Log.p("WARN", f"notify direct flood ke {target_chat}, retry {retry_after}s")
            await asyncio.sleep(retry_after)
            try:
                await _tg_app.bot.send_message(
                    chat_id=target_chat,
                    text=(text or "")[:4000],
                    parse_mode="HTML",
                )
                _last_log_chat_sent_at = time.monotonic()
            except Exception as e2:
                Log.p("WARN", f"notify direct gagal setelah retry ke {target_chat}: {e2}")
        except Exception as e:
            Log.p("WARN", f"notify direct gagal ke {target_chat}: {e}")


async def send_log_chat_message(text: str, reply_markup=None):
    global _last_log_chat_sent_at
    if not _tg_app or not _tg_app.bot:
        return None
    if not should_send_group_log(text):
        return None
    target = BOT_LOG_CHAT or CAPTCHA_LOG_CHAT
    target_chat = parse_chat_target(target) if target else OWNER_ID
    if not target_chat:
        return None
    async with _log_chat_lock:
        elapsed = time.monotonic() - _last_log_chat_sent_at
        wait = max(0.0, LOG_CHAT_MIN_INTERVAL - elapsed)
        if wait:
            await asyncio.sleep(wait)
        try:
            sent = await _tg_app.bot.send_message(
                chat_id=target_chat,
                text=(text or "")[:4000],
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            _last_log_chat_sent_at = time.monotonic()
            return sent
        except RetryAfter as e:
            retry_after = int(getattr(e, "retry_after", 5) or 5) + 1
            Log.p("WARN", f"send log flood ke {target_chat}, retry {retry_after}s")
            await asyncio.sleep(retry_after)
            try:
                sent = await _tg_app.bot.send_message(
                    chat_id=target_chat,
                    text=(text or "")[:4000],
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                _last_log_chat_sent_at = time.monotonic()
                return sent
            except Exception as e2:
                Log.p("WARN", f"send log gagal setelah retry ke {target_chat}: {e2}")
        except Exception as e:
            Log.p("WARN", f"send log gagal ke {target_chat}: {e}")
    return None


async def edit_log_chat_message(chat_id: int, message_id: int, text: str) -> bool:
    if not _tg_app or not _tg_app.bot:
        return False
    try:
        await _tg_app.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(text or "")[:4000],
            parse_mode="HTML",
        )
        return True
    except RetryAfter as e:
        retry_after = int(getattr(e, "retry_after", 5) or 5) + 1
        await asyncio.sleep(retry_after)
        try:
            await _tg_app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(text or "")[:4000],
                parse_mode="HTML",
            )
            return True
        except Exception as e2:
            Log.p("WARN", f"edit log gagal setelah retry: {e2}")
    except Exception as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            return True
        Log.p("WARN", f"edit log gagal: {e}")
    return False


async def log_event(kind: str, label: str = "main", message: str = ""):
    if not (BOT_LOG_CHAT or CAPTCHA_LOG_CHAT):
        return
    kind = str(kind or "").strip()
    if kind not in GROUP_LOG_ERROR_EVENT_KINDS:
        return
    label = ctx_label(label)
    account_name = account_name_for_label(label)
    body = (
        f"Akun: {account_name} ({label})\n"
        f"{message or '-'}"
    )
    text = (
        f"<b>[{html.escape(kind)}]</b>\n"
        f"<blockquote expandable>{html.escape(body)}</blockquote>"
    )
    await notify_owner_direct(text)


def update_origin_info(update) -> tuple[str, str]:
    chat_id = "-"
    user_id = "-"
    if update:
        effective_chat = getattr(update, "effective_chat", None)
        effective_user = getattr(update, "effective_user", None)
        if effective_chat is not None:
            chat_id = str(getattr(effective_chat, "id", "-") or "-")
        if effective_user is not None:
            user_id = str(getattr(effective_user, "id", "-") or "-")
    return chat_id, user_id


def is_transient_telegram_network_error(error: Exception) -> bool:
    if isinstance(error, (NetworkError, TimedOut)):
        return True
    cause = getattr(error, "__cause__", None)
    return isinstance(cause, (NetworkError, TimedOut))


async def safe_query_answer(query, *args, **kwargs) -> bool:
    try:
        await query.answer(*args, **kwargs)
        return True
    except (NetworkError, TimedOut) as e:
        Log.p("WARN", f"callback answer gagal sementara: {e}")
    except BadRequest as e:
        Log.p("WARN", f"callback answer diabaikan: {e}")
    return False


def current_mode_for_traceback(label: str = None) -> str:
    try:
        return mode_display_name(current_fish_mode(label))
    except Exception:
        return "-"


async def send_traceback_log(
    error: Exception,
    *,
    update=None,
    label: str = None,
    mode: str = None,
    user_id: int | str = None,
    chat_id: int | str = None,
):
    if not (BOT_LOG_CHAT or CAPTCHA_LOG_CHAT):
        return

    update_chat_id, update_user_id = update_origin_info(update)
    chat_id = str(chat_id or update_chat_id or "-")
    user_id = str(user_id or update_user_id or "-")
    mode = mode or current_mode_for_traceback(label)
    tb = traceback.format_exc()
    if not tb or tb.strip() == "NoneType: None":
        tb = "".join(traceback.format_exception(type(error), error, getattr(error, "__traceback__", None)))
    tb = tb[-3000:]
    error_text = f"{type(error).__name__}: {error}"
    text = (
        f"<b>Error:</b> {html.escape(error_text[:700])}\n"
        f"<b>Date:</b> {now_wib().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>form user :</b> {html.escape(chat_id)}\n"
        f"<b>Mode :</b> {html.escape(str(mode or '-'))}\n"
        f"<b>User ID:</b> {html.escape(user_id)}\n\n"
        "<b>Traceback:</b>\n"
        f"<pre><code>{html.escape(tb)}</code></pre>"
    )
    await send_log_chat_message(text)


async def tg_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if not error:
        return
    if message_not_modified_error(error):
        return
    if is_transient_telegram_network_error(error):
        Log.p("WARN", f"Telegram network error sementara: {error}")
        return
    Log.p("ERROR", f"Telegram handler error: {error}")
    try:
        label = None
        if update and getattr(update, "effective_user", None):
            label = selected_account_label(int(update.effective_user.id))
        await send_traceback_log(error, update=update, label=label)
    except Exception as e:
        Log.p("WARN", f"Gagal kirim traceback Telegram handler ke log: {e}")


def is_ignored_asyncio_error(error=None, message: str = "") -> bool:
    text = f"{message}\n{error or ''}".lower()
    ignored_markers = (
        "peer id invalid",
        "id not found:",
    )
    return any(marker in text for marker in ignored_markers)


def asyncio_exception_handler(loop, context):
    error = context.get("exception")
    message = str(context.get("message") or "Unhandled asyncio exception")
    if is_ignored_asyncio_error(error, message):
        return
    Log.p("ERROR", f"{message}: {error or '-'}")
    if not _tg_app or not _tg_app.bot:
        return
    try:
        if error:
            loop.create_task(send_traceback_log(error, label="main", mode="asyncio_task"))
        else:
            loop.create_task(
                send_log_chat_message(
                    "⚠️ <b>Error:</b> Unhandled asyncio exception\n\n"
                    + blockquote(message[:1000])
                )
            )
    except Exception as e:
        Log.p("WARN", f"Gagal jadwalkan asyncio traceback ke log: {e}")


def is_login_required_error(error: Exception | str) -> bool:
    raw = str(error or "")
    text = raw.lower()
    error_name = error.__class__.__name__.lower() if isinstance(error, Exception) else ""
    markers = [
        "auth key",
        "auth_key",
        "authkey",
        "session revoked",
        "session expired",
        "session password needed",
        "sessionpasswordneeded",
        "auth_key_unregistered",
        "auth_key_duplicated",
        "auth_key_invalid",
        "session_revoked",
        "unauthorized",
        "not authorized",
        "authorization key",
        "authorization failed",
        "user_deactivated",
        "user deactivated",
        "phone_code",
        "phone code",
        "revoked",
    ]
    return any(marker in text or marker in error_name for marker in markers)


def is_connection_lost_error(error: Exception | str) -> bool:
    raw = str(error or "")
    text = raw.lower()
    error_name = error.__class__.__name__.lower() if isinstance(error, Exception) else ""
    markers = [
        "connection lost",
        "connection aborted",
        "connection reset",
        "broken pipe",
        "network is unreachable",
        "timed out",
        "timeout",
        "server sent no data",
        "socket is closed",
        "transport closed",
        "client has not been started yet",
    ]
    return any(marker in text or marker in error_name for marker in markers)


def captcha_verification_status(text: str) -> str | None:
    tl = normalize_fish_name(text or "")
    if not tl:
        return None
    if (
        "verifikasi berhasil" in tl
        or "jawaban benar" in tl
        or captcha_resume_mancing_text(text)
    ):
        return "success"
    if "jawaban salah" in tl or ("verifikasi" in tl and "gagal" in tl):
        return "failure"
    return None


def runtime_state_summary(label: str = "main") -> str:
    label = ctx_label(label)
    mode = current_fish_mode(label)
    pending_join = _account_pending_group_join.get(label) or {}
    pending_age = ""
    saved_at = pending_join.get("saved_at")
    if saved_at:
        try:
            pending_age = f", join_pending_age={int(max(0, time.monotonic() - float(saved_at)))}s"
        except Exception:
            pending_age = ""
    return (
        f"mode={mode}, running={int(bool(_account_running.get(label)))}, "
        f"verify={int(verification_required(label))}, group={int(bool(_account_group_active.get(label)))}, "
        f"private={int(bool(_account_private_session_active.get(label)))}, "
        f"wait_confirm={int(bool(_account_waiting_confirmation.get(label)))}, "
        f"wait_private={int(bool(_account_private_session_waiting.get(label)))}, "
        f"active_group={active_group_chat_target(label) or '-'}, "
        f"pending_join={int(bool(pending_join))}{pending_age}"
    )


async def log_error_event_once(
    kind: str,
    label: str = "main",
    message: str = "",
    *,
    section: str = "",
    cooldown: int = ERROR_LOG_COOLDOWN,
    fingerprint: str = "",
):
    label = ctx_label(label)
    kind = str(kind or "").strip()
    fingerprint = (fingerprint or message or section or kind)[:120]
    key = (kind, label, fingerprint)
    now = time.monotonic()
    last = _error_log_last_sent.get(key, 0.0)
    if now - last < cooldown:
        return
    _error_log_last_sent[key] = now
    detail = []
    if section:
        detail.append(f"Bagian: {section}")
    if message:
        detail.append(str(message)[:1000])
    await log_event(kind, label, "\n".join(detail) or "-")


def render_sell_flow_log(label: str) -> str:
    label = ctx_label(label)
    state = _sell_flow_log_states.get(label, {})
    account_name = account_name_for_label(label)
    lines = [
        f"Akun: {account_name} ({label})",
        f"Status: {state.get('status', 'Berjalan')}",
        "",
        "Inventory:",
        state.get("inventory", "Menunggu..."),
        "",
        "Filter:",
        state.get("filter", "Menunggu..."),
        "",
        "Favorite:",
        state.get("favorite", "Menunggu..."),
        "",
        "Sell:",
        state.get("sell", "Menunggu..."),
    ]
    body = "\n".join(lines)
    return (
        "<b>[SELL FLOW]</b>\n"
        f"<blockquote expandable>{html.escape(body)}</blockquote>"
    )


async def sell_flow_log_start(label: str):
    if not SELL_FLOW_GROUP_LOG or not (BOT_LOG_CHAT or CAPTCHA_LOG_CHAT):
        return
    label = ctx_label(label)
    _sell_flow_log_states[label] = {
        "status": "Berjalan",
        "inventory": "Mulai baca inventory...",
        "filter": "Menunggu inventory.",
        "favorite": "Menunggu filter.",
        "sell": "Menunggu favorite.",
    }
    sent = await send_log_chat_message(render_sell_flow_log(label))
    if sent:
        chat_id = getattr(sent, "chat_id", None) or getattr(getattr(sent, "chat", None), "id", None)
        if chat_id:
            _sell_flow_log_messages[label] = (chat_id, sent.message_id)


async def sell_flow_log_update(label: str, **updates):
    if not SELL_FLOW_GROUP_LOG or not (BOT_LOG_CHAT or CAPTCHA_LOG_CHAT):
        return
    label = ctx_label(label)
    state = _sell_flow_log_states.setdefault(label, {})
    state.update({k: v for k, v in updates.items() if v is not None})
    text = render_sell_flow_log(label)
    target = _sell_flow_log_messages.get(label)
    if target:
        chat_id, message_id = target
        if await edit_log_chat_message(chat_id, message_id, text):
            return
    sent = await send_log_chat_message(text)
    if sent:
        chat_id = getattr(sent, "chat_id", None) or getattr(getattr(sent, "chat", None), "id", None)
        if chat_id:
            _sell_flow_log_messages[label] = (chat_id, sent.message_id)


