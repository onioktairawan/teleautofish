from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def normalize_button_text(text: str) -> str:
    text = normalize_fish_name(text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_group_room_message(message) -> bool:
    text = message.text or message.caption or ""
    tl = normalize_fish_name(text)
    required_keywords = [
        "pendaftaran dibuka",
        "peserta:",
        "auto mancing",
    ]
    return all(keyword in tl for keyword in required_keywords)


def extract_start_command_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    query = parse_qs(parsed.query or "")

    if parsed.scheme == "tg" and host == "resolve":
        bot_username = (query.get("domain") or [""])[0].strip()
        payload = (query.get("start") or query.get("startgroup") or [""])[0].strip()
        if not bot_username:
            return None
        command = f"/start {payload}" if payload else "/start"
        return f"@{bot_username}", command

    if host not in {"t.me", "telegram.me"}:
        return None

    bot_username = (parsed.path or "").strip("/")
    if not bot_username:
        return None

    payload = (query.get("start") or query.get("startgroup") or [""])[0].strip()
    command = f"/start {payload}" if payload else "/start"
    return f"@{bot_username}", command


def extract_group_room_start_command(message) -> tuple[str, str] | None:
    if not message or not getattr(message, "reply_markup", None):
        return None
    for row in (message.reply_markup.inline_keyboard or []):
        for btn in row:
            if "daftar mancing" not in normalize_button_text(btn.text or ""):
                continue
            url = getattr(btn, "url", None)
            if not url:
                continue
            start_command = extract_start_command_from_url(url)
            if start_command:
                return start_command
    return None


def classify_group_join_reply(text: str) -> str | None:
    tl = normalize_fish_name(text)
    if "sedang memancing di grup" in tl or "tunggu sesi grup selesai" in tl:
        return "group_active"
    if "inventory penuh" in tl or "jual ikan dulu" in tl:
        return "inventory_full"
    if "pendaftaran penuh" in tl or "vip user masih bisa join" in tl:
        return "room_full"
    if "pendaftaran berhasil" in tl or "peserta ke-" in tl or "grup:" in tl:
        return "joined"
    if "verifikasi berhasil" in tl or "jawaban benar" in tl or "gunakan /mancing" in tl:
        return "verified_retry"
    if is_captcha_text(text):
        return "captcha"
    return None


async def click_group_room_join_button(message, fish_app: Client = None, label: str = "main") -> bool:
    label = ctx_label(label)
    if not mark_action_once(label, message, "click_join_room"):
        Log.p("FISH", f"{fish_log_ctx(label)} Klik join room diabaikan karena sudah dilakukan untuk pesan ini")
        return True
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="klik room grup")
    if not fish_app:
        return False
    if not message or not message.reply_markup:
        return False

    for y, row in enumerate(message.reply_markup.inline_keyboard or []):
        for x, btn in enumerate(row):
            button_label = btn.text or ""
            normalized = normalize_button_text(button_label)
            if "daftar mancing" not in normalized:
                continue
            url = getattr(btn, "url", None)
            start_command = extract_start_command_from_url(url) if url else None
            try:
                await message.click(x, y, timeout=10)
                Log.p("FISH", f"{fish_log_ctx(label)} Klik tombol room grup: {button_label}")
                if start_command:
                    bot_username, command = start_command
                    Log.p("FISH", f"{fish_log_ctx(label)} Deep-link room terdeteksi, kirim {command.split()[0]} ke {bot_username}")
                    await safe_send(bot_username, command, fish_app=fish_app, label=label)
                return True
            except TimeoutError:
                Log.p("WARN", f"{fish_log_ctx(label)} Klik tombol daftar mancing timeout, cek notif pendaftaran")
                if start_command:
                    bot_username, command = start_command
                    await safe_send(bot_username, command, fish_app=fish_app, label=label)
                return True
            except Exception as e:
                Log.p("WARN", f"{fish_log_ctx(label)} Gagal klik tombol daftar mancing: {e}")
                if start_command:
                    bot_username, command = start_command
                    Log.p("FISH", f"{fish_log_ctx(label)} Fallback deep-link, kirim {command.split()[0]} ke {bot_username}")
                    await safe_send(bot_username, command, fish_app=fish_app, label=label)
                    return True
                return False

    return False


