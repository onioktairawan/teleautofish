from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def extract_button_labels(message) -> list[str]:
    labels = []
    if not message or not message.reply_markup:
        return labels

    for row in (message.reply_markup.inline_keyboard or []):
        for btn in row:
            label = btn.text or ""
            if label:
                labels.append(label)

    return labels


def find_button_position(message, target_label: str) -> tuple[int, int] | None:
    if not message or not message.reply_markup:
        return None
    target = target_label or ""
    target_normalized = normalize_fish_name(target)
    for y, row in enumerate(message.reply_markup.inline_keyboard or []):
        for x, btn in enumerate(row):
            label = btn.text or ""
            if label == target or normalize_fish_name(label) == target_normalized:
                return x, y
    return None


def first_inline_button(message):
    if not message or not message.reply_markup:
        return None
    for y, row in enumerate(message.reply_markup.inline_keyboard or []):
        for x, btn in enumerate(row):
            return x, y, btn
    return None


def button_url(btn) -> str:
    if not btn:
        return ""
    direct_url = getattr(btn, "url", None)
    if direct_url:
        return str(direct_url)
    for attr in ("web_app", "login_url"):
        value = getattr(btn, attr, None)
        url = getattr(value, "url", None)
        if url:
            return str(url)
    return ""


def first_verification_url(message) -> str:
    if not message or not message.reply_markup:
        return ""
    fallback = ""
    for row in (message.reply_markup.inline_keyboard or []):
        for btn in row:
            label = normalize_button_text(getattr(btn, "text", "") or "")
            url = button_url(btn)
            if url and ("verifikasi" in label or "verify" in label or "fishid.online/verify" in url):
                return url
            if url and not fallback:
                fallback = url
    return fallback


def captcha_resume_mancing_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        ("verifikasi berhasil" in tl or "setelah berhasil" in tl)
        and (
            "gunakan /mancing" in tl
            or "lanjut mancing" in tl
            or "melanjutkan" in tl
            or "lanjutkan dengan /mancing" in tl
        )
    )


