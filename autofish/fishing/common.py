from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def _remove_handler_if_registered(fish_app: Client, handler, group: int = 0):
    safe_remove_handler(handler, group=group, fish_app=fish_app)


def safe_remove_handler(handler, group: int = 0, fish_app: Client = None):
    if fish_app is None:
        return
    try:
        fish_app.remove_handler(handler, group)
    except Exception as e:
        Log.p("WARN", f"remove handler gagal: {e}")


async def remove_handler_now(handler, group: int = 0, fish_app: Client = None):
    safe_remove_handler(handler, group=group, fish_app=fish_app)


async def remove_handlers_now(handlers: list, group: int, fish_app: Client = None):
    for handler in handlers:
        safe_remove_handler(handler, group=group, fish_app=fish_app)


async def cancel_task_safely(task: asyncio.Task | None, *, label: str = "main", reason: str = "cancel task"):
    if not task or task.done() or task is asyncio.current_task():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception as e:
        Log.p("WARN", f"{fish_log_ctx(label)} {reason} gagal clean shutdown: {e}")


def cancel_task_background(task: asyncio.Task | None, *, label: str = "main", reason: str = "cancel task"):
    if not task or task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        task.cancel()
        return
    loop.create_task(cancel_task_safely(task, label=label, reason=reason))


async def resolve_fish_app_or_none(fish_app: Client = None, label: str = "main", action: str = "aksi fish") -> Client | None:
    label = ctx_label(label)
    expected_client = _account_clients.get(label)
    if expected_client is None:
        expected_client = await account_client_or_none(label)
    if not expected_client:
        Log.p("WARN", f"[{label}] {action} dibatalkan: userbot belum siap")
        return None
    if fish_app is not None and fish_app is not expected_client:
        Log.p("WARN", f"[{label}] {action} dibatalkan: client tidak cocok dengan label")
        return None
    return fish_app or expected_client


async def safe_send(chat, text: str, fish_app: Client = None, label: str = "main"):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action=f"kirim {text[:30]}")
    if not fish_app:
        return False
    if verification_required(label):
        Log.p("FISH", f"{fish_log_ctx(label)} Tunda kirim {text[:30]} karena menunggu verifikasi manual")
        return False
    captcha_lock = _account_captcha_locks.get(label)
    if captcha_lock and captcha_lock.locked():
        Log.p("FISH", f"{fish_log_ctx(label)} Tunda kirim {text[:30]} karena verifikasi sedang diproses")
        deadline = time.monotonic() + 15
        while captcha_lock.locked() and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
    try:
        await fish_app.send_message(chat, text)
        if chat in {FISH_BOT_USERNAME, private_command_bot_username(label)}:
            touch_activity(action=f"send {text[:30]}", label=label)
        return True
    except FloodWait as e:
        wait = int(getattr(e, "value", 5)) + 1
        Log.p("WARN", f"FloodWait {wait}s, tunggu...")
        await asyncio.sleep(wait)
        try:
            await fish_app.send_message(chat, text)
            return True
        except Exception as e2:
            Log.p("ERROR", f"safe_send gagal setelah FloodWait: {e2}")
    except Exception as e:
        if is_connection_lost_error(e):
            recovered = await recover_account_client_connection(fish_app=fish_app, label=label, reason=str(e))
            if recovered:
                try:
                    await recovered.send_message(chat, text)
                    if chat in {FISH_BOT_USERNAME, private_command_bot_username(label)}:
                        touch_activity(action=f"send {text[:30]} (retry)", label=label)
                    return True
                except Exception as retry_error:
                    Log.p("ERROR", f"safe_send gagal setelah recovery koneksi: {retry_error}")
        Log.p("ERROR", f"safe_send gagal: {e}")
    return False


async def human_delay(min_delay: float = None, max_delay: float = None):
    low = ACTION_DELAY_MIN if min_delay is None else min_delay
    high = ACTION_DELAY_MAX if max_delay is None else max_delay
    if high < low:
        high = low
    delay = random.uniform(low, high)
    Log.p("FISH", f"Jeda {delay:.1f}s")
    await asyncio.sleep(delay)


async def human_click_delay(action: str = "klik"):
    low = HUMAN_CLICK_DELAY_MIN
    high = HUMAN_CLICK_DELAY_MAX
    if high < low:
        high = low
    delay = random.uniform(low, high)
    Log.p("FISH", f"Jeda klik {action} {delay:.1f}s")
    await asyncio.sleep(delay)


async def captcha_click_delay():
    low = CAPTCHA_CLICK_DELAY_MIN
    high = CAPTCHA_CLICK_DELAY_MAX
    if high < low:
        high = low
    if high <= 0:
        return
    delay = random.uniform(low, high)
    Log.p("FISH", f"Jeda klik captcha {delay:.1f}s")
    await asyncio.sleep(delay)


async def private_done_delay(label: str = "main"):
    low = PRIVATE_DONE_DELAY_MIN
    high = PRIVATE_DONE_DELAY_MAX
    if high < low:
        high = low
    delay = random.uniform(low, high)
    Log.p("FISH", f"{fish_log_ctx(label, 'private')} Sesi private selesai, tunggu {delay:.1f}s sebelum /mancing lagi")
    await asyncio.sleep(delay)


async def wait_for_bot_reply(
    keywords: list[str] = None,
    timeout: int = 120,
    fish_app: Client = None,
    label: str = None,
    bot_username: str = None,
) -> str | None:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu reply bot")
    if not fish_app:
        return None
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()

    async def _handler(client, message):
        text = message.text or message.caption or ""
        if keywords is None:
            if not result_queue.full():
                await result_queue.put(text)
        else:
            tl = text.lower()
            if any(k.lower() in tl for k in keywords):
                if not result_queue.full():
                    await result_queue.put(text)

    handler = MessageHandler(
        _handler,
        filters.chat(bot_username or private_command_bot_username(label)) & filters.incoming,
    )
    fish_app.add_handler(handler, group=handler_group)

    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        safe_remove_handler(handler, group=handler_group, fish_app=fish_app)


def message_is_after(message, started_at: datetime) -> bool:
    msg_date = getattr(message, "date", None)
    if not msg_date:
        return True
    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)
    return msg_date >= started_at


def extract_message_text(message) -> str:
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


async def resolve_message_text(message, fish_app: Client = None) -> str:
    text = extract_message_text(message)
    if text or not fish_app or not getattr(message, "chat", None) or not getattr(message, "id", None):
        return text
    try:
        refreshed = await fish_app.get_messages(message.chat.id, message.id)
        return extract_message_text(refreshed)
    except Exception:
        return text


