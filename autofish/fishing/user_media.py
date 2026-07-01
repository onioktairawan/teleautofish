from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def user_log_media_type(message) -> str | None:
    for attr in USER_LOG_MEDIA_ATTRS:
        if getattr(message, attr, None):
            return attr
    return None


def user_log_display_name(user) -> str:
    if not user:
        return "-"
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    username = str(getattr(user, "username", "") or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip()
    return full_name or (f"@{username}" if username else str(getattr(user, "id", "") or "-"))


def user_log_open_link(user_id: int | str) -> str:
    return f"tg://openmessage?user_id={int(user_id or 0)}"


async def user_log_recipient_info(client: Client, label: str) -> dict:
    label = ctx_label(label)
    cached = _account_user_log_identity.get(label)
    if cached:
        return cached
    me = await client.get_me()
    info = {
        "id": int(getattr(me, "id", 0) or 0),
        "name": user_log_display_name(me),
    }
    _account_user_log_identity[label] = info
    return info


def format_user_media_log_caption(recipient: dict, sender, text: str) -> str:
    sender_id = int(getattr(sender, "id", 0) or 0)
    sender_name = user_log_display_name(sender)
    recipient_id = int(recipient.get("id", 0) or 0)
    recipient_name = str(recipient.get("name") or "-")
    body = (text or "").strip() or "-"
    if len(body) > 500:
        body = body[:497] + "..."
    return (
        "#USER_LOG\n"
        f'Penerima: <a href="{user_log_open_link(recipient_id)}">{html.escape(recipient_name)}</a>\n'
        f"ID Penerima: {recipient_id}\n"
        f'Pengirim: <a href="{user_log_open_link(sender_id)}">{html.escape(sender_name)}</a>\n'
        f"ID Pengirim: {sender_id}\n"
        f"Text: {html.escape(body)}"
    )[:1024]


async def send_user_media_log(media_path: str, media_type: str, caption: str):
    if not _tg_app or not _tg_app.bot or not LOG_BACKUP:
        return

    with open(media_path, "rb") as media_file:
        input_media = InputFile(media_file, filename=Path(media_path).name)
        if media_type == "photo":
            await _tg_app.bot.send_photo(chat_id=LOG_BACKUP, photo=input_media, caption=caption, parse_mode="HTML")
        elif media_type == "video":
            await _tg_app.bot.send_video(chat_id=LOG_BACKUP, video=input_media, caption=caption, parse_mode="HTML")
        elif media_type == "voice":
            await _tg_app.bot.send_voice(chat_id=LOG_BACKUP, voice=input_media, caption=caption, parse_mode="HTML")
        elif media_type == "audio":
            await _tg_app.bot.send_audio(chat_id=LOG_BACKUP, audio=input_media, caption=caption, parse_mode="HTML")
        elif media_type == "animation":
            await _tg_app.bot.send_animation(chat_id=LOG_BACKUP, animation=input_media, caption=caption, parse_mode="HTML")
        elif media_type == "video_note":
            await _tg_app.bot.send_video_note(chat_id=LOG_BACKUP, video_note=input_media)
            await _tg_app.bot.send_message(chat_id=LOG_BACKUP, text=caption, parse_mode="HTML")
        elif media_type == "sticker":
            await _tg_app.bot.send_sticker(chat_id=LOG_BACKUP, sticker=input_media)
            await _tg_app.bot.send_message(chat_id=LOG_BACKUP, text=caption, parse_mode="HTML")
        else:
            await _tg_app.bot.send_document(chat_id=LOG_BACKUP, document=input_media, caption=caption, parse_mode="HTML")


def user_media_log_debug(label: str, stage: str, message=None, extra: str = ""):
    chat = getattr(message, "chat", None) if message else None
    chat_id = getattr(chat, "id", "-") if chat else "-"
    chat_type = getattr(chat, "type", "-") if chat else "-"
    msg_id = getattr(message, "id", "-") if message else "-"
    sender = getattr(message, "from_user", None) if message else None
    sender_id = getattr(sender, "id", "-") if sender else "-"
    sender_name = user_log_display_name(sender) if sender else "-"
    media_type = user_log_media_type(message) if message else None
    note = f" | {extra}" if extra else ""
    Log.p(
        "BOT",
        f"[USER_MEDIA_DEBUG][{ctx_label(label)}] {stage} | chat={chat_id} type={chat_type} msg={msg_id} sender={sender_name}({sender_id}) media={media_type or '-'}{note}",
    )


async def handle_user_media_log(client: Client, message, label: str):
    if not LOG_BACKUP or not _tg_app or not _tg_app.bot:
        user_media_log_debug(label, "skip-no-backup", message, "LOG_BACKUP atau bot belum siap")
        return
    if getattr(getattr(message, "chat", None), "type", None) != enums.ChatType.PRIVATE:
        user_media_log_debug(label, "skip-not-private", message)
        return

    recipient = await user_log_recipient_info(client, label)
    sender = getattr(message, "from_user", None)
    sender_id = safe_user_id(getattr(sender, "id", 0))
    recipient_id = safe_user_id(recipient.get("id", 0))
    if sender_id and recipient_id and sender_id == recipient_id:
        user_media_log_debug(label, "skip-outgoing-self", message)
        return

    user_media_log_debug(label, "incoming-private", message, f"inferred_incoming={bool(sender_id and sender_id != recipient_id)}")
    media_type = user_log_media_type(message)
    if not media_type:
        user_media_log_debug(label, "skip-no-media", message)
        return

    try:
        caption = format_user_media_log_caption(recipient, sender, message.caption or "")
        sender_id = getattr(sender, "id", 0) if sender else 0
        Log.p("BOT", f"[{label}] User media log terdeteksi: {media_type} dari {sender_id or '-'}")
        with tempfile.TemporaryDirectory(prefix="fishit_user_log_") as tmp_dir:
            try:
                media_path = await message.download(file_name=tmp_dir + os.sep)
            except FloodWait as e:
                wait = int(getattr(e, "value", 5)) + 1
                Log.p("WARN", f"FloodWait {wait}s saat download media, tunggu...")
                await asyncio.sleep(wait)
                media_path = await message.download(file_name=tmp_dir + os.sep)
            
            if not media_path:
                user_media_log_debug(label, "skip-download-failed", message)
                return
            user_media_log_debug(label, "downloaded", message, f"path={media_path}")
            await send_user_media_log(media_path, media_type, caption)
        Log.p("BOT", f"[{label}] User media log terkirim: {media_type} dari {sender_id or '-'}")
    except Exception as e:
        user_media_log_debug(label, "error", message, str(e))
        Log.p("WARN", f"[{label}] Gagal kirim user media log: {e}")


def ensure_user_media_log_watcher(label: str, fish_app: Client = None):
    label = ctx_label(label)
    if fish_app is None or label in _account_user_log_handlers:
        return

    handler_group = alloc_handler_group()

    async def _handler(client, message):
        await handle_user_media_log(client, message, label)

    handler = MessageHandler(_handler, filters.private)
    fish_app.add_handler(handler, group=handler_group)
    _account_user_log_handlers[label] = (handler, handler_group)
    if LOG_BACKUP:
        Log.p("BOT", f"[{label}] User media log watcher aktif")


def remove_user_media_log_watcher(label: str, fish_app: Client = None):
    label = ctx_label(label)
    handler_info = _account_user_log_handlers.pop(label, None)
    target_app = fish_app or _account_clients.get(label)
    if handler_info:
        handler, group = handler_info
        safe_remove_handler(handler, group=group, fish_app=target_app)
    _account_user_log_identity.pop(label, None)


async def start_user_media_log_clients():
    started = []
    skipped = []
    for account in load_all_accounts():
        label = ctx_label(account.get("label", "main"))
        if label == "main":
            continue
        if not account.get("enabled", True):
            skipped.append(f"{label} (disabled)")
            continue
        if account.get("restored_needs_login") or account.get("last_login_error"):
            skipped.append(f"{label} (perlu login)")
            continue
        client = await start_account_client(label)
        if client:
            started.append(label)
            user_media_log_debug(label, "watcher-ready", None, "client aktif")

    if started:
        Log.p("BOT", f"User media log aktif untuk: {', '.join(started)}")
    if skipped:
        Log.p("WARN", f"User media log dilewati karena perlu login ulang: {', '.join(skipped)}")


