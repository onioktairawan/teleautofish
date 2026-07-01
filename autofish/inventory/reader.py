from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def add_inventory_page_handlers(fish_app: Client, queue: asyncio.Queue, group: int, bot_username: str = None) -> list:
    async def _handler(client, message):
        text = message.text or message.caption or ""
        tl = text.lower()
        if ("inventory" in tl or "slot terisi" in tl or is_inventory_empty_text(text)) and not queue.full():
            await queue.put((text, message))

    handlers = [
        MessageHandler(_handler, filters.chat(bot_username or FISH_BOT_USERNAME) & filters.incoming),
        EditedMessageHandler(_handler, filters.chat(bot_username or FISH_BOT_USERNAME)),
    ]
    for handler in handlers:
        fish_app.add_handler(handler, group=group)
    return handlers


def remove_handlers(handlers: list, group: int, fish_app: Client = None):
    for handler in handlers:
        safe_remove_handler(handler, group=group, fish_app=fish_app)


def parse_inventory_slots(text: str) -> tuple[int, int]:
    match = re.search(r"Slot terisi:\s*(\d+)\s*/\s*(\d+)", text or "", re.I)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def parse_inventory_page_info(text: str) -> tuple[int, int]:
    match = re.search(r"Halaman:\s*(\d+)\s*/\s*(\d+)", text or "", re.I)
    if not match:
        return 1, 1
    return int(match.group(1)), int(match.group(2))


def is_inventory_page_text(text: str, expected_page: int = None) -> bool:
    page_number, _ = parse_inventory_page_info(text)
    if expected_page is not None and page_number != expected_page:
        return False
    return bool(parse_inventory_items(text))


def is_inventory_empty_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        "inventory kosong" in tl
        or "inventory kamu kosong" in tl
        or "belum memiliki ikan" in tl
        or "tidak ada ikan" in tl
    )


def is_inventory_next_button(label: str) -> bool:
    normalized = normalize_fish_name(label)
    if not normalized:
        return False
    prev_markers = ["prev", "previous", "back", "sebelum", "kembali", "‹", "«", "◀", "⬅"]
    if any(marker in normalized for marker in prev_markers):
        return False
    next_markers = ["next", "lanjut", "berikut", "selanjutnya", "›", "»", "▶", "➡", "⏭", ">"]
    return any(marker in normalized for marker in next_markers)


def get_inventory_next_button_label(message) -> str | None:
    if not message or not message.reply_markup:
        return None

    fallback_label = None
    for row in (message.reply_markup.inline_keyboard or []):
        for btn in row:
            label = btn.text or ""
            normalized = normalize_fish_name(label)
            if not normalized:
                continue
            if is_inventory_next_button(label):
                return label
            if re.search(r"\d+\s*/\s*\d+", normalized) or "halaman" in normalized:
                continue
            if any(marker in normalized for marker in ["prev", "previous", "back", "sebelum", "kembali"]):
                continue
            fallback_label = label

    return fallback_label


async def click_inventory_next(message) -> bool:
    label = get_inventory_next_button_label(message)
    if not label:
        return False
    try:
        await human_click_delay("next inventory")
        await message.click(label, timeout=10)
        Log.p("INV", f"Klik Next inventory: {label}")
        return True
    except Exception as e:
        Log.p("WARN", f"Gagal klik Next inventory ({label}): {e}")
        await log_event("INVENTORY_WARN", _current_account_label.get(), f"Gagal klik Next inventory ({label}): {str(e)[:200]}")
        return False


async def wait_for_inventory_page(
    queue: asyncio.Queue,
    expected_page: int = None,
    timeout: int = 90,
) -> tuple[str, object] | tuple[None, None]:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, None
        try:
            page_text, page_msg = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None, None
        page_number, total_pages = parse_inventory_page_info(page_text)
        if expected_page is not None and page_number != expected_page:
            Log.p("INV", f"Abaikan halaman inventory {page_number}/{total_pages}, tunggu {expected_page}")
            await log_event(
                "INVENTORY_WARN",
                _current_account_label.get(),
                f"Halaman tidak sesuai: dapat {page_number}/{total_pages}, tunggu {expected_page}.",
            )
            continue
        if not is_inventory_page_text(page_text, expected_page=expected_page):
            Log.p("INV", f"Abaikan inventory tanpa item valid untuk halaman {expected_page or page_number}")
            await log_event(
                "INVENTORY_WARN",
                _current_account_label.get(),
                f"Inventory tanpa item valid untuk halaman {expected_page or page_number}.",
            )
            continue
        return page_text, page_msg


