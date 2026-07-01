from __future__ import annotations

def bind_runtime(namespace: dict):
    globals().update(namespace)

async def fishing_loop(fish_app: Client = None, label: str = "main"):
    global _is_running
    label = ctx_label(label)
    token = _current_account_label.set(label)
    fish_app = await resolve_fish_app_or_none(fish_app, label=label, action="loop mancing")
    if not fish_app:
        _account_running[label] = False
        _current_account_label.reset(token)
        return
    _is_running = True
    _account_running[label] = True
    Log.p("FISH", f"{fish_log_ctx(label)} Loop mancing dimulai!")

    while not _shutdown_event.is_set() and _account_running.get(label, False):
        try:
            if maintenance_blocks_account(label):
                Log.p("FISH", f"{fish_log_ctx(label)} Maintenance aktif, loop mancing berhenti sementara")
                _account_running[label] = False
                break
            if is_command_mode(label):
                await asyncio.sleep(1)
                continue
            if verification_required(label):
                touch_activity(action="verification pause", event="menunggu verifikasi manual", label=label)
                await asyncio.sleep(5)
                continue
            # Check for pending mode switch
            pending_mode = _account_mode_switch_pending.get(label)
            if pending_mode:
                if not _account_private_session_active.get(label) and not _account_group_active.get(label):
                    Log.p("FISH", f"{fish_log_ctx(label)} Menerapkan pergantian mode tertunda: {pending_mode}")
                    save_runtime_mode(pending_mode, label)
                    _account_mode_switch_pending.pop(label, None)
            mode = current_fish_mode(label)
            log_ctx = fish_log_ctx(label, mode)
            if mode == "special_group":
                target = special_group_chat_target(label)
                if not target:
                    Log.p("WARN", f"{log_ctx} Mode grup khusus aktif tapi grup khusus belum diset")
                    await asyncio.sleep(5)
                    continue

                if _account_group_active.get(label):
                    Log.p("FISH", f"{log_ctx} Sesi grup khusus masih aktif → tunggu hasil grup")
                    chat_filter = special_group_filter(label)
                    if chat_filter is None:
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(1.5)
                        continue
                    result_task = asyncio.create_task(wait_for_fish_event(
                        timeout=300,
                        fish_app=fish_app,
                        label=label,
                        chat_filter=chat_filter,
                    ))
                else:
                    join_status = await wait_and_join_group_room(
                        timeout=300,
                        fish_app=fish_app,
                        label=label,
                        group_targets=[target],
                        source_name="grup khusus",
                        recent_history_limit=12,
                    )
                    if join_status == "inventory_full":
                        inc_stat("inventory_full", label=label)
                        Log.p("FISH", f"{log_ctx} Inventory penuh saat daftar grup khusus → mulai sell flow")
                        await log_event("INVENTORY_FULL", label, "Saat daftar grup khusus.")
                        if not await run_inventory_full_clean(fish_app=fish_app, label=label):
                            return
                        _account_group_sessions_done[label] = 0
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(POST_EVENT_DELAY)
                        continue
                    if verification_required(label):
                        Log.p("WARN", f"{log_ctx} Join grup khusus tertunda karena verifikasi manual | {runtime_state_summary(label)}")
                        await asyncio.sleep(5)
                        continue
                    if join_status == "room_full":
                        Log.p("FISH", f"{log_ctx} Room grup khusus penuh, tunggu room berikutnya")
                        await asyncio.sleep(1.5)
                        continue
                    if join_status not in {"joined", "group_active"}:
                        await maybe_open_special_group_room(label, fish_app=fish_app, reason="no_room")
                        await asyncio.sleep(1.5)
                        continue

                    _account_group_active[label] = True
                    chat_filter = special_group_filter(label)
                    if chat_filter is None:
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(1.5)
                        continue
                    result_task = asyncio.create_task(wait_for_fish_event(
                        timeout=300,
                        fish_app=fish_app,
                        label=label,
                        chat_filter=chat_filter,
                    ))
            elif mode in {"group_room", "all"}:
                if _account_group_active.get(label):
                    Log.p("FISH", f"{log_ctx} Sesi grup masih aktif → tunggu hasil grup")
                    chat_filter = group_room_filter(label)
                    if chat_filter is None:
                        Log.p("WARN", f"{log_ctx} Tidak ada grup untuk dipantau, reset sesi grup")
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(1.5)
                        continue
                    result_task = asyncio.create_task(wait_for_fish_event(
                        timeout=300,
                        fish_app=fish_app,
                        label=label,
                        chat_filter=chat_filter,
                    ))
                    result = await result_task
                    if result is None:
                        Log.p("WARN", f"{log_ctx} Timeout tunggu event grup aktif, coba cek room lagi")
                        await asyncio.sleep(1.5)
                        continue
                    event, text, event_msg = result
                    if event == "done":
                        inc_stat("sessions_done", label=label)
                        _account_group_sessions_done[label] = _account_group_sessions_done.get(label, 0) + 1
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        Log.p("FISH", f"{log_ctx} Sesi grup selesai count={_account_group_sessions_done[label]}")
                        await asyncio.sleep(POST_EVENT_DELAY)
                        continue
                    if event == "full":
                        inc_stat("inventory_full", label=label)
                        Log.p("FISH", f"{log_ctx} Inventory penuh saat sesi grup → mulai sell flow")
                        await log_event("INVENTORY_FULL", label, "Saat sesi grup.")
                        if not await run_inventory_full_clean(fish_app=fish_app, label=label):
                            return
                        _account_group_sessions_done[label] = 0
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(POST_EVENT_DELAY)
                        continue
                    if event == "captcha":
                        Log.p("WARN", f"{log_ctx} Verifikasi terdeteksi saat sesi grup aktif")
                        solved = await solve_captcha_event_once(text, event_msg, fish_app=fish_app, label=label, source="group_event")
                        if solved is None:
                            await asyncio.sleep(POST_EVENT_DELAY)
                            continue
                        if solved:
                            inc_stat("captcha_solved", label=label)
                            await asyncio.sleep(POST_EVENT_DELAY)
                            continue
                        inc_stat("captcha_failed", label=label)
                        audit_log(label, "captcha_failed", "sesi grup", user_id=0)
                        if verification_required(label):
                            Log.p("WARN", f"{log_ctx} Verifikasi manual aktif, pause loop sampai dikonfirmasi")
                            await asyncio.sleep(5)
                            continue
                        Log.p("WARN", f"{log_ctx} Verifikasi sesi grup belum berhasil, lanjut tunggu event berikutnya")
                        await asyncio.sleep(POST_EVENT_DELAY)
                        continue
                    if event == "group_active":
                        touch_activity(action="group session active", event="sedang memancing di grup", label=label)
                        await asyncio.sleep(POST_EVENT_DELAY)
                        continue

                group_wait = ALL_MODE_GROUP_WAIT if mode == "all" else 300
                join_status = await wait_and_join_group_room(
                    timeout=group_wait,
                    fish_app=fish_app,
                    label=label,
                    recent_history_limit=12,
                )
                if join_status == "inventory_full":
                    inc_stat("inventory_full", label=label)
                    Log.p("FISH", f"{log_ctx} Inventory penuh saat daftar grup → mulai sell flow")
                    await log_event("INVENTORY_FULL", label, "Saat daftar grup.")
                    if not await run_inventory_full_clean(fish_app=fish_app, label=label):
                        return
                    _account_group_sessions_done[label] = 0
                    _account_group_active[label] = False
                    clear_active_group_chat(label)
                    await asyncio.sleep(POST_EVENT_DELAY)
                    continue
                if verification_required(label):
                    Log.p("WARN", f"{log_ctx} Join grup tertunda karena verifikasi manual | {runtime_state_summary(label)}")
                    await asyncio.sleep(5)
                    continue
                if join_status not in {"joined", "group_active"}:
                    if mode == "group_room":
                        await asyncio.sleep(1.5)
                        continue
                    if _account_group_active.get(label):
                        Log.p("FISH", f"{log_ctx} All mode: sesi grup masih aktif, skip fallback private")
                        chat_filter = group_room_filter(label)
                        if chat_filter is None:
                            _account_group_active[label] = False
                            clear_active_group_chat(label)
                            await asyncio.sleep(1.5)
                            continue
                        result_task = asyncio.create_task(wait_for_fish_event(
                            timeout=300,
                            fish_app=fish_app,
                            label=label,
                            chat_filter=chat_filter,
                        ))
                    else:
                        Log.p("FISH", f"{log_ctx} All mode: tidak ada room grup, fallback private 1 sesi")
                        result_task = asyncio.create_task(wait_for_private_fish_event(
                            fish_app=fish_app,
                            label=label,
                        ))
                        if _account_private_session_active.get(label):
                            Log.p("FISH", f"{log_ctx} Private masih aktif, tunggu selesai tanpa kirim /mancing")
                        else:
                            await asyncio.sleep(0)
                            sent = await send_private_mancing(fish_app=fish_app, label=label, allow_all_fallback=True)
                            if not sent:
                                await cancel_task_safely(result_task, label=label, reason="cancel wait private fallback")
                                await asyncio.sleep(1.5)
                                continue
                else:
                    _account_group_active[label] = True
                    chat_filter = group_room_filter(label)
                    if chat_filter is None:
                        _account_group_active[label] = False
                        clear_active_group_chat(label)
                        await asyncio.sleep(1.5)
                        continue
                    result_task = asyncio.create_task(wait_for_fish_event(
                        timeout=300,
                        fish_app=fish_app,
                        label=label,
                        chat_filter=chat_filter,
                    ))
            else:
                _account_waiting_confirmation[label] = True
                Log.p("FISH", f"{log_ctx} Mengirim /mancing...")
                result_task = asyncio.create_task(wait_for_private_fish_event(
                    fish_app=fish_app,
                    label=label,
                ))
                if _account_private_session_active.get(label):
                    Log.p("FISH", f"{log_ctx} Private masih aktif, tunggu selesai tanpa kirim /mancing")
                    _account_waiting_confirmation.pop(label, None)
                else:
                    await asyncio.sleep(0)
                    sent = await send_private_mancing(fish_app=fish_app, label=label)
                    if not sent:
                        await cancel_task_safely(result_task, label=label, reason="cancel wait private event")
                        _account_waiting_confirmation.pop(label, None)
                        await asyncio.sleep(1.5)
                        continue
                    
                    confirmation_timeout = 15
                    confirmed = False
                    start_wait = time.monotonic()
                    while time.monotonic() - start_wait < confirmation_timeout:
                        if _account_private_session_active.get(label) or result_task.done():
                            confirmed = True
                            break
                        await asyncio.sleep(0.5)
                    
                    _account_waiting_confirmation.pop(label, None)
                    
                    if not confirmed:
                        await cancel_task_safely(result_task, label=label, reason="cancel unconfirmed private event")
                        _account_mancing_attempts[label] = _account_mancing_attempts.get(label, 0) + 1
                        attempts = _account_mancing_attempts[label]
                        Log.p("WARN", f"{log_ctx} Fish It tidak merespon /mancing (attempt {attempts}/3)")
                        
                        if attempts == 1:
                            Log.p("WARN", f"{log_ctx} Tunggu 30 detik sebelum coba lagi...")
                            await asyncio.sleep(30)
                        elif attempts == 2:
                            Log.p("WARN", f"{log_ctx} Tunggu 60 detik sebelum coba lagi...")
                            await asyncio.sleep(60)
                        else:
                            Log.p("ERROR", f"{log_ctx} Fish It tidak merespon setelah 3x percobaan. STOP.")
                            await notify(f"⚠️ [{label}] Fish It tidak merespon setelah 3x percobaan.\nCek manual atau tekan Start untuk mulai lagi.")
                            _account_running[label] = False
                            _account_mancing_attempts[label] = 0
                            _is_running = is_any_running()
                            break
                        continue
                    
                    _account_mancing_attempts[label] = 0

            result = await result_task

            if result is None:
                Log.p("WARN", f"{log_ctx} Timeout tunggu event mancing, coba lagi")
                await asyncio.sleep(1.5)
                continue

            event, text, event_msg = result

            if event == "done":
                inc_stat("sessions_done", label=label)
                _account_private_session_active.pop(label, None)
                active_chat = active_group_chat_target(label)
                if is_special_group_mode(label) and event_msg.chat:
                    _account_group_sessions_done[label] = _account_group_sessions_done.get(label, 0) + 1
                    _account_group_active[label] = False
                    clear_active_group_chat(label)
                    clear_special_join_state(event_msg.chat.id)
                    Log.p("FISH", f"{log_ctx} Sesi grup khusus selesai count={_account_group_sessions_done[label]}")
                    await asyncio.sleep(POST_EVENT_DELAY)
                    await maybe_open_special_group_room(label, fish_app=fish_app, reason="session_done")
                    continue
                if uses_group_room(label) and event_msg.chat and (not active_chat or str(event_msg.chat.id) == str(active_chat)):
                    _account_group_sessions_done[label] = _account_group_sessions_done.get(label, 0) + 1
                    _account_group_active[label] = False
                    clear_active_group_chat(label)
                    Log.p("FISH", f"{log_ctx} Sesi grup selesai count={_account_group_sessions_done[label]}")
                if mode == "private":
                    await private_done_delay(label)
                else:
                    Log.p("FISH", f"{log_ctx} Sesi selesai → lanjut loop")
                    await asyncio.sleep(POST_EVENT_DELAY)

            elif event == "full":
                inc_stat("inventory_full", label=label)
                _account_private_session_active.pop(label, None)
                Log.p("FISH", f"{log_ctx} Inventory penuh → mulai sell flow")
                await log_event("INVENTORY_FULL", label, f"Mode: {mode}")
                if not await run_inventory_full_clean(fish_app=fish_app, label=label):
                    return
                if uses_group_room(label):
                    _account_group_sessions_done[label] = 0
                    _account_group_active[label] = False
                    clear_active_group_chat(label)
                await asyncio.sleep(POST_EVENT_DELAY)

            elif event == "group_active":
                _account_group_active[label] = True
                if event_msg.chat:
                    set_active_group_chat(label, event_msg.chat.id)
                touch_activity(action="group session active", event="sedang memancing di grup", label=label)
                Log.p("FISH", f"{log_ctx} Bot masih sedang memancing di grup → tunggu event grup, jangan kirim private")
                await asyncio.sleep(POST_EVENT_DELAY)

            elif event == "captcha":
                Log.p("WARN", f"{log_ctx} Verifikasi terdeteksi, minta verifikasi manual...")
                solved = await solve_captcha_event_once(text, event_msg, fish_app=fish_app, label=label, source="fish_event")
                if solved is None:
                    await asyncio.sleep(POST_EVENT_DELAY)
                    continue
                if solved:
                    inc_stat("captcha_solved", label=label)
                    await notify(f"✅ [{label}] Verifikasi selesai. Loop lanjut.")
                    await asyncio.sleep(POST_EVENT_DELAY)
                    continue

                inc_stat("captcha_failed", label=label)
                audit_log(label, "captcha_failed", "private/group event", user_id=0)
                if verification_required(label):
                    Log.p("WARN", f"{log_ctx} Verifikasi manual aktif, pause loop sampai dikonfirmasi")
                    await asyncio.sleep(5)
                    continue
                Log.p("WARN", f"{log_ctx} Verifikasi belum berhasil, lanjut otomatis dan tunggu event berikutnya")
                await asyncio.sleep(POST_EVENT_DELAY)
                continue

        except Exception as e:
            Log.p("ERROR", f"{fish_log_ctx(label)} Error di fishing_loop: {e}")
            if is_connection_lost_error(e):
                await recover_account_client_connection(fish_app=fish_app, label=label, reason=str(e))
            await send_traceback_log(e, label=label, mode=f"fishing_loop {mode_display_name(current_fish_mode(label))}")
            await log_error_event_once(
                "LOOP_ERROR",
                label,
                f"Error loop mancing: {str(e)[:500]}",
                section=f"fishing_loop mode={current_fish_mode(label)}",
                fingerprint=f"fishing_loop:{type(e).__name__}",
            )
            await notify(f"❌ [{label}] Error loop mancing:\n{e}\nRetry dalam 10 detik...")
            await human_delay(10, 15)

    _account_running[label] = False
    _is_running = is_any_running()
    Log.p("FISH", f"{fish_log_ctx(label)} Loop mancing dihentikan.")
    await notify(f"🛑 [{label}] Loop mancing dihentikan.")

