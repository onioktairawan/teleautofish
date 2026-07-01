from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def request_userbot_restart(message):
    _shutdown_event.set()
    await stop_all_accounts()
    progress_msg = None
    try:
        await message.delete()
    except Exception:
        pass
    try:
        progress_msg = await message.reply_text("🔄 Restart bot sedang diproses.")
    except Exception:
        progress_msg = None
    asyncio.create_task(
        restart_current_process(
            chat_id=progress_msg.chat.id if progress_msg else OWNER_ID,
            message_id=progress_msg.id if progress_msg else 0,
            source="userbot",
        )
    )


async def fetch_fish_command(command: str, keywords: list[str], timeout: int = 30, label: str = "main") -> str | None:
    label = ctx_label(label)
    fish_app = await account_client_or_none(label)
    if not fish_app:
        Log.p("WARN", f"[{label}] Command {command} dibatalkan: userbot belum siap")
        return None
    target_bot = private_command_bot_username(label)
    set_command_mode(label, True)
    try:
        reply_task = asyncio.create_task(wait_for_bot_reply(keywords=keywords, timeout=timeout, fish_app=fish_app, label=label, bot_username=target_bot))
        await asyncio.sleep(0)
        sent = await safe_send(target_bot, command, fish_app=fish_app, label=label)
        if not sent:
            await cancel_task_safely(reply_task, label=label, reason=f"cancel wait reply {command}")
            return None
        return await reply_task
    finally:
        set_command_mode(label, False)


async def start_logged_in_account(label: str):
    client = await start_account_client(label)
    if client:
        await start_account_loop(label, client)


async def stop_account_client(label: str):
    label = ctx_label(label)
    async with get_lifecycle_lock(label):
        await stop_account_loop_runtime(label, persist_auto_start=False)
        client = _account_clients.pop(label, None)
        remove_private_captcha_watcher(label, client)
        remove_user_media_log_watcher(label, client)
        if client:
            try:
                await client.stop()
            except Exception as e:
                Log.p("WARN", f"[{label}] Gagal stop client sebelum login ulang: {e}")
        cleanup_account_runtime_state(label)


def cleanup_account_runtime_state(label: str):
    label = ctx_label(label)
    for mapping in (
        _account_running,
        _account_tasks,
        _account_private_boost_tasks,
        _account_clients,
        _account_last_activity,
        _account_last_action,
        _account_last_event,
        _account_last_sell,
        _account_last_captcha_response_text,
        _account_captcha_locks,
        _account_captcha_seen,
        _account_captcha_handlers,
        _account_user_log_handlers,
        _account_user_log_identity,
        _account_group_sessions_done,
        _account_command_mode,
        _account_group_active,
        _account_active_group_chat,
        _account_pending_group_join,
        _account_private_session_waiting,
        _account_private_session_active,
        _account_private_boost_until,
        _account_private_boost_last,
        _account_sell_locks,
        _account_inventory_clean_locks,
        _account_last_inventory_read_summary,
        _sell_flow_log_messages,
        _sell_flow_log_states,
    ):
        mapping.pop(label, None)

    _account_required_channel_joined.discard(label)
    _account_required_channel_status.pop(label, None)
    for key in list(_account_notify_message_ids):
        if key[0] == label:
            _account_notify_message_ids.pop(key, None)
    for key in list(_account_notify_locks):
        if key[0] == label:
            _account_notify_locks.pop(key, None)
    for key in list(_special_group_write_blocked_until):
        if key[1] == label:
            _special_group_write_blocked_until.pop(key, None)
            _special_group_write_blocked_reason.pop(key, None)
            _special_group_write_blocked_stage.pop(key, None)
    for joined in _special_join_success.values():
        joined.discard(label)
    for failed in _special_join_failed.values():
        failed.pop(label, None)