async def read_all_inventory(fish_app: Client = None, label: str = "main", log_success: bool = False) -> tuple[str, int, int]:
    label = ctx_label(label)
    _account_last_inventory_read_summary.pop(label, None)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="baca inventory")
    if not fish_app:
        await log_event("INVENTORY_WARN", label, "Userbot belum siap, baca inventory dibatalkan.")
        return "", 0, 0
    max_pages = 20
    max_attempts = 3
    last_slots_used = 0
    last_slots_total = 0
    target_bot = private_command_bot_username(label)

    for read_attempt in range(1, max_attempts + 1):
        Log.p("INV", f"[{label}] Mulai baca inventory attempt {read_attempt}/{max_attempts}...")
        all_text = ""
        slots_used = 0
        complete_read = True
        handler_group = alloc_handler_group()

        first_page_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        first_handlers = add_inventory_page_handlers(fish_app, first_page_queue, handler_group, target_bot)
        await safe_send(target_bot, "/inventory", fish_app=fish_app, label=label)

        try:
            page_text, page_msg = await asyncio.wait_for(first_page_queue.get(), timeout=30)
        except asyncio.TimeoutError:
            Log.p("WARN", f"Timeout baca halaman 1 inventory attempt {read_attempt}")
            remove_handlers(first_handlers, group=handler_group, fish_app=fish_app)
            await log_event("INVENTORY_WARN", label, f"Timeout baca halaman 1 inventory attempt {read_attempt}/{max_attempts}.")
            await asyncio.sleep(1)
            continue
        finally:
            remove_handlers(first_handlers, group=handler_group, fish_app=fish_app)

        if is_inventory_empty_text(page_text):
            save_inventory_slots(label, 0, 0)
            _account_last_inventory_read_summary[label] = {
                "status": "empty",
                "attempt": read_attempt,
                "max_attempts": max_attempts,
                "pages_read": 0,
                "total_pages": 0,
                "seen_pages": [],
                "slots_used": 0,
                "slots_total": 0,
                "parsed_count": 0,
            }
            Log.p("INV", f"[{label}] Inventory kosong, tidak perlu baca halaman/retry")
            if log_success:
                await log_event(
                    "INVENTORY",
                    label,
                    "Inventory kosong.\n"
                    f"Attempt: {read_attempt}/{max_attempts}\n"
                    "Halaman: 0/0\n"
                    "Slot: 0/0\n"
                    "Item parsed: 0",
                )
            return page_text.strip(), 0, 0

        slots_used, slots_total = parse_inventory_slots(page_text)
        last_slots_used, last_slots_total = slots_used, slots_total
        current_page, total_pages = parse_inventory_page_info(page_text)
        if slots_used:
            Log.p("INV", f"Slot: {slots_used}/{slots_total}")
        save_inventory_slots(label, slots_used, slots_total)
        if total_pages == 1 and slots_used > 20:
            total_pages = (slots_used + 19) // 20
        total_pages = max(1, min(total_pages, max_pages))

        seen_pages = {current_page}
        all_text += f"\n--- Halaman {current_page}/{total_pages} ---\n{page_text}"
        Log.p("INV", f"Halaman {current_page}/{total_pages} berhasil dibaca")

        while current_page < total_pages:
            expected_page = current_page + 1
            result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
            page_handlers = add_inventory_page_handlers(fish_app, result_queue, handler_group, target_bot)

            clicked = await click_inventory_next(page_msg)
            if not clicked:
                remove_handlers(page_handlers, group=handler_group, fish_app=fish_app)
                Log.p("WARN", f"Tombol Next tidak ditemukan di halaman {current_page}/{total_pages}")
                await log_event("INVENTORY_WARN", label, f"Tombol Next tidak ditemukan di halaman {current_page}/{total_pages}.")
                complete_read = False
                break

            try:
                page_text, page_msg = await asyncio.wait_for(result_queue.get(), timeout=30)
            except asyncio.TimeoutError:
                Log.p("WARN", f"Timeout baca halaman {expected_page}, stop baca")
                await log_event("INVENTORY_WARN", label, f"Timeout baca halaman {expected_page}/{total_pages}.")
                complete_read = False
                break
            finally:
                remove_handlers(page_handlers, group=handler_group, fish_app=fish_app)

            page_number, parsed_total_pages = parse_inventory_page_info(page_text)
            if parsed_total_pages > total_pages:
                total_pages = min(parsed_total_pages, max_pages)

            if page_number in seen_pages:
                Log.p("WARN", f"Halaman inventory duplikat terbaca ({page_number}), stop baca")
                await log_event("INVENTORY_WARN", label, f"Halaman inventory duplikat terbaca ({page_number}).")
                complete_read = False
                break
            if page_number != expected_page:
                Log.p("WARN", f"Halaman inventory lompat: expected {expected_page}, dapat {page_number}")
                await log_event("INVENTORY_WARN", label, f"Halaman inventory lompat: expected {expected_page}, dapat {page_number}.")
                complete_read = False
                break

            seen_pages.add(page_number)
            current_page = page_number
            all_text += f"\n--- Halaman {current_page}/{total_pages} ---\n{page_text}"
            Log.p("INV", f"Halaman {current_page}/{total_pages} berhasil dibaca")

        parsed_count = len(parse_inventory_items(all_text))
        Log.p("INV", f"Selesai baca {len(seen_pages)}/{total_pages} halaman inventory, item={parsed_count}")
        if complete_read and len(seen_pages) == total_pages and parsed_count > 0:
            _account_last_inventory_read_summary[label] = {
                "status": "complete",
                "attempt": read_attempt,
                "max_attempts": max_attempts,
                "pages_read": len(seen_pages),
                "total_pages": total_pages,
                "seen_pages": sorted(seen_pages),
                "slots_used": slots_used,
                "slots_total": slots_total,
                "parsed_count": parsed_count,
            }
            if log_success:
                await log_event(
                    "INVENTORY",
                    label,
                    "Inventory berhasil dibaca lengkap.\n"
                    f"Attempt: {read_attempt}/{max_attempts}\n"
                    f"Halaman: {len(seen_pages)}/{total_pages}\n"
                    f"Halaman terbaca: {', '.join(str(x) for x in sorted(seen_pages))}\n"
                    f"Slot: {slots_used}/{slots_total}\n"
                    f"Item parsed: {parsed_count}",
                )
            return all_text.strip(), slots_used, slots_total

        Log.p("WARN", f"[{label}] Inventory tidak lengkap terbaca attempt {read_attempt}: {len(seen_pages)}/{total_pages}, item={parsed_count}")
        await log_event(
            "INVENTORY_WARN",
            label,
            f"Inventory tidak lengkap attempt {read_attempt}/{max_attempts}: {len(seen_pages)}/{total_pages}, item={parsed_count}.",
        )
        await asyncio.sleep(1)

    Log.p("WARN", f"[{label}] Inventory gagal dibaca lengkap setelah {max_attempts} attempt, abort")
    _account_last_inventory_read_summary[label] = {
        "status": "failed",
        "attempt": max_attempts,
        "max_attempts": max_attempts,
        "slots_used": last_slots_used,
        "slots_total": last_slots_total,
    }
    await log_event("INVENTORY_WARN", label, f"Inventory gagal dibaca lengkap setelah {max_attempts} attempt, sell flow dibatalkan.")
    return "", last_slots_used, last_slots_total


