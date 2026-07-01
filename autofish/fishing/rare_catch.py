from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def extract_rare_catch_rarity(text: str) -> str | None:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return None
    head = lines[:4]
    if not any("berat:" in normalize_fish_name(line) for line in lines[:8]):
        return None
    if not any("nilai:" in normalize_fish_name(line) for line in lines[:8]):
        return None

    for line in head:
        tl = normalize_fish_name(line).replace("_", " ")
        if "secret shiny" in tl:
            return "SECRET SHINY"
        if "secret" in tl:
            return "SECRET"
        if "celestial" in tl:
            return "CELESTIAL"
    return None


def rare_source_bot_usernames() -> set[str]:
    usernames = set()
    for raw in [FISH_BOT_USERNAME, *split_chat_targets(PRIVATE_FISH_BOT_USERNAMES)]:
        username = normalize_bot_username(raw).lstrip("@").lower()
        if username:
            usernames.add(username)
    return usernames


def message_from_fish_bot(message) -> bool:
    allowed = rare_source_bot_usernames()
    for attr in ("from_user", "sender_chat"):
        sender = getattr(message, attr, None)
        username = str(getattr(sender, "username", "") or "").lstrip("@").lower()
        if username and username in allowed:
            return True
    return False


def extract_rare_catch_player(text: str) -> str:
    for raw_line in (text or "").splitlines()[:6]:
        line = raw_line.strip()
        tl = normalize_fish_name(line)
        if "mendapatkan" not in tl:
            continue
        before = re.split(r"\bmendapatkan\b", line, maxsplit=1, flags=re.I)[0].strip()
        before = re.sub(r"^[^\w@]+", "", before, flags=re.UNICODE).strip()
        return before[:80] or "-"
    return "-"


def message_public_link(message) -> str | None:
    chat = getattr(message, "chat", None)
    chat_type = str(getattr(chat, "type", "") or "").lower()
    if "private" in chat_type:
        return None
    direct_link = str(getattr(message, "link", "") or "").strip()
    if direct_link.startswith("https://t.me/"):
        return direct_link
    message_id = int(getattr(message, "id", 0) or 0)
    if not chat or not message_id:
        return None
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    chat_id = getattr(chat, "id", None)
    if isinstance(chat_id, int) and str(chat_id).startswith("-100"):
        return f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"
    return None


def rare_catch_keyboard(message) -> InlineKeyboardMarkup | None:
    link = message_public_link(message)
    if not link:
        return None
    return compact_inline_markup([[InlineKeyboardButton("Buka Pesan", url=link)]])


def rare_catch_chat_name(message, source: str) -> str:
    if source == "private":
        return "Private"
    chat = getattr(message, "chat", None)
    if not chat:
        return "-"
    for attr in ("title", "username", "first_name"):
        value = str(getattr(chat, attr, "") or "").strip()
        if value:
            return value
    return str(getattr(chat, "id", "") or "-")