def remember_pending_group_join(label: str, room_msg, source_name: str = "grup"):
    label = ctx_label(label)
    chat = getattr(room_msg, "chat", None)
    message_id = getattr(room_msg, "id", None)
    chat_id = getattr(chat, "id", None)
    if not chat_id or not message_id:
        return
    _account_pending_group_join[label] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "source_name": source_name,
        "saved_at": time.monotonic(),
    }


def clear_pending_group_join(label: str):
    _account_pending_group_join.pop(ctx_label(label), None)


async def load_pending_group_join_message(label: str, fish_app: Client = None):
    label = ctx_label(label)
    pending = _account_pending_group_join.get(label) or {}
    chat_id = pending.get("chat_id")
    message_id = pending.get("message_id")
    saved_at = pending.get("saved_at", 0)
    if saved_at and time.monotonic() - float(saved_at) > 900:
        Log.p("WARN", f"{fish_log_ctx(label)} Pending join room kedaluwarsa, dibersihkan")
        clear_pending_group_join(label)
        return None, {}
    if not chat_id or not message_id:
        return None, pending
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="ambil ulang room grup")
    if not fish_app:
        return None, pending
    try:
        message = await fish_app.get_messages(chat_id, message_id)
        if has_group_room_join_button(message):
            return message, pending
    except Exception as e:
        Log.p("WARN", f"{fish_log_ctx(label)} Gagal ambil ulang room grup setelah verifikasi: {e}")
    clear_pending_group_join(label)
    return None, pending


