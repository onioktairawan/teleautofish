from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def click_sell_all_confirmation(message) -> bool:
    if not message or not message.reply_markup:
        return False
    label = ctx_label()
    if not mark_action_once(label, message, "click_sell_confirm"):
        Log.p("SELL", f"{fish_log_ctx(label)} Klik konfirmasi jual diabaikan karena sudah dilakukan untuk pesan ini")
        return True

    for y, row in enumerate(message.reply_markup.inline_keyboard or []):
        for x, btn in enumerate(row):
            label = btn.text or ""
            normalized = label.lower()
            if "jual semua" in normalized and ("ya" in normalized or "jual" in normalized):
                try:
                    await human_click_delay("konfirmasi jual")
                    await message.click(x, y, timeout=10)
                    Log.p("SELL", f"Klik konfirmasi: {label}")
                    return True
                except TimeoutError:
                    Log.p("WARN", "Klik konfirmasi timeout, lanjut cek hasil jual")
                    return True
                except Exception as e:
                    Log.p("WARN", f"Gagal klik konfirmasi jual: {e}")
                    return False

    return False


def is_sell_success_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        (
            "penjualan berhasil" in tl
            or "berhasil dijual" in tl
            or "berhasil menjual" in tl
        )
        and (
            "inventory sudah dikosongkan" in tl
            or "ikan terjual" in tl
            or "total coins" in tl
        )
    )


def is_sell_confirmation_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        "konfirmasi penjualan" in tl
        or "jual semua ikan di inventory" in tl
        or "ikan yang sudah terjual tidak dapat dikembalikan" in tl
    )


async def sell_all_once(attempt: int, fish_app: Client = None, label: str = "main") -> str | None:
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="/jual semua")
    if not fish_app:
        return None
    target_bot = private_command_bot_username(label)
    Log.p("SELL", f"{fish_log_ctx(label)} Kirim /jual semua attempt {attempt}/{SELL_RETRY_COUNT}...")
    confirm_task = asyncio.create_task(wait_for_bot_message(
        keywords=[
            "konfirmasi penjualan",
            "jual semua ikan di inventory",
            "ikan yang sudah terjual",
            "penjualan berhasil",
            "inventory sudah dikosongkan",
            "inventory kamu kosong",
        ],
        timeout=30,
        fish_app=fish_app,
        label=label,
        bot_username=target_bot,
    ))
    await asyncio.sleep(0)
    await safe_send(target_bot, "/jual semua", fish_app=fish_app, label=label)

    confirm_msg = await confirm_task
    if not confirm_msg:
        Log.p("WARN", f"Konfirmasi jual timeout attempt {attempt}")
        return None
    confirm_text = confirm_msg.text or confirm_msg.caption or ""
    if is_sell_success_text(confirm_text):
        Log.p("SELL", f"{fish_log_ctx(label)} Penjualan sudah berhasil tanpa klik konfirmasi")
        return confirm_text
    if is_inventory_empty_text(confirm_text):
        Log.p("SELL", f"{fish_log_ctx(label)} Inventory sudah kosong, stop retry jual")
        return confirm_text

    jual_task = asyncio.create_task(wait_for_bot_message_or_edit(
        keywords=[
            "penjualan berhasil",
            "inventory sudah dikosongkan",
            "berhasil dijual",
            "berhasil menjual",
            "inventory kamu kosong",
            "inventory kosong",
        ],
        timeout=30,
        fish_app=fish_app,
        label=label,
        bot_username=target_bot,
    ))
    await asyncio.sleep(0)

    clicked = await click_sell_all_confirmation(confirm_msg)
    if not clicked:
        jual_task.cancel()
        Log.p("WARN", "Tombol 'Ya, Jual Semua' tidak ditemukan")
        return None

    jual_msg = await jual_task
    if not jual_msg:
        return None
    jual_text = jual_msg.text or jual_msg.caption or ""
    if is_inventory_empty_text(jual_text):
        Log.p("SELL", f"{fish_log_ctx(label)} Inventory kosong setelah /jual semua, stop retry")
        return jual_text
    if is_sell_success_text(jual_text):
        return jual_text
    if is_sell_confirmation_text(jual_text):
        Log.p("WARN", f"{fish_log_ctx(label)} Hasil jual masih berupa pesan konfirmasi, bukan sukses")
        return None
    Log.p("WARN", f"{fish_log_ctx(label)} Respons jual belum dikenali sebagai sukses: {jual_text[:80]}")
    return None