def rare_catch_userbot_name(user_info: dict, label: str) -> str:
    first = str(user_info.get("first_name", "") or "").strip()
    last = str(user_info.get("last_name", "") or "").strip()
    username = str(user_info.get("username", "") or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip()
    if username and full_name:
        return f"{full_name} (@{username})"
    if username:
        return f"@{username}"
    if full_name:
        return full_name
    user_id = safe_user_id(user_info.get("id"))
    return str(user_id or ctx_label(label))


async def rare_catch_context(label: str, rarity: str, source: str, message, fish_app: Client) -> dict:
    label = ctx_label(label)
    user_info = await get_rare_catch_user_info(fish_app, label)
    return {
        "account": f"{account_name_for_label(label)} ({label})",
        "player": extract_rare_catch_player(await resolve_message_text(message, fish_app=fish_app)) if source != "private" else account_name_for_label(label),
        "mode": "Private" if source == "private" else "Grup",
        "rarity": str(rarity or "-"),
        "group": rare_catch_chat_name(message, source),
        "reader": f"{rare_catch_userbot_name(user_info, label)} ({label})",
    }


def rare_catch_plain_text(context: dict, body: str) -> str:
    body = (body or "").strip() or "-"
    identity_label = "Player" if context.get("mode") == "Grup" else "Akun"
    identity_value = context.get("player") if identity_label == "Player" else context.get("account")
    header = (
        "🌟 Rare Catch\n"
        f"{identity_label}: {identity_value or '-'}\n"
        f"Mode: {context.get('mode', '-')}\n"
        f"Rarity: {context.get('rarity', '-')}\n"
        f"Grup: {context.get('group', '-')}\n"
        f"Terbaca oleh: {context.get('reader', '-')}"
    )
    return f"{header}\n\n{body}"[:4000]


async def get_rare_catch_user_info(fish_app: Client, label: str) -> dict:
    label = ctx_label(label)
    cached = _rare_catch_user_cache.get(label)
    if cached:
        return cached
    try:
        me = await fish_app.get_me()
        info = {
            "id": int(getattr(me, "id", 0) or 0),
            "first_name": str(getattr(me, "first_name", "") or "").strip(),
            "last_name": str(getattr(me, "last_name", "") or "").strip(),
            "username": str(getattr(me, "username", "") or "").strip(),
        }
    except Exception:
        account = load_account(label)
        tg_user = account.get("telegram_user") or {}
        info = {
            "id": safe_user_id(tg_user.get("id")),
            "first_name": str(tg_user.get("first_name") or "").strip(),
            "last_name": str(tg_user.get("last_name") or "").strip(),
            "username": str(tg_user.get("username") or "").strip(),
        }
    _rare_catch_user_cache[label] = info
    return info


def message_mentions_user(message, user_id: int) -> bool:
    if not user_id:
        return False
    entities = []
    entities.extend(getattr(message, "entities", None) or [])
    entities.extend(getattr(message, "caption_entities", None) or [])
    for entity in entities:
        user = getattr(entity, "user", None)
        if safe_user_id(getattr(user, "id", 0)) == user_id:
            return True
    return False


def group_rare_text_matches_user(text: str, user_info: dict) -> bool:
    tl = normalize_fish_name(text)
    if "mendapatkan" not in tl:
        return False
    names = [
        user_info.get("first_name", ""),
        " ".join(part for part in [user_info.get("first_name", ""), user_info.get("last_name", "")] if part).strip(),
        user_info.get("username", ""),
    ]
    names = [normalize_fish_name(name.lstrip("@")) for name in names if normalize_fish_name(name.lstrip("@"))]
    if not names:
        return False
    for line in (text or "").splitlines()[:5]:
        line_tl = normalize_fish_name(line).lstrip("@")
        if "mendapatkan" in line_tl and any(name in line_tl for name in names):
            return True
    return False


async def rare_catch_belongs_to_account(message, text: str, fish_app: Client, label: str, source: str) -> bool:
    if source == "private":
        return True
    user_info = await get_rare_catch_user_info(fish_app, label)
    return message_mentions_user(message, safe_user_id(user_info.get("id"))) or group_rare_text_matches_user(text, user_info)


def message_has_sendable_media(message) -> bool:
    return any(getattr(message, attr, None) for attr in ("photo", "animation", "video", "document"))


def rare_catch_media_filename(message, path: str) -> str:
    media = (
        getattr(message, "animation", None)
        or getattr(message, "video", None)
        or getattr(message, "document", None)
        or getattr(message, "photo", None)
    )
    file_name = str(getattr(media, "file_name", "") or "").strip()
    if file_name:
        return file_name
    suffix = Path(path).suffix.lower()
    if suffix:
        return f"rare_catch{suffix}"
    document = getattr(message, "document", None)
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    if mime_type == "image/gif":
        return "rare_catch.gif"
    if mime_type == "video/mp4" or getattr(message, "animation", None) or getattr(message, "video", None):
        return "rare_catch.mp4"
    return "rare_catch"


def rare_catch_media_is_animation(message, path: str) -> bool:
    if getattr(message, "animation", None):
        return True
    document = getattr(message, "document", None)
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    file_name = rare_catch_media_filename(message, path).lower()
    if mime_type in {"image/gif", "video/mp4", "video/gif"}:
        return True
    if file_name.endswith((".gif", ".mp4", ".m4v")):
        return True
    for attr in getattr(document, "attributes", None) or []:
        attr_name = type(attr).__name__.lower()
        if "animated" in attr_name or "animation" in attr_name:
            return True
    return False


async def send_rare_catch_media(bot: Bot, owner_id: int, path: str, message, caption: str, reply_markup=None):
    filename = rare_catch_media_filename(message, path)
    with open(path, "rb") as media:
        input_media = InputFile(media, filename=filename)
        if getattr(message, "photo", None):
            return await bot.send_photo(chat_id=owner_id, photo=input_media, caption=caption[:1024], reply_markup=reply_markup)
        if rare_catch_media_is_animation(message, path):
            return await bot.send_animation(chat_id=owner_id, animation=input_media, caption=caption[:1024], reply_markup=reply_markup)
        if getattr(message, "video", None):
            return await bot.send_video(chat_id=owner_id, video=input_media, caption=caption[:1024], reply_markup=reply_markup)
        return await bot.send_document(chat_id=owner_id, document=input_media, caption=caption[:1024], reply_markup=reply_markup)


async def send_rare_catch_to_owners(message, text: str, rarity: str, fish_app: Client, label: str, source: str):
    if not _tg_app or not _tg_app.bot:
        return
    account = load_account(label)
    owner_ids = account_notification_owner_ids(account, label)
    if not owner_ids:
        return

    context = await rare_catch_context(label, rarity, source, message, fish_app)
    notify_text = rare_catch_plain_text(context, text)
    reply_markup = rare_catch_keyboard(message)
    media_path = None

    try:
        if message_has_sendable_media(message):
            try:
                media_path = await message.download(file_name=str(Path("/tmp") / f"fishit_rare_{label}_{getattr(message, 'id', 0)}_"))
            except Exception as e:
                Log.p("WARN", f"{fish_log_ctx(label)} Download media rare catch gagal, kirim teks saja: {e}")
                await log_rare_catch_error(label, source, e)
        for owner_id in owner_ids:
            try:
                if media_path:
                    await send_rare_catch_media(_tg_app.bot, owner_id, media_path, message, notify_text, reply_markup=reply_markup)
                else:
                    await _tg_app.bot.send_message(chat_id=owner_id, text=notify_text, reply_markup=reply_markup)
                await asyncio.sleep(0.08)
            except Exception as e:
                Log.p("WARN", f"{fish_log_ctx(label)} Gagal kirim rare catch ke {owner_id}: {e}")
                await log_rare_catch_error(label, source, e)
                try:
                    await _tg_app.bot.send_message(chat_id=owner_id, text=notify_text, reply_markup=reply_markup)
                except Exception as e2:
                    Log.p("WARN", f"{fish_log_ctx(label)} Fallback rare catch gagal ke {owner_id}: {e2}")
                    await log_rare_catch_error(label, source, e2)
    finally:
        if media_path:
            try:
                Path(media_path).unlink(missing_ok=True)
            except Exception:
                pass


async def log_rare_catch_event(label: str, rarity: str, source: str, text: str, message, fish_app: Client):
    context = await rare_catch_context(label, rarity, source, message, fish_app)
    preview = " ".join((text or "").split())[:900] or "-"
    identity_label = "Player" if context.get("mode") == "Grup" else "Akun"
    identity_value = context.get("player") if identity_label == "Player" else context.get("account")
    detail = (
        f"🌟 <b>Rare Catch</b>\n\n"
        f"{blockquote(f'{identity_label}: {identity_value or "-"}')}\n"
        f"{blockquote(f'Mode: {context.get("mode", "-")}')}\n"
        f"{blockquote(f'Rarity: {context.get("rarity", "-")}')}\n"
        f"{blockquote(f'Grup: {context.get("group", "-")}')}\n"
        f"{blockquote(f'Terbaca oleh: {context.get("reader", "-")}')}\n"
        f"{blockquote(f'Pesan: {preview}')}"
    )
    await send_log_chat_message(detail, reply_markup=rare_catch_keyboard(message))


async def log_rare_catch_error(label: str, source: str, error: Exception):
    await send_log_chat_message(
        "⚠️ <b>Rare Catch Notify Error</b>\n\n"
        + blockquote(
            f"Akun: {account_name_for_label(label)} ({ctx_label(label)})\n"
            f"Mode: {'Private' if source == 'private' else 'Grup'}\n"
            f"Error: {str(error)[:900]}"
        )
    )


async def maybe_notify_rare_catch(message, fish_app: Client, label: str, source: str):
    try:
        label = ctx_label(label)
        text = await resolve_message_text(message, fish_app=fish_app)
        rarity = extract_rare_catch_rarity(text)
        if not rarity:
            return
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", "-") if chat else "-"
        message_id = getattr(message, "id", "-")
        if source != "private" and not message_from_fish_bot(message):
            return

        owned_by_account = await rare_catch_belongs_to_account(message, text, fish_app, label, source)
        log_key = f"{source}:{chat_id}:{message_id}"
        notify_key = f"{label}:{chat_id}:{message_id}"
        should_log = source == "private" or log_key not in _rare_catch_log_seen
        should_notify_owner = owned_by_account and notify_key not in _rare_catch_notify_seen

        if not should_log and not should_notify_owner:
            return
        if should_log:
            _rare_catch_log_seen.add(log_key)
            if len(_rare_catch_log_seen) > 1000:
                _rare_catch_log_seen.clear()
                _rare_catch_log_seen.add(log_key)
        if should_notify_owner:
            _rare_catch_notify_seen.add(notify_key)
            if len(_rare_catch_notify_seen) > 1000:
                _rare_catch_notify_seen.clear()
                _rare_catch_notify_seen.add(notify_key)
        Log.p("NOTIF", f"{fish_log_ctx(label)} Rare catch {rarity} terdeteksi dari {source}")
        if should_log:
            asyncio.create_task(log_rare_catch_event(label, rarity, source, text, message, fish_app))
        if should_notify_owner:
            asyncio.create_task(send_rare_catch_to_owners(message, text, rarity, fish_app, label, source))
    except Exception as e:
        Log.p("WARN", f"{fish_log_ctx(label)} Rare catch notify gagal: {e}")
        asyncio.create_task(log_rare_catch_error(label, source, e))