def is_captcha_verify_response(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return any(k in tl for k in ["verifikasi berhasil", "jawaban benar", "jawaban salah", "berhasil", "gagal"])


async def find_captcha_verify_response(captcha_msg, fish_app: Client = None, label: str = "main") -> str | None:
    label = ctx_label(label)
    interval = max(0.05, CAPTCHA_VERIFY_POLL_INTERVAL)
    attempts = max(1, int(6 / interval))
    for _ in range(attempts):
        await asyncio.sleep(interval)
        try:
            chat = getattr(captcha_msg, "chat", None)
            message_id = getattr(captcha_msg, "id", None)
            if chat and message_id:
                refreshed = await fish_app.get_messages(chat.id, message_id)
                text = await resolve_message_text(refreshed, fish_app=fish_app)
                if text and is_captcha_verify_response(text):
                    return text
        except Exception:
            pass
        for target in private_fish_bot_targets(label):
            try:
                async for message in fish_app.get_chat_history(target, limit=5):
                    text = await resolve_message_text(message, fish_app=fish_app)
                    if text and is_captcha_verify_response(text):
                        return text
            except Exception:
                continue
    return None


def verification_chat_url(label: str, verification_msg=None) -> str:
    username = ""
    chat = getattr(verification_msg, "chat", None)
    if chat:
        username = getattr(chat, "username", "") or ""
    if not username:
        username = (private_command_bot_username(label) or FISH_BOT_USERNAME).lstrip("@")
    username = username.lstrip("@").strip()
    return f"https://t.me/{username}" if username else ""


async def send_manual_verification_notice(label: str, url: str = "", message_text: str = "", chat_url: str = ""):
    label = ctx_label(label)
    account = load_account(label)
    owner_ids = account_notification_owner_ids(account, label)
    account_name = account_name_for_label(label, owner_ids[0] if owner_ids else OWNER_ID)
    rows = []
    if chat_url:
        button_text, icon_id = premium_button_text_and_icon("🔒 Buka Chat Fish It")
        kwargs = {"text": button_text, "url": chat_url, "style": "primary"}
        if icon_id:
            kwargs["icon_custom_emoji_id"] = icon_id
        try:
            button = InlineKeyboardButton(**kwargs)
        except TypeError:
            kwargs.pop("icon_custom_emoji_id", None)
            button = InlineKeyboardButton(**kwargs)
        rows.append([button])
    rows.append([styled_button("✅ Sudah Verifikasi", f"verify:done:{label}", "success")])
    rows.append([styled_button("🛑 Stop Loop", f"verify:stop:{label}", "danger")])
    keyboard = compact_inline_markup(rows)
    text = (
        "🔒 Verifikasi Diperlukan\n\n"
        f"Akun: {account_name}\n"
        "Buka chat Fish It, tekan tombol 🔒 Verifikasi Sekarang dari pesan Fish It, lalu tekan Sudah Verifikasi di sini.\n\n"
        "Bot akan pause akun ini sampai verifikasi selesai."
    )
    if not chat_url:
        text += "\n\nLink chat tidak bisa dibuat otomatis. Buka chat Fish It manual dan tekan tombol 🔒 Verifikasi Sekarang di sana."
    if message_text:
        text += f"\n\nPesan Fish It:\n{message_text.replace(chr(10), ' ')[:500]}"
    if not _tg_app or not _tg_app.bot:
        return
    for owner_id in owner_ids:
        try:
            await _tg_app.bot.send_message(
                chat_id=owner_id,
                text=text[:4000],
                reply_markup=keyboard,
                parse_mode=None,
            )
        except Exception as e:
            Log.p("WARN", f"{fish_log_ctx(label)} Gagal kirim notifikasi verifikasi ke {owner_id}: {e}")


async def request_manual_verification(
    verification_text: str,
    verification_msg,
    fish_app: Client = None,
    label: str = "main",
) -> bool:
    label = ctx_label(label)
    url = first_verification_url(verification_msg)
    chat_url = verification_chat_url(label, verification_msg)
    save_verification_state(label, True, url=url, message=verification_text)
    _account_private_session_active.pop(label, None)
    Log.p("WARN", f"{fish_log_ctx(label)} Verifikasi manual diperlukan; akun dipause")
    await log_event(
        "VERIFY_MANUAL",
        label,
        f"Pesan: {(verification_text or '').replace(chr(10), ' ')[:500]}\nURL: {url[:500] or '-'}",
    )
    await send_manual_verification_notice(label, url=url, message_text=verification_text, chat_url=chat_url)
    return False


async def recover_account_client_connection(fish_app: Client = None, label: str = "main", reason: str = "") -> Client | None:
    label = ctx_label(label)
    if not fish_app:
        return None
    reason = (reason or "connection lost").replace("\n", " ")[:120]
    Log.p("WARN", f"{fish_log_ctx(label)} Coba pulihkan koneksi userbot ({reason}) | {runtime_state_summary(label)}")
    try:
        if getattr(fish_app, "is_connected", False):
            await fish_app.stop()
    except Exception as stop_error:
        Log.p("WARN", f"{fish_log_ctx(label)} Gagal stop userbot saat recovery: {stop_error}")
    try:
        await fish_app.start()
        Log.p("FISH", f"{fish_log_ctx(label)} Recovery koneksi userbot berhasil | {runtime_state_summary(label)}")
        return fish_app
    except Exception as start_error:
        Log.p("ERROR", f"{fish_log_ctx(label)} Recovery koneksi userbot gagal: {start_error}")
        return None


async def recent_manual_verification_status(fish_app: Client = None, label: str = "main", limit: int = 8) -> tuple[str | None, str]:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="cek hasil verifikasi manual")
    if not fish_app:
        return None, ""
    for target in private_fish_bot_targets(label):
        try:
            async for message in fish_app.get_chat_history(target, limit=limit):
                text = await resolve_message_text(message, fish_app=fish_app)
                status = captcha_verification_status(text)
                if status:
                    return status, text or ""
        except Exception as e:
            if is_connection_lost_error(e):
                recovered = await recover_account_client_connection(fish_app=fish_app, label=label, reason=f"cek verifikasi {target}")
                if recovered:
                    fish_app = recovered
                    try:
                        async for message in fish_app.get_chat_history(target, limit=limit):
                            text = await resolve_message_text(message, fish_app=fish_app)
                            status = captcha_verification_status(text)
                            if status:
                                return status, text or ""
                    except Exception as retry_error:
                        Log.p("WARN", f"{fish_log_ctx(label)} Retry cek history hasil verifikasi gagal {target}: {retry_error}")
            Log.p("WARN", f"{fish_log_ctx(label)} Gagal cek history hasil verifikasi {target}: {e}")
    return None, ""