async def sell_all_with_retry(fish_app: Client = None, label: str = "main") -> str | None:
    attempts = max(1, SELL_RETRY_COUNT)
    for attempt in range(1, attempts + 1):
        jual_resp = await sell_all_once(attempt, fish_app=fish_app, label=label)
        if jual_resp:
            return jual_resp
        if attempt < attempts:
            await human_delay()

    return None


def is_favorite_success_text(text: str) -> bool:
    tl = normalize_fish_name(text or "")
    return (
        "transfer ke favorite selesai" in tl
        or "berhasil ditambahkan ke favorite" in tl
        or ("favorite" in tl and "berhasil" in tl)
        or ("favorite" in tl and "dipindahkan" in tl)
    )


async def favorite_numbers_once(numbers: list[int], fish_app: Client = None, label: str = "main", attempt_label: str = "1") -> tuple[bool, str]:
    label = ctx_label(label)
    cleaned_numbers = set()
    for number in numbers:
        try:
            number = int(number)
        except (TypeError, ValueError):
            continue
        if number > 0:
            cleaned_numbers.add(number)
    numbers = sorted(cleaned_numbers)
    if not numbers:
        return True, "skip"
    if len(numbers) >= MAX_FAVORITE_SLOTS:
        return False, f"terlalu banyak item favorite: {len(numbers)}"

    target_bot = private_command_bot_username(label)
    nomor_str = " ".join(str(n) for n in numbers)
    fav_task = asyncio.create_task(wait_for_bot_reply(
        keywords=["transfer ke favorite selesai", "berhasil ditambahkan ke favorite", "favorite", "penuh", "gagal", "error"],
        timeout=60,
        fish_app=fish_app,
        label=label,
        bot_username=target_bot,
    ))
    await asyncio.sleep(0)
    Log.p("SELL", f"{fish_log_ctx(label)} Favorite attempt {attempt_label}: /favorite {nomor_str}")
    await safe_send(target_bot, f"/favorite {nomor_str}", fish_app=fish_app, label=label)

    fav_resp = await fav_task
    preview = (fav_resp or "timeout/no response").replace("\n", " ")[:160]
    if fav_resp and "penuh" in fav_resp.lower():
        return False, f"favorite penuh: {preview}"
    if fav_resp and any(word in fav_resp.lower() for word in ["gagal", "error"]):
        return False, f"favorite gagal: {preview}"
    if not fav_resp or not is_favorite_success_text(fav_resp):
        return False, f"favorite belum terkonfirmasi sukses: {preview}"
    return True, preview


async def read_inventory_rarity_summary(fish_app: Client, label: str = "main") -> bool:
    label = ctx_label(label)
    bot_username = private_command_bot_username(label)
    
    q = asyncio.Queue(maxsize=1)
    handler_group = alloc_handler_group()
    
    async def _handler(client, message):
        text = message.text or message.caption or ""
        if "Rarity:" in text or "Inventory Kosong" in text or "Total Item" in text:
            if not q.full():
                await q.put(text)
                
    handlers = [
        MessageHandler(_handler, filters.chat(bot_username) & filters.incoming),
        EditedMessageHandler(_handler, filters.chat(bot_username)),
    ]
    
    for h in handlers:
        fish_app.add_handler(h, group=handler_group)
        
    try:
        await safe_send(bot_username, "/inventory", fish_app=fish_app, label=label)
        try:
            text = await asyncio.wait_for(q.get(), timeout=30.0)
        except asyncio.TimeoutError:
            Log.p("WARN", f"[{label}] Timeout baca rarity summary")
            return False
            
        for line in text.split('\n'):
            if "Rarity:" in line:
                if any(emoji in line for emoji in ["🌟", "✨", "💫", "☀️", "🟤"]):
                    return True
        return False
    finally:
        remove_handlers(handlers, group=handler_group, fish_app=fish_app)