async def wait_and_join_group_room(
    timeout: int = 300,
    fish_app: Client = None,
    label: str = "main",
    group_targets: list[int | str] = None,
    source_name: str = "grup",
    recent_history_limit: int = 0,
    initial_room_msg=None,
) -> str | None:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action=f"tunggu/join room {source_name}")
    if not fish_app:
        return None
    group_targets = group_targets or fish_group_chat_targets(label)
    if not group_targets:
        Log.p("WARN", f"{fish_log_ctx(label)} Belum ada {source_name} mancing yang dikonfigurasi")
        return None

    room_msg = initial_room_msg
    if room_msg:
        Log.p("FISH", f"{fish_log_ctx(label)} Pakai room {source_name} yang sudah terdeteksi")
    if not room_msg and recent_history_limit > 0:
        for target in group_targets:
            try:
                async for message in fish_app.get_chat_history(target, limit=recent_history_limit):
                    text = message.text or message.caption or ""
                    if is_special_group_done_text(text) or is_special_group_active_text(text):
                        break
                    if has_group_room_join_button(message):
                        room_msg = message
                        Log.p("FISH", f"{fish_log_ctx(label)} Room {source_name} ditemukan dari history terbaru")
                        break
            except Exception as e:
                Log.p("WARN", f"{fish_log_ctx(label)} Gagal cek history {source_name}: {e}")
            if room_msg:
                break

    if not room_msg:
        result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        handler_group = alloc_handler_group()

        async def _handler(client, message):
            if is_command_mode(label) or result_queue.full():
                return
            text = message.text or message.caption or ""
            if is_special_group_mode(label) and message.chat:
                observe_special_boost_message(message.chat.id, text, label=label)
            if not message.reply_markup:
                return
            if not is_group_room_message(message):
                return
            for row in (message.reply_markup.inline_keyboard or []):
                for btn in row:
                    if "daftar mancing" in normalize_button_text(btn.text or ""):
                        await result_queue.put(message)
                        return

        handler = MessageHandler(
            _handler,
            filters.chat(group_targets) & filters.incoming,
        )
        fish_app.add_handler(handler, group=handler_group)

        try:
            Log.p("FISH", f"{fish_log_ctx(label)} Menunggu room {source_name} dengan tombol daftar mancing ({len(group_targets)} grup)...")
            room_msg = await asyncio.wait_for(result_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            Log.p("WARN", f"{fish_log_ctx(label)} Timeout menunggu room {source_name}")
            return None
        finally:
            safe_remove_handler(handler, group=handler_group, fish_app=fish_app)

    room_chat = room_msg.chat.id if room_msg.chat else None
    join_target = room_chat or (group_targets[0] if group_targets else None)
    room_start_command = extract_group_room_start_command(room_msg)

    join_keywords = [
        "pendaftaran berhasil",
        "peserta ke-",
        "grup:",
        "pendaftaran penuh",
        "vip user masih bisa join",
        "inventory penuh",
        "jual ikan dulu",
        "sedang memancing di grup",
        "tunggu sesi grup selesai",
        "verifikasi berhasil",
        "jawaban benar",
        "gunakan /mancing",
        *CAPTCHA_KEYWORDS,
    ]

    async def _join_attempt(attempt: int, use_start_command: bool = False) -> tuple[str | None, str]:
        if verification_required(label):
            if is_special_group_mode(label):
                mark_special_join_failed(join_target, label, "menunggu verifikasi manual")
            return None, "menunggu verifikasi manual"

        join_reply_task = asyncio.create_task(wait_for_bot_message(
            keywords=join_keywords,
            timeout=30,
            fish_app=fish_app,
            label=label,
        ))
        await asyncio.sleep(0)

        sent_join = False
        if use_start_command and room_start_command:
            bot_username, command = room_start_command
            Log.p("FISH", f"{fish_log_ctx(label)} Retry daftar room via deep-link setelah sell: {command.split()[0]} ke {bot_username}")
            sent_join = await safe_send(bot_username, command, fish_app=fish_app, label=label)
        else:
            sent_join = await click_group_room_join_button(room_msg, fish_app=fish_app, label=label)

        if not sent_join:
            await cancel_task_safely(join_reply_task, label=label, reason="cancel wait join reply")
            Log.p("WARN", f"{fish_log_ctx(label)} Tidak menemukan/gagal kirim daftar attempt {attempt}")
            if is_special_group_mode(label):
                mark_special_join_failed(join_target, label, f"attempt {attempt}: gagal kirim daftar")
            return None, ""

        join_msg = await join_reply_task
        if not join_msg:
            Log.p("WARN", f"{fish_log_ctx(label)} Klik daftar attempt {attempt} tidak mendapat balasan status")
            if is_special_group_mode(label):
                mark_special_join_failed(join_target, label, f"attempt {attempt}: tidak ada balasan status")
            return None, ""

        join_reply = join_msg.text or join_msg.caption or ""
        preview = join_reply.replace("\n", " ")[:80]
        status = classify_group_join_reply(join_reply)
        Log.p("FISH", f"{fish_log_ctx(label)} Status daftar attempt {attempt}: {status or 'unknown'} | {preview or '-'}")
        if status != "captcha":
            return status, preview

        Log.p("WARN", f"{fish_log_ctx(label)} Verifikasi muncul saat daftar grup attempt {attempt}")
        remember_pending_group_join(label, room_msg, source_name=source_name)
        solved = await solve_captcha_event_once(join_reply, join_msg, fish_app=fish_app, label=label, source="join_group")
        if not solved:
            if solved is False:
                inc_stat("captcha_failed", label=label)
                audit_log(label, "captcha_failed", "daftar grup", user_id=0)
                Log.p("WARN", f"{fish_log_ctx(label)} Verifikasi daftar grup menunggu tindakan manual")
                if is_special_group_mode(label):
                    mark_special_join_failed(join_target, label, "menunggu verifikasi manual")
                return None, preview

            wait_until = time.monotonic() + 5
            while time.monotonic() < wait_until:
                last_captcha_response = _account_last_captcha_response_text.get(label, _last_captcha_response_text)
                captcha_status = classify_group_join_reply(last_captcha_response)
                if captcha_status and captcha_status != "captcha":
                    return captcha_status, last_captcha_response.replace("\n", " ")[:80]
                await asyncio.sleep(0.25)

        if solved:
            inc_stat("captcha_solved", label=label)
        last_captcha_response = _account_last_captcha_response_text.get(label, _last_captcha_response_text)
        captcha_status = classify_group_join_reply(last_captcha_response)
        if captcha_status and captcha_status != "captcha":
            return captcha_status, last_captcha_response.replace("\n", " ")[:80]

        followup_msg = await wait_for_bot_message(
            keywords=join_keywords,
            timeout=30,
            fish_app=fish_app,
            label=label,
        )
        if not followup_msg:
            Log.p("WARN", f"{fish_log_ctx(label)} Tidak ada status pendaftaran setelah verifikasi")
            return None, preview

        followup_reply = followup_msg.text or followup_msg.caption or ""
        return classify_group_join_reply(followup_reply), followup_reply.replace("\n", " ")[:80]

    inventory_cleaned = False
    retry_join_via_start = False
    for attempt in range(1, 4):
        status, preview = await _join_attempt(attempt, use_start_command=retry_join_via_start)
        retry_join_via_start = False

        if status == "joined":
            Log.p("FISH", f"{fish_log_ctx(label)} Pendaftaran room berhasil: {preview}")
            if is_special_group_mode(label):
                mark_special_join_success(join_target, label)
            touch_activity(action="join group room", event="pendaftaran berhasil", label=label)
            _account_group_active[label] = True
            clear_pending_group_join(label)
            set_active_group_chat(label, room_chat)
            return "joined"

        if status == "group_active":
            Log.p("FISH", f"{fish_log_ctx(label)} Sudah sedang memancing di grup: {preview}")
            if is_special_group_mode(label):
                mark_special_join_success(join_target, label)
            touch_activity(action="group session active", event="sedang memancing di grup", label=label)
            _account_group_active[label] = True
            clear_pending_group_join(label)
            set_active_group_chat(label, room_chat)
            return "group_active"

        if status == "room_full":
            Log.p("WARN", f"{fish_log_ctx(label)} Room grup penuh: {preview}")
            if is_special_group_mode(label):
                mark_special_join_failed(join_target, label, "room penuh")
            touch_activity(action="group room full", event="pendaftaran penuh", label=label)
            clear_pending_group_join(label)
            return "room_full"

        if status == "inventory_full":
            Log.p("WARN", f"{fish_log_ctx(label)} Inventory penuh saat daftar grup: {preview}")
            if is_special_group_mode(label):
                mark_special_join_failed(join_target, label, "inventory penuh saat daftar")
            touch_activity(action="group room inventory full", event="inventory penuh", label=label)
            if inventory_cleaned:
                return "inventory_full"
            inc_stat("inventory_full", label=label)
            if not await run_inventory_full_clean(fish_app=fish_app, label=label):
                return "inventory_full"
            _account_group_sessions_done[label] = 0
            clear_active_group_chat(label)
            inventory_cleaned = True
            retry_join_via_start = bool(room_start_command)
            Log.p("FISH", f"{fish_log_ctx(label)} Sell selesai, retry daftar room grup yang sama")
            continue

        if status == "verified_retry":
            Log.p("FISH", f"{fish_log_ctx(label)} Verifikasi berhasil, retry daftar room grup yang sama")
            continue

        Log.p("WARN", f"{fish_log_ctx(label)} Status pendaftaran tidak jelas attempt {attempt}: {preview or '-'}")
        if is_special_group_mode(label):
            reason = preview if preview and preview != "-" else f"status tidak jelas attempt {attempt}"
            mark_special_join_failed(join_target, label, reason)
        clear_pending_group_join(label)
        return None

    Log.p("WARN", f"{fish_log_ctx(label)} Gagal daftar room grup setelah retry")
    if is_special_group_mode(label):
        mark_special_join_failed(join_target, label, "gagal setelah retry")
    clear_pending_group_join(label)
    return None