async def send_resume_after_manual_verification(label: str, fish_app: Client = None) -> bool:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="resume setelah verifikasi")
    if not fish_app:
        return False
    mode = current_fish_mode(label)
    _account_private_session_active.pop(label, None)

    if mode in {"special_group", "group_room", "all"}:
        pending_msg, pending = await load_pending_group_join_message(label, fish_app=fish_app)
        if pending_msg:
            source_name = pending.get("source_name") or ("grup khusus" if mode == "special_group" else "grup")
            Log.p("FISH", f"{fish_log_ctx(label, mode)} Resume verifikasi: klik ulang tombol daftar room tersimpan")
            status = await wait_and_join_group_room(
                timeout=0,
                fish_app=fish_app,
                label=label,
                group_targets=[pending["chat_id"]],
                source_name=source_name,
                initial_room_msg=pending_msg,
            )
            return status in {"joined", "group_active", "room_full"}

        if mode == "special_group":
            target = active_group_chat_target(label) or special_group_chat_target(label)
            targets = [target] if target else []
            source_name = "grup khusus"
        else:
            targets = [active_group_chat_target(label)] if active_group_chat_target(label) else fish_group_chat_targets(label)
            source_name = "grup"

        targets = [target for target in targets if target]
        if targets:
            Log.p("FISH", f"{fish_log_ctx(label, mode)} Resume verifikasi: cari ulang tombol daftar dari history {source_name}")
            status = await wait_and_join_group_room(
                timeout=0,
                fish_app=fish_app,
                label=label,
                group_targets=targets,
                source_name=source_name,
                recent_history_limit=12,
            )
            return status in {"joined", "group_active", "room_full"}

    if mode == "group_room":
        Log.p("WARN", f"{fish_log_ctx(label, mode)} Resume verifikasi: tidak ada tombol daftar room untuk diklik")
        return False
    if mode in {"private", "all"}:
        return await send_private_mancing(fish_app=fish_app, label=label, allow_all_fallback=(mode == "all"))
    return False


async def complete_manual_verification(label: str, user_id: int = 0) -> bool:
    label = ctx_label(label)
    client = await start_account_client(label)
    if not client:
        return False
    save_verification_state(label, False)
    _account_last_captcha_response_text[label] = "verifikasi manual dikonfirmasi oleh user"
    touch_activity(action="verification done", event=f"dikonfirmasi user {user_id}", label=label)
    Log.p("FISH", f"{fish_log_ctx(label)} Verifikasi manual dikonfirmasi | {runtime_state_summary(label)}")
    await log_event("VERIFY_OK", label, f"Verifikasi manual dikonfirmasi.\nOleh: {user_id}")
    resumed = await send_resume_after_manual_verification(label, fish_app=client)
    started = False
    if not _account_running.get(label):
        await start_account_loop(label, client)
        started = True
    return bool(resumed or started)


async def click_quick_verification(
    verification_text: str,
    verification_msg,
    fish_app: Client = None,
    label: str = "main",
) -> bool:
    return await request_manual_verification(
        verification_text,
        verification_msg,
        fish_app=fish_app,
        label=label,
    )


async def solve_and_click_captcha(
    captcha_text: str,
    captcha_msg,
    fish_app: Client = None,
    label: str = "main",
) -> bool:
    global _last_captcha_response_text
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="proses verifikasi")
    if not fish_app:
        return False
    _last_captcha_response_text = ""
    _account_last_captcha_response_text[label] = ""
    if is_captcha_text(captcha_text):
        return await click_quick_verification(captcha_text, captcha_msg, fish_app=fish_app, label=label)

    button_labels = extract_button_labels(captcha_msg)
    if not button_labels:
        Log.p("WARN", f"{fish_log_ctx(label)} Format CAPTCHA lama/non-verifikasi terdeteksi tapi sudah dinonaktifkan")
        return False

    Log.p("WARN", f"{fish_log_ctx(label)} CAPTCHA lama dinonaktifkan, abaikan opsi: {button_labels}")
    await log_event(
        "CAPTCHA_DISABLED",
        label,
        f"CAPTCHA lama dinonaktifkan.\nPertanyaan: {(captcha_text or '').replace(chr(10), ' ')[:500]}\n"
        f"Tombol: {', '.join(button_labels)[:500]}",
    )
    return False