async def sell_flow(fish_app: Client = None, label: str = "main"):
    label = ctx_label(label)
    lock = _account_sell_locks.setdefault(label, asyncio.Lock())
    if lock.locked():
        Log.p("WARN", f"{fish_log_ctx(label)} Sell flow sudah berjalan, skip panggilan duplikat")
        return

    async with lock:
        token = _current_account_label.set(label)
        try:
            await _sell_flow_locked(fish_app=fish_app, label=label)
        finally:
            _current_account_label.reset(token)


async def _sell_flow_locked(fish_app: Client = None, label: str = "main"):
    label = ctx_label(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="sell flow")
    if not fish_app:
        await log_event("SELL_FAIL", label, "Userbot belum siap, sell flow dibatalkan.")
        return
    Log.p("SELL", f"{fish_log_ctx(label)} === SELL FLOW DIMULAI ===")
    audit_log(label, "sell_start", "inventory full / clean inventory", user_id=0)
    await notify(f"🟥 [{label}] Inventory penuh! Memulai proses jual...")
    await sell_flow_log_start(label)

    raw_inventory, slots_used, slots_total = await read_all_inventory(fish_app=fish_app, label=label, log_success=False)
    inv_summary = _account_last_inventory_read_summary.get(label, {})
    if inv_summary.get("status") == "complete":
        await sell_flow_log_update(
            label,
            inventory=(
                "OK - Inventory berhasil dibaca lengkap.\n"
                f"Attempt: {inv_summary.get('attempt')}/{inv_summary.get('max_attempts')}\n"
                f"Halaman: {inv_summary.get('pages_read')}/{inv_summary.get('total_pages')}\n"
                f"Halaman terbaca: {', '.join(str(x) for x in inv_summary.get('seen_pages', []))}\n"
                f"Slot: {slots_used}/{slots_total}\n"
                f"Item parsed: {inv_summary.get('parsed_count', 0)}"
            ),
        )
    elif inv_summary.get("status") == "empty":
        await sell_flow_log_update(
            label,
            inventory="OK - Inventory kosong.\nAttempt: "
            f"{inv_summary.get('attempt')}/{inv_summary.get('max_attempts')}\nSlot: 0/0\nItem parsed: 0",
        )
    if not raw_inventory:
        Log.p("ERROR", "Inventory kosong atau gagal dibaca")
        await notify("❌ Gagal baca inventory! Cek manual.")
        await sell_flow_log_update(
            label,
            status="Gagal",
            inventory="GAGAL - Inventory kosong atau gagal dibaca.",
            sell="Dibatalkan.",
        )
        await log_event("SELL_FAIL", label, "Gagal baca inventory.")
        return
    if is_inventory_empty_text(raw_inventory):
        Log.p("SELL", f"{fish_log_ctx(label)} Inventory kosong, skip sell flow")
        await notify(f"🟥 [{label}] Inventory kosong, sell flow dilewati.")
        await sell_flow_log_update(label, status="Selesai", filter="Skip - inventory kosong.", favorite="Skip.", sell="Skip - inventory kosong.")
        return

    snapshot_ok, snapshot_msg, snapshot_summary = validate_inventory_snapshot(raw_inventory, slots_used, slots_total, label=label)
    if not snapshot_ok:
        Log.p("WARN", f"{fish_log_ctx(label)} Snapshot inventory tidak valid: {snapshot_msg}")
        await notify(
            f"⚠️ [{label}] Snapshot inventory tidak valid.\n"
            "Bot tidak lanjut favorite/jual demi keamanan.\n\n"
            f"Detail: {snapshot_msg}"
        )
        await sell_flow_log_update(
            label,
            status="Gagal",
            filter=f"GAGAL - Snapshot inventory tidak valid.\n{snapshot_msg}",
            sell="Dibatalkan.",
        )
        await log_event("SELL_FAIL", label, f"Snapshot inventory tidak valid: {snapshot_msg}\nSummary: {snapshot_summary}")
        return

    save_list, parsed_items = local_filter_inventory(raw_inventory, label=label)
    inventory_solver = "Lokal"
    if parsed_items == 0:
        Log.p("WARN", f"{fish_log_ctx(label)} Parser lokal gagal baca inventory, sell flow dibatalkan")
        await notify("⚠️ Parser lokal gagal baca inventory. Sell flow dibatalkan, cek manual.")
        await sell_flow_log_update(
            label,
            status="Gagal",
            filter="GAGAL - Parser lokal gagal baca item.",
            sell="Dibatalkan.",
        )
        await log_event(
            "INVENTORY_WARN",
            label,
            "Solver: Lokal\n"
            "Response: Parser lokal gagal baca item, sell flow dibatalkan.",
        )
        await log_event("SELL_FAIL", label, "Parser lokal gagal baca inventory.")
        return
    protected_ok, protected_msg, protected_items = validate_protected_save_list(raw_inventory, save_list, label=label)
    if not protected_ok:
        Log.p("WARN", f"{fish_log_ctx(label)} Protected sanity gagal: {protected_msg}")
        await notify(
            f"⚠️ [{label}] Item protected belum aman.\n"
            "Bot tidak lanjut jual demi keamanan.\n\n"
            f"{protected_msg}"
        )
        await sell_flow_log_update(
            label,
            status="Gagal",
            filter=f"GAGAL - Protected item tidak masuk target.\n{protected_msg}",
            sell="Dibatalkan.",
        )
        await log_event("SELL_FAIL", label, protected_msg)
        return
    rare_items = find_rare_catch_items(save_list, raw_inventory)
    gallery_items = favorite_history_items(save_list, raw_inventory, label=label)
    save_favorite_gallery(gallery_items, label=label)
    await notify_rare_catches(rare_items, label=label)
    await sell_flow_log_update(
        label,
        filter=(
            f"Solver: {inventory_solver}\n"
            f"Slot: {slots_used}/{slots_total}\n"
            f"Item terbaca: {parsed_items}\n"
            f"Protected: {[item['number'] for item in protected_items] if protected_items else '-'}\n"
            f"Favorite target: {save_list if save_list else '-'}"
        ),
    )

    if save_list:
        Log.p("SELL", f"Ikan yang akan difavoritkan: {save_list}")

        if len(save_list) >= MAX_FAVORITE_SLOTS:
            await notify(
                f"⚠️ Terlalu banyak ikan yang mau disimpan ({len(save_list)} ekor).\n"
                f"Silakan cek dan kelola favorite manual!"
            )
            await sell_flow_log_update(
                label,
                status="Dibatalkan",
                favorite=f"GAGAL - Terlalu banyak item favorite: {len(save_list)}",
                sell="Dibatalkan.",
            )
            await log_event("FAVORITE_ABORT", label, f"Terlalu banyak item favorite: {len(save_list)}")
            return

        fav_ok, fav_resp = await favorite_numbers_once(save_list, fish_app=fish_app, label=label, attempt_label="1")
        if not fav_ok and "penuh" in fav_resp.lower():
            await notify(
                "⚠️ Slot FAVORITE PENUH!\n"
                "Bot dihentikan. Harap kelola favorite manual,\n"
                "lalu buka /mancing dan tekan Start untuk lanjut."
            )
            Log.p("WARN", "Favorite penuh, abort sell flow")
            await sell_flow_log_update(label, status="Dibatalkan", favorite="GAGAL - Slot favorite penuh.", sell="Dibatalkan.")
            await log_event("FAVORITE_FULL", label, f"Favorite penuh. Target: {save_list}")
            return

        if not fav_ok:
            await notify(
                f"⚠️ [{label}] Favorite belum terkonfirmasi sukses.\n"
                "Bot tidak lanjut /jual demi keamanan.\n\n"
                f"Response: {fav_resp}"
            )
            Log.p("WARN", f"{fish_log_ctx(label)} Favorite belum sukses/timeout, abort sell flow: {fav_resp}")
            await sell_flow_log_update(
                label,
                status="Dibatalkan",
                favorite=f"GAGAL - Favorite belum terkonfirmasi sukses.\nResponse: {fav_resp}",
                sell="Dibatalkan.",
            )
            await log_event("FAVORITE_FAIL", label, f"Target: {save_list}\nResponse: {fav_resp}")
            return

        await notify(f"✅ {len(save_list)} ikan berhasil difavoritkan: {save_list}")
        favorite_log = f"Attempt 1 OK\nJumlah: {len(save_list)}\nNomor: {save_list}"
        await sell_flow_log_update(label, favorite=favorite_log)
        await human_delay()

        has_rare = await read_inventory_rarity_summary(fish_app=fish_app, label=label)
        if not has_rare:
            Log.p("SELL", f"{fish_log_ctx(label)} Verifikasi cepat: tidak ada rarity target, lanjut jual")
            await sell_flow_log_update(label, favorite=f"{favorite_log}\nVerify: cepat OK - tidak ada rarity target.")
        else:
            Log.p("SELL", f"{fish_log_ctx(label)} Verifikasi cepat: rarity target terdeteksi, jalankan verify penuh")
            verify_inventory, verify_slots_used, verify_slots_total = await read_all_inventory(fish_app=fish_app, label=label, log_success=False)
            if not verify_inventory:
                Log.p("WARN", f"{fish_log_ctx(label)} Gagal baca inventory verifikasi setelah favorite")
                await notify(f"⚠️ [{label}] Gagal baca inventory verifikasi setelah favorite. Bot tidak lanjut jual.")
                await sell_flow_log_update(label, status="Gagal", favorite=f"{favorite_log}\nVerify: gagal baca inventory.", sell="Dibatalkan.")
                await log_event("SELL_FAIL", label, "Gagal baca inventory verifikasi setelah favorite.")
                return

            if is_inventory_empty_text(verify_inventory):
                Log.p("SELL", f"{fish_log_ctx(label)} Inventory kosong setelah favorite pertama")
                await sell_flow_log_update(label, favorite=f"{favorite_log}\nVerify: inventory kosong.")
            else:
                verify_ok, verify_msg, verify_summary = validate_inventory_snapshot(verify_inventory, verify_slots_used, verify_slots_total, label=label)
                if not verify_ok:
                    Log.p("WARN", f"{fish_log_ctx(label)} Snapshot verifikasi tidak valid: {verify_msg}")
                    await notify(
                        f"⚠️ [{label}] Snapshot verifikasi inventory tidak valid.\n"
                        "Bot tidak lanjut jual demi keamanan.\n\n"
                        f"Detail: {verify_msg}"
                    )
                    await sell_flow_log_update(
                        label,
                        status="Gagal",
                        favorite=f"{favorite_log}\nVerify: snapshot tidak valid.\n{verify_msg}",
                        sell="Dibatalkan.",
                    )
                    await log_event("SELL_FAIL", label, f"Snapshot verifikasi tidak valid: {verify_msg}\nSummary: {verify_summary}")
                    return

                remaining_save_list, remaining_parsed = local_filter_inventory(verify_inventory, label=label)
                remaining_protected_ok, remaining_protected_msg, remaining_protected_items = validate_protected_save_list(
                    verify_inventory,
                    remaining_save_list,
                    label=label,
                )
                if not remaining_protected_ok:
                    Log.p("WARN", f"{fish_log_ctx(label)} Protected sanity verify gagal: {remaining_protected_msg}")
                    await notify(
                        f"⚠️ [{label}] Item protected belum aman pada inventory verifikasi.\n"
                        "Bot tidak lanjut jual demi keamanan.\n\n"
                        f"{remaining_protected_msg}"
                    )
                    await sell_flow_log_update(
                        label,
                        status="Gagal",
                        favorite=f"{favorite_log}\nVerify: protected sanity gagal.\n{remaining_protected_msg}",
                        sell="Dibatalkan.",
                    )
                    await log_event("SELL_FAIL", label, remaining_protected_msg)
                    return

                if remaining_save_list:
                    Log.p("SELL", f"{fish_log_ctx(label)} Item keep masih ada setelah favorite pertama, favorite ulang: {remaining_save_list}")
                    if len(remaining_save_list) >= MAX_FAVORITE_SLOTS:
                        await notify(f"⚠️ [{label}] Terlalu banyak item tersisa untuk favorite ulang ({len(remaining_save_list)}). Bot tidak lanjut jual.")
                        await sell_flow_log_update(
                            label,
                            status="Dibatalkan",
                            favorite=f"{favorite_log}\nAttempt 2 GAGAL - Terlalu banyak item: {len(remaining_save_list)}",
                            sell="Dibatalkan.",
                        )
                        await log_event("FAVORITE_ABORT", label, f"Terlalu banyak item favorite ulang: {remaining_save_list}")
                        return

                    second_fav_ok, second_fav_resp = await favorite_numbers_once(remaining_save_list, fish_app=fish_app, label=label, attempt_label="2")
                    if not second_fav_ok and "penuh" in second_fav_resp.lower():
                        await notify("⚠️ Slot FAVORITE PENUH saat favorite ulang. Bot tidak lanjut jual.")
                        await sell_flow_log_update(label, status="Dibatalkan", favorite=f"{favorite_log}\nAttempt 2 GAGAL - {second_fav_resp}", sell="Dibatalkan.")
                        await log_event("FAVORITE_FULL", label, f"Favorite ulang penuh. Target: {remaining_save_list}")
                        return
                    if not second_fav_ok:
                        await notify(
                            f"⚠️ [{label}] Favorite ulang belum terkonfirmasi sukses.\n"
                            "Bot tidak lanjut /jual demi keamanan.\n\n"
                            f"Response: {second_fav_resp}"
                        )
                        await sell_flow_log_update(label, status="Dibatalkan", favorite=f"{favorite_log}\nAttempt 2 GAGAL - {second_fav_resp}", sell="Dibatalkan.")
                        await log_event("FAVORITE_FAIL", label, f"Target ulang: {remaining_save_list}\nResponse: {second_fav_resp}")
                        return

                    await notify(f"✅ Favorite ulang berhasil untuk item tersisa: {remaining_save_list}")
                    await sell_flow_log_update(
                        label,
                        favorite=(
                            f"{favorite_log}\n"
                            f"Verify: masih ada target keep {remaining_save_list}\n"
                            f"Attempt 2 OK\nNomor: {remaining_save_list}"
                        ),
                    )
                    await human_delay()
                else:
                    Log.p("SELL", f"{fish_log_ctx(label)} Verify OK, tidak ada item keep tersisa")
                    await sell_flow_log_update(label, favorite=f"{favorite_log}\nVerify OK - tidak ada item keep tersisa.")
    else:
        Log.p("SELL", "Tidak ada ikan yang perlu difavoritkan, langsung jual semua")
        await sell_flow_log_update(label, favorite="Skip - tidak ada item yang perlu difavorite.")

    jual_resp = await sell_all_with_retry(fish_app=fish_app, label=label)

    if jual_resp:
        global _last_sell_summary
        _last_sell_summary = jual_resp.replace("\n", " ")[:120]
        _account_last_sell[label] = _last_sell_summary
        inc_stat("sell_success", label=label)
        audit_log(label, "sell_success", _last_sell_summary, user_id=0)
        Log.p("SELL", f"Jual OK: {jual_resp[:60]}")
        await sell_flow_log_update(label, status="Selesai", sell=f"OK\nResponse: {_last_sell_summary}")
    else:
        Log.p("WARN", "Tidak ada konfirmasi hasil jual (timeout)")
        await notify("⚠️ Tidak ada konfirmasi hasil jual. Cek manual!")
        await sell_flow_log_update(label, status="Gagal", sell="GAGAL - Tidak ada konfirmasi hasil jual atau timeout.")
        await log_event("SELL_FAIL", label, "Tidak ada konfirmasi hasil jual atau timeout.")

    Log.p("SELL", f"{fish_log_ctx(label)} === SELL FLOW SELESAI ===")