async def clear_stuck_account_runtime(label: str, user_id: int = 0) -> tuple[bool, str]:
    label = ctx_label(label)
    sell_lock = _account_sell_locks.get(label)
    inventory_lock = _account_inventory_clean_locks.get(label)
    captcha_lock = _account_captcha_locks.get(label)
    if sell_lock and sell_lock.locked():
        return False, "Akun sedang menjalankan sell flow. Clear Stuck dibatalkan supaya jual tidak setengah jalan."
    if inventory_lock and inventory_lock.locked():
        return False, "Akun sedang membersihkan/membaca inventory. Clear Stuck dibatalkan supaya flow tidak bentrok."
    if captcha_lock and captcha_lock.locked():
        return False, "Akun sedang memproses captcha. Coba lagi beberapa detik lagi kalau masih nyangkut."

    was_running = bool(_account_running.get(label))
    task = _account_tasks.get(label)
    task_alive = bool(task and not task.done())
    cleared = []

    if verification_required(label):
        save_verification_state(label, False)
        cleared.append("verifikasi manual")
    if _account_pending_group_join.pop(label, None):
        cleared.append("pending join grup")
    if _account_group_active.pop(label, None) is not None:
        cleared.append("status sesi grup")
    if _account_active_group_chat.pop(label, None) is not None:
        cleared.append("active group chat")
    if _account_private_session_waiting.pop(label, None) is not None:
        cleared.append("private waiting")
    if _account_private_wait_started.pop(label, None) is not None:
        cleared.append("private wait timer")
    if _account_private_session_active.pop(label, None) is not None:
        cleared.append("sesi private")
    if _account_waiting_confirmation.pop(label, None) is not None:
        cleared.append("waiting confirmation")
    if _account_mode_switch_pending.pop(label, None) is not None:
        cleared.append("pending switch mode")
    if _account_last_captcha_response_text.pop(label, None) is not None:
        cleared.append("cache respons verifikasi")
    if _account_captcha_seen.pop(label, None) is not None:
        cleared.append("captcha seen cache")
    if _account_seen_events.pop(label, None) is not None:
        cleared.append("event guard")
    if _account_action_guard.pop(label, None) is not None:
        cleared.append("action guard")
    if _account_last_inventory_read_summary.pop(label, None) is not None:
        cleared.append("cache inventory")
    for failed in _special_join_failed.values():
        if failed.pop(label, None) is not None:
            cleared.append("status join gagal")
            break

    resumed = False
    resume_note = ""
    if was_running and not task_alive:
        if maintenance_blocks_account(label):
            resume_note = "Loop belum dilanjutkan karena maintenance aktif."
        else:
            client = await start_account_client(label)
            if client:
                await start_account_loop(label, client)
                resumed = True
                resume_note = "Loop otomatis dilanjutkan."
            else:
                resume_note = "Loop belum bisa dilanjutkan karena userbot gagal start/login."
    elif was_running:
        resume_note = "Loop masih aktif, state runtime sudah dibersihkan."
    else:
        resume_note = "Akun sedang stopped, jadi loop tidak distart otomatis."

    audit_log(label, "owner_clear_stuck", f"cleared={', '.join(cleared) or '-'}; resumed={resumed}", user_id=user_id)
    Log.p("BOT", f"[{label}] Clear stuck by owner {user_id} | cleared={', '.join(cleared) or '-'} | resumed={resumed}")
    body = (
        f"Nama: {account_name_for_label(label, user_id)}\n"
        f"Sebelumnya running: {'ya' if was_running else 'tidak'}\n"
        f"Task loop aktif: {'ya' if task_alive else 'tidak'}\n"
        f"Dibersihkan: {', '.join(cleared) if cleared else '-'}\n"
        f"Resume: {resume_note}"
    )
    return True, body


async def remove_user_sessions(user_id: int) -> dict:
    user_id = int(user_id or 0)
    if user_id <= 0 or user_id == OWNER_ID:
        return {"labels": [], "db_deleted": 0, "files_deleted": 0}

    labels: list[str] = []
    session_names: list[str] = []
    if mongo_enabled():
        try:
            docs = list(mongo_col.find({"type": "account", "owner_ids": user_id, "label": {"$ne": "main"}}))
            for doc in docs:
                label = doc.get("label")
                if label:
                    labels.append(str(label))
                session_name = doc.get("session_name")
                if session_name:
                    session_names.append(str(session_name))
        except PyMongoError as e:
            Log.p("WARN", f"Mongo cari session user {user_id} gagal: {e}")

    fallback_label = default_user_account_label(user_id)
    fallback_session = f"fishbot_session_{fallback_label}"
    if fallback_label not in labels:
        labels.append(fallback_label)
    if fallback_session not in session_names:
        session_names.append(fallback_session)

    for label in labels:
        await stop_account_client(label)
        cleanup_account_runtime_state(label)

    for selected_user, selected_label in list(_selected_account_by_user.items()):
        if selected_user == user_id or selected_label in labels:
            _selected_account_by_user.pop(selected_user, None)

    db_deleted = 0
    if mongo_enabled():
        try:
            mongo_col.update_many(
                {"type": "account", "owner_ids": user_id},
                {"$pull": {"owner_ids": user_id}, "$set": {"updated_at": now_wib()}},
            )
            invalidate_accounts_cache()
        except PyMongoError as e:
            Log.p("WARN", f"Mongo cabut owner_ids user {user_id} gagal: {e}")
    if labels:
        db_deleted += db_delete_docs({"type": "account", "label": {"$in": labels}})
    db_deleted += db_delete_docs({"type": "account", "owner_ids": user_id, "label": {"$ne": "main"}})

    files_deleted = 0
    for session_name in set(session_names):
        files_deleted += remove_session_files(session_name)

    return {"labels": labels, "db_deleted": db_deleted, "files_deleted": files_deleted}