async def wait_for_bot_message(
    keywords: list[str] = None,
    timeout: int = 120,
    fish_app: Client = None,
    label: str = None,
    bot_username: str = None,
):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu pesan bot")
    if not fish_app:
        return None
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()

    async def _handler(client, message):
        text = message.text or message.caption or ""
        if keywords is None:
            if not result_queue.full():
                await result_queue.put(message)
        else:
            tl = text.lower()
            if any(k.lower() in tl for k in keywords):
                if not result_queue.full():
                    await result_queue.put(message)

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


async def wait_for_bot_message_or_edit(
    keywords: list[str] = None,
    timeout: int = 120,
    fish_app: Client = None,
    label: str = None,
    bot_username: str = None,
):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="tunggu pesan/edit bot")
    if not fish_app:
        return None
    result_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()

    async def _handler(client, message):
        text = message.text or message.caption or ""
        if keywords is None:
            if not result_queue.full():
                await result_queue.put(message)
        else:
            tl = text.lower()
            if any(k.lower() in tl for k in keywords):
                if not result_queue.full():
                    await result_queue.put(message)

    chat_filter = filters.chat(bot_username) if bot_username else private_fish_bot_filter(label)
    handlers = [
        MessageHandler(_handler, chat_filter & filters.incoming),
        EditedMessageHandler(_handler, chat_filter),
    ]
    for handler in handlers:
        fish_app.add_handler(handler, group=handler_group)

    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        remove_handlers(handlers, group=handler_group, fish_app=fish_app)