def get_captcha_lock(label: str) -> asyncio.Lock:
    label = ctx_label(label)
    lock = _account_captcha_locks.get(label)
    if lock is None:
        lock = asyncio.Lock()
        _account_captcha_locks[label] = lock
    return lock


def captcha_message_key(message) -> tuple[int | str, int] | None:
    chat = getattr(message, "chat", None)
    message_id = getattr(message, "id", None)
    if not chat or not message_id:
        return None
    return (getattr(chat, "id", None) or getattr(chat, "username", "") or "private", int(message_id))


def mark_captcha_seen(label: str, message) -> bool:
    label = ctx_label(label)
    key = captcha_message_key(message)
    if key is None:
        return True
    seen = _account_captcha_seen.setdefault(label, set())
    if key in seen:
        return False
    seen.add(key)
    if len(seen) > 80:
        for old_key in list(seen)[:40]:
            seen.discard(old_key)
    return True


async def handle_private_captcha_event(message, fish_app: Client = None, label: str = "main", source: str = "watcher"):
    label = ctx_label(label)
    text = await resolve_message_text(message, fish_app=fish_app)
    if not is_captcha_text(text):
        return

    solved = await solve_captcha_event_once(text, message, fish_app=fish_app, label=label, source=source)
    if solved is None:
        return
    if solved:
        inc_stat("captcha_solved", label=label)
        await notify(f"✅ [{label}] Verifikasi selesai. Loop lanjut.")
        return

    inc_stat("captcha_failed", label=label)
    audit_log(label, "captcha_failed", f"private captcha watcher/{source}", user_id=0)
    await notify(
        f"⚠️ [{label}] Verifikasi muncul.\n"
        "Selesaikan manual lewat tombol yang dikirim, lalu tekan Sudah Verifikasi."
    )


async def solve_captcha_event_once(
    captcha_text: str,
    captcha_msg,
    fish_app: Client = None,
    label: str = "main",
    source: str = "flow",
) -> bool | None:
    label = ctx_label(label)
    if not mark_captcha_seen(label, captcha_msg):
        return None

    lock = get_captcha_lock(label)
    async with lock:
        Log.p("WARN", f"{fish_log_ctx(label)} Verifikasi terdeteksi oleh {source}, minta verifikasi manual")
        touch_activity(action=f"captcha {source}", event=(captcha_text or "").replace("\n", " ")[:80], label=label)
        return await solve_and_click_captcha(captcha_text, captcha_msg, fish_app=fish_app, label=label)


def ensure_private_captcha_watcher(label: str, fish_app: Client = None):
    label = ctx_label(label)
    if fish_app is None or label in _account_captcha_handlers:
        return

    handler_group = alloc_handler_group()

    async def _handler(client, message):
        await handle_private_captcha_event(message, fish_app=fish_app, label=label, source="global_private")

    handlers = [
        MessageHandler(_handler, private_fish_bot_filter(label) & filters.incoming),
        EditedMessageHandler(_handler, private_fish_bot_filter(label)),
    ]
    for handler in handlers:
        fish_app.add_handler(handler, group=handler_group)

    _account_captcha_handlers[label] = [(handler, handler_group) for handler in handlers]
    Log.p("BOT", f"[{label}] Private verifikasi watcher aktif")


def remove_private_captcha_watcher(label: str, fish_app: Client = None):
    label = ctx_label(label)
    handlers = _account_captcha_handlers.pop(label, [])
    target_app = fish_app or _account_clients.get(label)
    for handler, group in handlers:
        safe_remove_handler(handler, group=group, fish_app=target_app)
    _account_captcha_seen.pop(label, None)
    if handlers:
        Log.p("BOT", f"[{label}] Private verifikasi watcher dilepas")