async def cancel_userbot_login(user_id: int):
    user_id = int(user_id)
    task = _login_flow_tasks.pop(user_id, None)
    await cancel_task_safely(task, label="main", reason="cancel login flow timer")
    flow = _login_flows.pop(user_id, None)
    client = flow.get("client") if flow else None
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    if flow and not flow.get("had_session"):
        remove_session_files(flow.get("session_name", ""))


def set_login_flow(user_id: int, flow: dict):
    user_id = int(user_id)
    _login_flows[user_id] = flow
    task = _login_flow_tasks.pop(user_id, None)
    cancel_task_background(task, label="main", reason="replace login flow timer")
    try:
        _login_flow_tasks[user_id] = asyncio.create_task(expire_login_flow(user_id))
    except RuntimeError:
        pass


async def expire_login_flow(user_id: int):
    await asyncio.sleep(LOGIN_FLOW_TIMEOUT)
    flow = _login_flows.get(int(user_id))
    if flow:
        await cancel_userbot_login(user_id)
        audit_log(flow.get("label", default_user_account_label(user_id)), "login_timeout", f"timeout={LOGIN_FLOW_TIMEOUT}s", user_id=user_id)


async def finish_userbot_login(user_id: int, flow: dict, client: Client, update: Update):
    label = flow["label"]
    session_name = flow["session_name"]
    try:
        me = await client.get_me()
    except FloodWait as e:
        wait = int(getattr(e, "value", 5)) + 1
        Log.p("WARN", f"FloodWait {wait}s saat get_me login, tunggu...")
        await asyncio.sleep(wait)
        me = await client.get_me()
    await ensure_required_channel_joined(client, label=label)
    try:
        await client.disconnect()
    except Exception:
        pass

    existing_account = db_get_doc("account", label) if mongo_enabled() else load_account(label)
    existing_account = existing_account or default_account_doc(label)
    owner_ids = account_owner_ids(existing_account, user_id)
    if label != "main" and user_id != OWNER_ID:
        owner_ids = sorted({owner_id for owner_id in owner_ids if owner_id != OWNER_ID} | {user_id})
    elif label == "main":
        owner_ids = sorted(set(owner_ids) | {OWNER_ID})
    account_update = {
        "session_name": session_name,
        "owner_ids": owner_ids,
        "enabled": True,
        "auto_start": True,
        "mode": existing_account.get("mode", "private"),
        "groups": existing_account.get("groups", []),
        "telegram_user": {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": getattr(me, "last_name", None),
            "full_name": " ".join(part for part in [me.first_name, getattr(me, "last_name", None)] if part),
            "username": me.username,
            "is_premium": telegram_user_premium_flag(me),
            "premium_checked_at": now_wib(),
        },
        "restored_needs_login": False,
        "last_login_error": "",
    }
    set_main_premium_status_from_user(me, label)
    display_name = account_display_name({"telegram_user": account_update["telegram_user"]}, user_id)
    db_upsert_doc("account", label, account_update)
    audit_log(label, "login_userbot", display_name, user_id=user_id)
    _selected_account_by_user[int(user_id)] = label
    _login_flows.pop(int(user_id), None)
    task = _login_flow_tasks.pop(int(user_id), None)
    await cancel_task_safely(task, label=label, reason="finish login flow timer")
    cleanup_account_runtime_state(label)
    await update.message.reply_text(
        "✅ Login userbot berhasil.\n"
        f"Akun Telegram: {display_name}\n\n"
        "Auto mancing akan langsung dijalankan.",
        reply_markup=main_menu_keyboard(user_id),
    )
    await start_logged_in_account(label)


async def submit_login_phone(update: Update, user_id: int, flow: dict, phone: str) -> bool:
    label = flow["label"]
    session_name = flow["session_name"]
    client = Client(
        session_name,
        api_id=API_ID,
        api_hash=API_HASH,
        device_model=PYRO_DEVICE_MODEL,
        system_version=PYRO_SYSTEM_VERSION,
        app_version=PYRO_APP_VERSION,
        workdir=BASE_DIR,
        sleep_threshold=60,
    )
    try:
        await client.connect()
        sent = await client.send_code(phone)
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        await cancel_userbot_login(user_id)
        audit_log(label, "login_failed", f"kirim OTP gagal: {e}", user_id=user_id)
        await update.message.reply_text(f"❌ Gagal kirim OTP: {e}", reply_markup=ReplyKeyboardRemove())
        return True

    flow.update({
        "step": "otp",
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
        "client": client,
    })
    await update.message.reply_text(
        "📩 OTP sudah dikirim Telegram.\n\n"
        "Kirim OTP dengan spasi antar angka.\n"
        "Contoh: `1 2 3 4 5`\n\n"
        "Jangan kirim format 12345.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return True


async def handle_userbot_login_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.effective_user.id)
    if maintenance_enabled() and not can_manage_admins(user_id):
        await update.message.reply_text(maintenance_message_text(), parse_mode="HTML")
        return
    flow = _login_flows.get(user_id)
    if not flow or flow.get("step") != "phone":
        return

    contact = update.message.contact
    if not contact:
        return
    if safe_user_id(getattr(contact, "user_id", 0)) != user_id:
        await update.message.reply_text(
            "⚠️ Kontak harus milik akun Telegram lu sendiri. Klik Kontak Gua atau ketik nomor manual.",
            reply_markup=contact_request_keyboard(),
        )
        return

    phone = re.sub(r"\s+", "", contact.phone_number or "")
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"
    if not re.fullmatch(r"\+?\d{8,16}", phone):
        await update.message.reply_text(
            "⚠️ Nomor dari kontak tidak valid. Ketik manual dengan format internasional, contoh: +6281234567890",
            reply_markup=contact_request_keyboard(),
        )
        return
    await submit_login_phone(update, user_id, flow, phone)


async def handle_userbot_login_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = int(update.effective_user.id)
    flow = _login_flows.get(user_id)
    if not flow:
        return False

    text = (update.message.text or "").strip()
    step = flow.get("step")
    client = flow.get("client")

    if step == "phone":
        phone = re.sub(r"\s+", "", text)
        if not re.fullmatch(r"\+?\d{8,16}", phone):
            await update.message.reply_text(
                "⚠️ Nomor HP tidak valid. Kirim format internasional, contoh: +6281234567890",
                reply_markup=contact_request_keyboard(),
            )
            return True
        return await submit_login_phone(update, user_id, flow, phone)

    if step == "otp":
        if " " not in text.strip():
            await update.message.reply_text("⚠️ OTP wajib pakai spasi. Contoh: `1 2 3 4 5`", reply_markup=input_flow_keyboard())
            return True
        code = re.sub(r"\s+", "", text)
        if not re.fullmatch(r"\d{5,6}", code):
            await update.message.reply_text("⚠️ OTP tidak valid. Kirim ulang, contoh: `1 2 3 4 5`", reply_markup=input_flow_keyboard())
            return True

        try:
            await client.sign_in(flow["phone"], flow["phone_code_hash"], code)
            await finish_userbot_login(user_id, flow, client, update)
        except SessionPasswordNeeded:
            flow["step"] = "password"
            await update.message.reply_text("🔐 Akun ini memakai 2FA. Kirim password 2FA Telegram kamu.", reply_markup=input_flow_keyboard())
        except PhoneCodeInvalid:
            audit_log(flow.get("label", selected_account_label(user_id)), "login_failed", "OTP salah", user_id=user_id)
            await update.message.reply_text("❌ OTP salah. Kirim OTP yang benar dengan spasi, contoh: `1 2 3 4 5`", reply_markup=input_flow_keyboard())
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            await cancel_userbot_login(user_id)
            audit_log(flow.get("label", selected_account_label(user_id)), "login_failed", str(e), user_id=user_id)
            await update.message.reply_text(f"❌ Login gagal: {e}", reply_markup=input_flow_keyboard())
        return True

    if step == "password":
        try:
            await client.check_password(text)
            await finish_userbot_login(user_id, flow, client, update)
        except Exception as e:
            audit_log(flow.get("label", selected_account_label(user_id)), "login_failed", f"2FA gagal: {e}", user_id=user_id)
            await update.message.reply_text(f"❌ Password 2FA salah/gagal: {e}\nKirim password 2FA lagi atau tekan menu untuk batal.", reply_markup=input_flow_keyboard())
        return True

    return False


