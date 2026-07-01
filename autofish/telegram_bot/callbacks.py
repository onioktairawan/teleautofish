from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def tg_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _is_running, _shutdown_event

    query = update.callback_query
    if not query:
        return

    user_id = update.effective_user.id
    if is_callback_rate_limited(user_id):
        await safe_query_answer(query, "Terlalu cepat.", show_alert=False)
        return

    data = query.data or ""
    if data == "report:start":
        await start_user_report_flow(update, context, query=query)
        return
    if data == "report:cancel":
        clear_pending_input(user_id)
        await safe_query_answer(query, "Dibatalkan")
        try:
            await query.edit_message_text("Laporan dibatalkan.", reply_markup=maintenance_keyboard() if maintenance_enabled() and not can_manage_admins(user_id) else main_menu_keyboard(user_id), parse_mode="HTML")
        except Exception:
            pass
        return
    if maintenance_enabled() and not can_manage_admins(user_id):
        await safe_query_answer(query, "Bot sedang maintenance.", show_alert=True)
        try:
            await query.edit_message_text(maintenance_message_text(), reply_markup=maintenance_keyboard(), parse_mode="HTML")
        except Exception:
            pass
        return

    if data == "fish:help":
        await safe_query_answer(query, "Help")
        await reply_clean(query, 
            format_help_html(),
            reply_markup=help_main_keyboard(user_id),
            parse_mode="HTML",
        )
        return

    if data.startswith("help:topic:"):
        topic = data.split(":", 2)[2]
        await safe_query_answer(query, "Help")
        await reply_clean(query,
            format_help_topic_html(topic),
            reply_markup=help_topic_keyboard(user_id),
            parse_mode="HTML",
        )
        return

    if not is_admin_user(user_id):
        await safe_query_answer(query, "Tidak punya akses.", show_alert=True)
        return

    label = selected_account_label(user_id)
    if data.startswith("verify:done:") or data.startswith("verify:stop:"):
        parts = data.split(":", 2)
        target_label = parts[2] if len(parts) > 2 else label
        target_label = safe_label(target_label)
        if not can_access_account(user_id, target_label):
            await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
            return
        if data.startswith("verify:stop:"):
            await stop_account_loop_runtime(target_label, persist_auto_start=True)
            save_verification_state(target_label, False)
            await safe_query_answer(query, "Loop dihentikan")
            await reply_clean(
                query,
                "🛑 <b>Verifikasi</b>\n\n"
                + blockquote(f"Nama: {account_name_for_label(target_label, user_id)}\nStatus: loop dihentikan"),
                reply_markup=back_keyboard("menu:fishing"),
                parse_mode="HTML",
            )
            return
        await safe_query_answer(query, "Mencoba lanjut")
        ok = await complete_manual_verification(target_label, user_id=user_id)
        status = "loop dilanjutkan" if ok else "belum bisa lanjut. Pastikan Fish It sudah kirim pesan verifikasi berhasil lalu tekan lagi."
        await reply_clean(
            query,
            "✅ <b>Verifikasi</b>\n\n"
            + blockquote(f"Nama: {account_name_for_label(target_label, user_id)}\nStatus: {status}"),
            reply_markup=back_keyboard("menu:fishing"),
            parse_mode="HTML",
        )
        return

    account_required_prefixes = ("fish:", "mode:set:", "groups:", "special:", "private:", "rules:", "menu:inventory:")
    account_required_menus = {"menu:fishing", "menu:inventory", "menu:rules", "menu:monitoring", "menu:mode", "menu:groups", "menu:special_group", "menu:private"}
    if (data.startswith(account_required_prefixes) or data in account_required_menus) and not can_access_account(user_id, label):
        await safe_query_answer(query, "Login Telegram dulu untuk akses fitur akun.", show_alert=True)
        await query.edit_message_text(format_userbot_text(user_id), reply_markup=userbot_menu_keyboard(label))
        return

    if data == "menu:accounts":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Akun saya")
            await query.edit_message_text(format_monitoring_menu(label, user_id), reply_markup=back_keyboard("menu:main"), parse_mode="HTML")
            return
        await safe_query_answer(query, "Accounts")
        clear_pending_input(user_id)
        await query.edit_message_text(format_accounts_text(user_id), reply_markup=accounts_menu_keyboard(user_id), parse_mode="HTML")
        return

    if data == "menu:account_status":
        await safe_query_answer(query, "Akun saya")
        clear_pending_input(user_id)
        await reply_clean(query, format_monitoring_menu(label, user_id), reply_markup=back_keyboard("menu:main"), parse_mode="HTML")
        return

    if data.startswith("account:page:"):
        try:
            page = int(data.split(":", 2)[2])
        except (ValueError, IndexError):
            page = 0
        await safe_query_answer(query, "Accounts")
        clear_pending_input(user_id)
        await query.edit_message_text(
            format_accounts_text(user_id, page),
            reply_markup=accounts_menu_keyboard(user_id, page),
            parse_mode="HTML",
        )
        return

    if data.startswith("account:select:"):
        parts = data.split(":", 3)
        try:
            page = int(parts[2])
            selected = parts[3]
        except (ValueError, IndexError):
            page = 0
            selected = data.split(":", 2)[2]
        if not can_access_account(user_id, selected):
            await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
            return
        clear_pending_input(user_id)
        _selected_account_by_user[user_id] = selected
        label = selected
        await safe_query_answer(query, f"Nama: {account_name_for_label(selected, user_id)}")
        if can_manage_admins(user_id) and selected != "main":
            await reply_clean(query, 
                format_monitoring_menu(label, user_id),
                reply_markup=account_detail_keyboard(label, page),
                parse_mode="HTML",
            )
            return
        await reply_clean(query, format_main_menu(label, user_id), reply_markup=accounts_back_keyboard(page), parse_mode="HTML")
        return

    if data == "menu:main":
        await safe_query_answer(query, "Menu utama")
        clear_pending_input(user_id)
        await cancel_userbot_login(user_id)
        await query.edit_message_text(format_main_menu(label, user_id), reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    if data == "menu:fishing":
        await safe_query_answer(query, "Fishing")
        clear_pending_input(user_id)
        await query.edit_message_text(format_fishing_menu(label), reply_markup=fishing_menu_keyboard(), parse_mode="HTML")
        return

    if data == "menu:inventory" or data.startswith("menu:inventory:"):
        if data.startswith("menu:inventory:"):
            label = callback_label_or_selected(data, "menu:inventory:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        await safe_query_answer(query, "Inventory")
        clear_pending_input(user_id)
        await query.edit_message_text(format_inventory_menu(label), reply_markup=inventory_menu_keyboard(label), parse_mode="HTML")
        return

    if data == "menu:rules":
        await safe_query_answer(query, "Rules")
        clear_pending_input(user_id)
        await query.edit_message_text(format_rules_text(label), reply_markup=rules_menu_keyboard(), parse_mode="HTML")
        return

    if data == "menu:monitoring":
        await safe_query_answer(query, "Monitoring")
        clear_pending_input(user_id)
        await query.edit_message_text(format_monitoring_menu(label, user_id), reply_markup=monitoring_menu_keyboard(user_id), parse_mode="HTML")
        return

    if data == "menu:settings":
        await safe_query_answer(query, "Settings")
        clear_pending_input(user_id)
        await cancel_userbot_login(user_id)
        await query.edit_message_text(format_settings_menu(label, user_id), reply_markup=settings_menu_keyboard(user_id), parse_mode="HTML")
        return

    if data == "menu:userbot":
        await safe_query_answer(query, "Userbot")
        clear_pending_input(user_id)
        await query.edit_message_text(format_userbot_text(user_id), reply_markup=userbot_menu_keyboard(label))
        return

    if data == "menu:groups":
        await safe_query_answer(query, "Groups")
        clear_pending_input(user_id)
        await query.edit_message_text(format_groups_text(label), reply_markup=groups_menu_keyboard(), parse_mode="HTML")
        return

    if data == "menu:special_group":
        await safe_query_answer(query, "Grup khusus")
        clear_pending_input(user_id)
        await query.edit_message_text(format_special_group_text(label), reply_markup=special_group_menu_keyboard(label), parse_mode="HTML")
        return

    if data == "menu:private":
        await safe_query_answer(query, "Private")
        clear_pending_input(user_id)
        await query.edit_message_text(format_private_settings_text(label), reply_markup=private_settings_keyboard(label), parse_mode="HTML")
        return

    if data == "menu:mode":
        await safe_query_answer(query, "Mode")
        clear_pending_input(user_id)
        await query.edit_message_text(format_mode_text(label), reply_markup=mode_menu_keyboard())
        return

    if data == "private:boost_toggle":
        enabled = not private_auto_boost_enabled(label)
        save_private_auto_boost(label, enabled)
        if enabled:
            save_private_boost_paused(label, False)
            _account_private_boost_last[label] = "auto boost dinyalakan"
        else:
            _account_private_boost_last[label] = "auto boost dimatikan"
        await safe_query_answer(query, "Auto boost private ON" if enabled else "Auto boost private OFF")
        await query.edit_message_text(format_private_settings_text(label), reply_markup=private_settings_keyboard(label), parse_mode="HTML")
        return

    if data == "private:boost_reset":
        save_private_boost_paused(label, False)
        _account_private_boost_until.pop(label, None)
        _account_private_boost_last[label] = "siap dicoba lagi"
        await safe_query_answer(query, "Boost private siap dicoba lagi")
        await query.edit_message_text(format_private_settings_text(label), reply_markup=private_settings_keyboard(label), parse_mode="HTML")
        return

    if data == "private:bot_set":
        set_pending_input(user_id, f"private_bot_set:{label}")
        await safe_query_answer(query, "Kirim username bot")
        await query.edit_message_text(
            "🤖 <b>Ubah Bot Private</b>\n\n"
            + blockquote(
                f"Nama: {account_name_for_label(label, user_id)}\n"
                "Kirim username bot private yang mau dipakai saat mode private.\n\n"
                "Contoh: @fish_it_vip5_bot"
            ),
            reply_markup=back_keyboard("menu:private"),
            parse_mode="HTML",
        )
        return

    if data == "private:bot_reset":
        reset_private_bot_username(label)
        await safe_query_answer(query, "Bot private kembali default")
        await query.edit_message_text(format_private_settings_text(label), reply_markup=private_settings_keyboard(label), parse_mode="HTML")
        return

    if data == "private:refresh":
        await safe_query_answer(query, "Refresh")
        await query.edit_message_text(format_private_settings_text(label), reply_markup=private_settings_keyboard(label), parse_mode="HTML")
        return

    if data.startswith("mode:set:"):
        mode = data.split(":", 2)[2]
        try:
            if _account_private_session_active.get(label) or _account_group_active.get(label):
                _account_mode_switch_pending[label] = mode
                await safe_query_answer(query, f"Mode akan diubah ke {mode} setelah sesi selesai")
                await reply_clean(query, 
                    "🔁 <b>Perubahan Mode Ditunda</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nMode Baru (Pending): {mode}\n(Akan diterapkan setelah sesi saat ini selesai)"),
                    reply_markup=back_keyboard("menu:mode"),
                    parse_mode="HTML",
                )
                Log.p("BOT", f"[{label}] Pergantian mode ke {mode} ditunda karena sesi masih aktif")
                await log_event("MODE_PENDING", label, f"Mode ditunda ke: {mode}\nOleh: {user_id}")
            else:
                save_runtime_mode(mode, label)
                _account_mode_switch_pending.pop(label, None)
                await safe_query_answer(query, f"Mode diubah: {mode}")
                await reply_clean(query, 
                    "🔁 <b>Mode Diubah</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nMode: {mode}"),
                    reply_markup=back_keyboard("menu:mode"),
                    parse_mode="HTML",
                )
                Log.p("BOT", f"[{label}] Mode diubah ke {mode} dari panel")
                await log_event("MODE", label, f"Mode diubah ke: {mode}\nOleh: {user_id}")
        except ValueError:
            await safe_query_answer(query, "Mode tidak valid.", show_alert=True)
        return

    if data == "fish:start":
        await safe_query_answer(query, "Start")
        if maintenance_blocks_account(label):
            await reply_clean(query, maintenance_message_text(), reply_markup=back_keyboard("menu:fishing"), parse_mode="HTML")
            return
        if _account_running.get(label):
            await reply_clean(query, 
                "⚠️ <b>Auto Mancing</b>\n\n" + blockquote("Auto mancing sudah jalan."),
                reply_markup=back_keyboard("menu:fishing"),
                parse_mode="HTML",
            )
            return
        _shutdown_event.clear()
        await reply_clean(query, 
            "🎣 <b>Auto Mancing</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nStatus: mulai jalan"),
            reply_markup=back_keyboard("menu:fishing"),
            parse_mode="HTML",
        )
        Log.p("BOT", f"Start mancing dari tombol Telegram untuk {label}")
        client = await start_account_client(label)
        if client:
            await start_account_loop(label, client)
            audit_log(label, "start_loop", "started from panel", user_id=user_id)
            await log_event("START", label, f"Auto mancing dimulai dari panel.\nOleh: {user_id}")
        else:
            await reply_clean(query, 
                "❌ <b>Auto Mancing</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nStatus: gagal jalan. Cek login Telegram dulu."),
                reply_markup=back_keyboard("menu:fishing"),
                parse_mode="HTML",
            )
        return

    if data == "fish:stop":
        await safe_query_answer(query, "Stop")
        await stop_account_loop_runtime(label, persist_auto_start=True)
        audit_log(label, "stop_loop", "stopped from panel", user_id=user_id)
        await log_event("STOP", label, f"Auto mancing dihentikan dari panel.\nOleh: {user_id}")
        await reply_clean(query, 
            "🛑 <b>Auto Mancing</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nStatus: berhenti"),
            reply_markup=back_keyboard("menu:fishing"),
            parse_mode="HTML",
        )
        Log.p("BOT", f"Stop mancing dari tombol Telegram untuk {label}")
        return

    if data == "fish:restart":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya superadmin yang bisa restart bot.", show_alert=True)
            return
        await safe_query_answer(query, "Restarting...")
        try:
            await query.message.delete()
        except Exception:
            pass
        await request_bot_restart(query.message.chat.id, query.message.chat.send_message, user_id)
        return

    if data == "fish:status":
        await safe_query_answer(query, "Status")
        await reply_clean(query, format_monitoring_menu(label, user_id), reply_markup=back_keyboard("menu:monitoring"), parse_mode="HTML")
        return

    if data == "fish:stats":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Stats hanya untuk owner.", show_alert=True)
            return
        await safe_query_answer(query, "Stats")
        await reply_clean(query, format_stats_text(label), reply_markup=back_keyboard("menu:monitoring"), parse_mode="HTML")
        return

    if data == "admin:list":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya superadmin yang bisa lihat admin list.", show_alert=True)
            return
        await safe_query_answer(query, "Admin list")
        admins = "\n".join(f"• {admin_display_name(admin_id)}" for admin_id in sorted(load_admin_ids()))
        await reply_clean(query, 
            "👥 <b>Admin Aktif</b>\n\n" + expandable_blockquote(f"{admins}\n\nOwner utama: {admin_display_name(OWNER_ID)}"),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "admin:add":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama yang bisa tambah admin.", show_alert=True)
            return
        await safe_query_answer(query, "Mode tambah admin")
        set_pending_input(user_id, "admin_add")
        await reply_clean(query, 
            "👤 <b>Tambah Admin</b>\n\n" + expandable_blockquote(
                "Kirim Telegram user ID admin baru.\n"
                "Bisa banyak, pisahkan dengan baris baru atau koma."
            ),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "userbot:login":
        await safe_query_answer(query)
        clear_pending_input(user_id)
        login_label = preferred_login_label(user_id)
        session_name = load_account(login_label).get("session_name") or f"fishbot_session_{login_label}"
        if login_label == "main" and user_id != OWNER_ID:
            login_label = default_user_account_label(user_id)
            session_name = f"fishbot_session_{login_label}"
        await cancel_userbot_login(user_id)
        await stop_account_client(login_label)
        set_login_flow(user_id, {
            "step": "phone",
            "label": login_label,
            "session_name": session_name,
            "had_session": any(path.exists() for path in session_files_for_name(session_name)),
        })
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="🔐 <b>Login Userbot</b>\n\n" + expandable_blockquote(
                "Klik tombol Kontak Gua buat kirim Nomor Telepon Telegram lu."
            ),
            reply_markup=contact_request_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "groups:list":
        await safe_query_answer(query, "Groups")
        clear_pending_input(user_id)
        await reply_clean(query, format_groups_text(label), reply_markup=back_keyboard("menu:groups"), parse_mode="HTML")
        return

    if data == "groups:add":
        await safe_query_answer(query, "Tambah group")
        set_pending_input(user_id, f"group_add:{label}")
        await reply_clean(query, 
            "➕ <b>Tambah Group</b>\n\n" + expandable_blockquote(
                "Kirim chat ID atau username grup mancing.\n"
                "Bisa banyak, pisahkan dengan baris baru, koma, atau spasi.\n\n"
                "Contoh: -1001234567890"
            ),
            reply_markup=back_keyboard("menu:groups"),
            parse_mode="HTML",
        )
        return

    if data == "groups:del":
        await safe_query_answer(query, "Hapus group")
        set_pending_input(user_id, f"group_del:{label}")
        await reply_clean(query, 
            "🗑 <b>Hapus Group</b>\n\n" + expandable_blockquote(
                "Kirim chat ID atau username grup yang mau dihapus."
            ),
            reply_markup=back_keyboard("menu:groups"),
            parse_mode="HTML",
        )
        return

    if data == "special:set":
        await safe_query_answer(query, "Set grup khusus")
        set_pending_input(user_id, f"special_group_set:{label}")
        await reply_clean(query, 
            "🎯 <b>Set Grup Khusus</b>\n\n" + expandable_blockquote(
                "Kirim 1 chat ID atau username grup khusus.\n\n"
                "Contoh: -1001234567890"
            ),
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )
        return

    if data == "special:clear":
        await safe_query_answer(query, "Hapus grup khusus")
        save_special_group_chat("", label=label)
        await reply_clean(query, 
            "🎯 <b>Grup Khusus</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nGrup khusus dihapus."),
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )
        return

    if data == "special:auto_toggle":
        enabled = not special_auto_open_enabled(label)
        save_special_auto_open(label, enabled)
        await safe_query_answer(query, "Auto open ON" if enabled else "Auto open OFF")
        await query.edit_message_text(format_special_group_text(label), reply_markup=special_group_menu_keyboard(label), parse_mode="HTML")
        return

    if data == "special:boost_toggle":
        enabled = not special_auto_boost_enabled(label)
        save_special_auto_boost(label, enabled)
        await safe_query_answer(query, "Boost ON" if enabled else "Boost OFF")
        await query.edit_message_text(format_special_group_text(label), reply_markup=special_group_menu_keyboard(label), parse_mode="HTML")
        return

    if data == "special:delay":
        await safe_query_answer(query, "Waktu tunggu")
        await reply_clean(query, 
            "⏱ <b>Waktu Tunggu Auto Open</b>\n\n" + expandable_blockquote(
                "Pilih jeda setelah WAKTU HABIS sebelum bot membuka room otomatis.\n"
                "Kalau selama jeda ada room baru, bot tetap batal open."
            ),
            reply_markup=special_delay_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "special:delay:custom":
        await safe_query_answer(query, "Custom")
        set_pending_input(user_id, f"special_delay_custom:{label}")
        await reply_clean(query, 
            "⏱ <b>Custom Waktu Tunggu</b>\n\n" + expandable_blockquote(
                "Kirim rentang detik minimum dan maksimum.\n"
                "Contoh: 9-12 atau 9 12.\n\n"
                "Batas: 1-300 detik."
            ),
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )
        return

    if data.startswith("special:delay:set:"):
        parts = data.split(":")
        try:
            low = int(parts[3])
            high = int(parts[4])
        except (IndexError, ValueError):
            await safe_query_answer(query, "Waktu tidak valid.", show_alert=True)
            return
        save_special_open_delay(label, low, high)
        await safe_query_answer(query, f"Waktu tunggu {low}-{high}s")
        await reply_clean(query, 
            "⏱ <b>Waktu Tunggu Diubah</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nWaktu tunggu: {low}-{high}s"),
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )
        return

    if data == "owner:users":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        _pending_restore_upload.discard(int(user_id))
        await safe_query_answer(query, "Users")
        await query.edit_message_text(format_owner_dashboard(), reply_markup=owner_users_keyboard(), parse_mode="HTML")
        return

    if data.startswith("owner:section:"):
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        section = data.split(":", 2)[2]
        if section == "users":
            await safe_query_answer(query, "Users")
            await query.edit_message_text(
                format_owner_users_section(),
                reply_markup=owner_users_section_keyboard(),
                parse_mode="HTML",
            )
            return
        if section == "ops":
            await safe_query_answer(query, "Operasi")
            await query.edit_message_text(
                "⚙️ <b>Operasi</b>\n\n" + expandable_blockquote("Kontrol massal loop akun dan restart bot."),
                reply_markup=owner_ops_section_keyboard(),
                parse_mode="HTML",
            )
            return
        if section == "maintenance":
            await safe_query_answer(query, "Maintenance")
            await query.edit_message_text(
                format_owner_maintenance_text(),
                reply_markup=owner_maintenance_section_keyboard(),
                parse_mode="HTML",
            )
            return
        if section == "admin":
            await safe_query_answer(query, "Admin")
            await query.edit_message_text(
                "👤 <b>Admin</b>\n\n" + expandable_blockquote("Kelola admin/premium bot."),
                reply_markup=owner_admin_section_keyboard(),
                parse_mode="HTML",
            )
            return

    if data == "owner:maintenance:toggle":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        enabled = not maintenance_enabled()
        if enabled:
            resume_labels = await enable_maintenance_runtime(user_id=user_id, source="manual")
            clear_pending_input(user_id)
            await log_event(
                "MAINTENANCE",
                "main",
                f"Maintenance ON oleh {user_id}. Loop dihentikan sementara.\nResume nanti: {', '.join(resume_labels) or '-'}",
            )
            await safe_query_answer(query, "Maintenance ON")
        else:
            started, failed = await disable_maintenance_runtime(user_id=user_id, source="manual")
            await log_event(
                "MAINTENANCE",
                "main",
                f"Maintenance OFF oleh {user_id}.\nResume: {', '.join(started) or '-'}\nGagal: {', '.join(failed) or '-'}",
            )
            answer = f"Maintenance OFF, resume {len(started)} akun"
            if failed:
                answer += f", gagal {len(failed)}"
            await safe_query_answer(query, answer[:200])
        await query.edit_message_text(
            format_owner_maintenance_text(),
            reply_markup=owner_maintenance_section_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "owner:maintenance:schedule_set":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        set_pending_input(user_id, "maintenance_schedule_set")
        await safe_query_answer(query, "Set jadwal")
        await reply_clean(
            query,
            "⏰ <b>Jadwal Maintenance</b>\n\n" + expandable_blockquote(
                "Kirim rentang jam WIB.\n"
                "Contoh: 18:00-20:00 atau 18 20.\n\n"
                "Saat masuk jam mulai, maintenance ON otomatis. Saat lewat jam selesai, maintenance OFF otomatis dan akun yang sebelumnya jalan akan dilanjutkan."
            ),
            reply_markup=back_keyboard("owner:section:maintenance"),
            parse_mode="HTML",
        )
        return

    if data == "owner:maintenance:schedule_clear":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        save_maintenance_schedule(False, user_id=user_id)
        await safe_query_answer(query, "Jadwal dihapus")
        await query.edit_message_text(
            format_owner_maintenance_text(),
            reply_markup=owner_maintenance_section_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "owner:users:summary":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Ringkasan")
        await reply_clean(query, 
            format_owner_account_summary(),
            reply_markup=compact_inline_markup([
                [styled_button("🔄 Refresh", "owner:users:summary", "primary")],
                [styled_button("⬅ Users", "owner:section:users", "primary")],
            ]),
            parse_mode="HTML",
        )
        return

    if data in {"owner:users:list", "owner:users:running", "owner:users:not_login"}:
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        kind = "running" if data.endswith(":running") else "not_login" if data.endswith(":not_login") else "all"
        await safe_query_answer(query, "Users")
        await reply_clean(query, format_owner_user_list(kind), reply_markup=back_keyboard("owner:users"), parse_mode="HTML")
        return

    if data == "owner:all:start":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        if maintenance_enabled():
            await safe_query_answer(query, "Maintenance masih ON.", show_alert=True)
            await reply_clean(query, format_owner_maintenance_text(), reply_markup=owner_maintenance_section_keyboard(), parse_mode="HTML")
            return
        await safe_query_answer(query, "Start semua...")
        progress_msg = await reply_clean(query, 
            "▶ <b>Start Semua Akun</b>\n\n" + blockquote("Memulai semua akun yang sudah login..."),
            parse_mode="HTML",
        )
        _shutdown_event.clear()
        started = []
        already = []
        failed = []
        for target_label in configured_account_labels(enabled_only=True):
            if _account_running.get(target_label):
                already.append(target_label)
                continue
            client = await start_account_client(target_label)
            if client:
                await start_account_loop(target_label, client)
                started.append(target_label)
                audit_log(target_label, "owner_start", "started by owner all", user_id=user_id)
            else:
                failed.append(target_label)
        body = (
            f"Berhasil jalan: {len(started)}\n"
            f"Sudah jalan: {len(already)}\n"
            f"Gagal/Belum login: {len(failed)}\n\n"
            f"Berhasil jalan: {', '.join(account_names_for_labels(started)) or '-'}\n"
            f"Sudah jalan: {', '.join(account_names_for_labels(already)) or '-'}\n"
            f"Gagal: {', '.join(account_names_for_labels(failed)) or '-'}"
        )
        await progress_msg.edit_text(
            "▶ <b>Start Semua Akun</b>\n\n" + expandable_blockquote(body),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "owner:all:stop":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Stop semua...")
        running_before = running_labels()
        await stop_all_accounts(persist_auto_start=True)
        stopped_labels = configured_account_labels(enabled_only=True)
        for target_label in stopped_labels:
            save_account_auto_start(target_label, False)
            audit_log(target_label, "owner_stop", "stopped by owner all", user_id=user_id)
        body = (
            f"Dihentikan: {len(running_before)}\n"
            f"Auto-start dimatikan: {len(stopped_labels)}\n"
            f"Nama: {', '.join(account_names_for_labels(stopped_labels)) or '-'}\n\n"
            "Pending auto open grup khusus akan batal saat guard berikutnya berjalan."
        )
        await reply_clean(query, 
            "■ <b>Stop Semua Akun</b>\n\n" + expandable_blockquote(body),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "owner:bulk_special":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Bulk grup khusus")
        await reply_clean(query, format_bulk_special_text(), reply_markup=owner_bulk_special_keyboard(), parse_mode="HTML")
        return

    if data == "owner:bulk_special:set_group":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Set grup semua")
        set_pending_input(user_id, "bulk_special_group_set")
        await reply_clean(query, 
            "🎯 <b>Bulk Set Grup Khusus</b>\n\n" + expandable_blockquote(
                "Kirim 1 chat ID atau username grup khusus.\n"
                "Setting akan diterapkan ke semua akun enabled yang tidak perlu login ulang.\n\n"
                "Loop tidak akan otomatis distart."
            ),
            reply_markup=back_keyboard("owner:bulk_special"),
            parse_mode="HTML",
        )
        return

    if data == "owner:bulk_special:delay":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Set delay semua")
        set_pending_input(user_id, "bulk_special_delay_set")
        await reply_clean(query, 
            "⏱ <b>Bulk Set Delay Auto Open</b>\n\n" + expandable_blockquote(
                "Kirim rentang detik minimum dan maksimum.\n"
                "Contoh: 9-12 atau 9 12.\n\n"
                "Batas: 1-300 detik."
            ),
            reply_markup=back_keyboard("owner:bulk_special"),
            parse_mode="HTML",
        )
        return

    if data.startswith("owner:bulk_special:"):
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        action = data.split(":", 2)[2]
        labels = bulk_special_target_labels()
        changed = []
        failed = []
        for target_label in labels:
            try:
                if action == "mode":
                    save_runtime_mode("special_group", target_label)
                    audit_log(target_label, "bulk_special_mode", "mode=special_group", user_id=user_id)
                elif action == "auto_on":
                    save_special_auto_open(target_label, True)
                    audit_log(target_label, "bulk_special_auto_open", "enabled=True", user_id=user_id)
                elif action == "auto_off":
                    save_special_auto_open(target_label, False)
                    audit_log(target_label, "bulk_special_auto_open", "enabled=False", user_id=user_id)
                elif action == "boost_on":
                    save_special_auto_boost(target_label, True)
                    audit_log(target_label, "bulk_special_boost", "enabled=True", user_id=user_id)
                elif action == "boost_off":
                    save_special_auto_boost(target_label, False)
                    audit_log(target_label, "bulk_special_boost", "enabled=False", user_id=user_id)
                else:
                    await safe_query_answer(query, "Aksi bulk tidak valid.", show_alert=True)
                    return
                changed.append(target_label)
            except Exception as e:
                failed.append(f"{target_label} ({e})")
        titles = {
            "mode": "Mode Grup Khusus Semua",
            "auto_on": "Auto Open ON Semua",
            "auto_off": "Auto Open OFF Semua",
            "boost_on": "Boost ON Semua",
            "boost_off": "Boost OFF Semua",
        }
        await safe_query_answer(query, "Bulk selesai")
        await reply_clean(query, 
            format_bulk_result_text(titles.get(action, "Bulk Grup Khusus"), changed, failed=failed),
            reply_markup=back_keyboard("owner:bulk_special"),
            parse_mode="HTML",
        )
        return

    if data in {"owner:audit", "owner:audit:all"}:
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        issues_only = data != "owner:audit:all"
        await safe_query_answer(query, "Issue Log" if issues_only else "Audit")
        keyboard = compact_inline_markup([
            [styled_button("📋 Semua Audit", "owner:audit:all", "primary")] if issues_only else [styled_button("🧾 Issue Log", "owner:audit", "primary")],
            [styled_button("⬅ Back", "owner:users", "primary")],
        ])
        await reply_clean(query, format_audit_text(issues_only=issues_only), reply_markup=keyboard, parse_mode="HTML")
        return

    if data == "owner:health":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Health")
        await reply_clean(query, format_health_dashboard(), reply_markup=back_keyboard("owner:users"), parse_mode="HTML")
        return

    if data == "owner:backup":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        _pending_restore_upload.discard(int(user_id))
        await safe_query_answer(query, "Backup")
        await query.edit_message_text(format_backup_menu_text(), reply_markup=backup_menu_keyboard(), parse_mode="HTML")
        return

    if data == "owner:backup:create":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Membuat backup...")
        progress_msg = await reply_clean(query, 
            "💾 <b>Backup</b>\n\n" + blockquote("Membuat backup config..."),
            parse_mode="HTML",
        )
        try:
            payload, summary = create_backup_payload()
            path = write_backup_file(payload)
            await progress_msg.edit_text(
                "✅ <b>Backup</b>\n\n" + blockquote("Backup dibuat. Mengirim file ke owner..."),
                parse_mode="HTML",
            )
            await send_backup_file(user_id, path, summary, context)
            await progress_msg.edit_text(
                "✅ <b>Backup</b>\n\n" + blockquote("Backup selesai. File JSON sudah dikirim."),
                reply_markup=back_keyboard("owner:backup"),
                parse_mode="HTML",
            )
        except Exception as e:
            Log.p("ERROR", f"Backup gagal: {e}")
            audit_log("main", "backup_failed", str(e), user_id=user_id)
            await progress_msg.edit_text(
                "❌ <b>Backup</b>\n\n" + expandable_blockquote(f"Backup gagal:\n{e}"),
                reply_markup=back_keyboard("owner:backup"),
                parse_mode="HTML",
            )
        return

    if data == "owner:backup:restore":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        _pending_restore_upload.add(int(user_id))
        await safe_query_answer(query, "Kirim file backup")
        await reply_clean(query, 
            "♻ <b>Restore Config</b>\n\n" + expandable_blockquote(
                "Kirim file backup JSON dari menu Backup.\n\n"
                "Restore tidak mengembalikan login Telegram. Akun hasil restore perlu login Telegram lagi."
            ),
            reply_markup=back_keyboard("owner:backup"),
            parse_mode="HTML",
        )
        return

    if data == "owner:broadcast":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        await safe_query_answer(query, "Broadcast")
        set_pending_input(user_id, "broadcast")
        await reply_clean(query, 
            "📣 <b>Broadcast</b>\n\n" + expandable_blockquote(
                "Kirim pesan broadcast persis seperti yang mau dikirim.\n"
                "HTML didukung, termasuk <blockquote expandable>.\n"
                "Forward pesan juga didukung jika ingin penerima melihat label diteruskan.\n\n"
                "Bot akan menampilkan preview sebelum broadcast dikirim."
            ),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "owner:daily:menu":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        clear_pending_input(user_id)
        config = load_daily_broadcast_config()
        payload_status = "✅ Sudah di-set" if config.get("payload") else "❌ Belum ada"
        await reply_clean(query, 
            "⏰ <b>Pengaturan Daily Broadcast</b>\n\n"
            f"Pesan akan dikirim otomatis setiap hari jam <b>{config.get('time', '20:00')} WIB</b>.\n\n"
            f"Status Pesan: {payload_status}\n\n"
            "Gunakan tombol di bawah untuk mengatur pesan dan waktu.",
            reply_markup=daily_broadcast_keyboard(),
            parse_mode="HTML"
        )
        return
        
    if data == "owner:daily:toggle_status":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        config = load_daily_broadcast_config()
        if not config.get("payload"):
            return await safe_query_answer(query, "Set pesan dulu!", show_alert=True)
        config["enabled"] = not config.get("enabled", False)
        save_daily_broadcast_config(config)
        await refresh_daily_broadcast_scheduler()
        
        await query.edit_message_reply_markup(reply_markup=daily_broadcast_keyboard())
        return

    if data == "owner:daily:toggle_target":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        config = load_daily_broadcast_config()
        config["target"] = "public" if config.get("target", "premium") == "premium" else "premium"
        save_daily_broadcast_config(config)
        await query.edit_message_reply_markup(reply_markup=daily_broadcast_keyboard())
        return

    if data == "owner:daily:set_payload":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        _pending_owner_inputs[user_id] = "daily_broadcast_payload"
        await safe_query_answer(query, "Menunggu input...")
        await reply_clean(query, 
            "📝 <b>Set Pesan Daily Broadcast</b>\n\n"
            "Kirim atau forward pesan (bisa berupa gambar, video, stiker, teks dengan format HTML) ke bot sekarang juga.\n\n"
            "Pesan ini yang akan dikirim otomatis setiap hari.",
            reply_markup=back_keyboard("owner:daily:menu"),
            parse_mode="HTML"
        )
        return

    if data == "owner:daily:set_time":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        _pending_owner_inputs[user_id] = "daily_broadcast_time"
        await safe_query_answer(query, "Menunggu input...")
        await reply_clean(query, 
            "⏰ <b>Set Waktu Daily Broadcast</b>\n\n"
            "Kirim jam dalam format <b>HH:MM</b>.\n"
            "Contoh: <b>20:00</b> untuk jam 8 malam WIB.",
            reply_markup=back_keyboard("owner:daily:menu"),
            parse_mode="HTML"
        )
        return

    if data == "owner:daily:preview":
        if not can_manage_admins(user_id):
            return await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
        config = load_daily_broadcast_config()
        payload = config.get("payload")
        if not payload:
            return await safe_query_answer(query, "Belum ada pesan yang di-set.", show_alert=True)
            
        await safe_query_answer(query, "Mengirim preview...")
        try:
            if payload.get("type") == "forward":
                await context.bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            elif payload.get("type") == "copy":
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            else:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=payload.get("text", ""),
                        parse_mode="HTML",
                        message_effect_id=DAILY_BROADCAST_MESSAGE_EFFECT_ID,
                    )
                except BadRequest as effect_error:
                    if message_effect_error(effect_error):
                        Log.p("WARN", "Daily preview effect ditolak Telegram, retry tanpa effect")
                        await context.bot.send_message(chat_id=user_id, text=payload.get("text", ""), parse_mode="HTML")
                    else:
                        raise
        except Exception as e:
            await query.message.reply_text(f"Gagal mengirim preview: {e}")
        return

    if data == "owner:broadcast:cancel":
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        _pending_broadcast.pop(user_id, None)
        clear_pending_input(user_id)
        await safe_query_answer(query, "Dibatalkan")
        await reply_clean(query, 
            "📣 <b>Broadcast</b>\n\n" + blockquote("Broadcast dibatalkan."),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data.startswith("owner:broadcast:send"):
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        parts = data.split(":")
        target_kind = parts[3] if len(parts) > 3 else "premium"
        payload = _pending_broadcast.pop(user_id, None)
        if not payload:
            await safe_query_answer(query, "Tidak ada broadcast pending.", show_alert=True)
            return
        await safe_query_answer(query, "Mengirim...")
        targets = broadcast_user_ids(target_kind)
        sent = 0
        failed = 0
        for target_id in targets:
            try:
                if payload.get("type") == "forward":
                    sent_msg = await context.bot.forward_message(
                        chat_id=target_id,
                        from_chat_id=payload["from_chat_id"],
                        message_id=payload["message_id"],
                    )
                elif payload.get("type") == "copy":
                    sent_msg = await context.bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=payload["from_chat_id"],
                        message_id=payload["message_id"],
                    )
                else:
                    sent_msg = await context.bot.send_message(chat_id=target_id, text=payload.get("text", ""), parse_mode="HTML")
                record_broadcast_message(target_id, sent_msg.message_id, payload, target_kind, user_id)
                sent += 1
                if target_kind == "public":
                    mark_broadcast_user_blocked(target_id, False)
                await asyncio.sleep(0.08)
            except Exception as e:
                failed += 1
                if target_kind == "public":
                    mark_broadcast_user_blocked(target_id, True)
                Log.p("WARN", f"Broadcast gagal ke {target_id}: {e}")
        audit_log("main", "broadcast", f"target={target_kind}, sent={sent}, failed={failed}", user_id=user_id)
        await reply_clean(query, 
            "📣 <b>Broadcast selesai</b>\n\n" + expandable_blockquote(
                f"Tujuan: {'Public' if target_kind == 'public' else 'Premium'}\n"
                f"Target: {len(targets)}\n"
                f"Terkirim: {sent}\n"
                f"Gagal: {failed}"
            ),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data.startswith("account:action:"):
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        parts = data.split(":", 4)
        if len(parts) < 5:
            await safe_query_answer(query, "Data akun tidak valid.", show_alert=True)
            return
        action = parts[2]
        try:
            page = int(parts[3])
        except ValueError:
            page = 0
        target_label = parts[4]
        if not can_access_account(user_id, target_label):
            await safe_query_answer(query, "Akun tidak bisa diakses.", show_alert=True)
            return

        if action == "start":
            if maintenance_blocks_account(target_label):
                await safe_query_answer(query, "Maintenance masih ON.", show_alert=True)
                text = "🛠 <b>Maintenance</b>\n\n" + expandable_blockquote("Start akun diblokir sampai maintenance dimatikan.")
                await reply_clean(query, text, reply_markup=account_detail_keyboard(target_label, page), parse_mode="HTML")
                return
            client = await start_account_client(target_label)
            if client:
                await start_account_loop(target_label, client)
                audit_log(target_label, "owner_start", "started by owner", user_id=user_id)
                await safe_query_answer(query, "Jalan")
                text = "▶ <b>Start Akun</b>\n\n" + expandable_blockquote(f"Nama: {account_name_for_label(target_label)}\nStatus: jalan")
            else:
                audit_log(target_label, "owner_start_failed", "client failed", user_id=user_id)
                await safe_query_answer(query, "Gagal start", show_alert=True)
                text = "❌ <b>Start Akun</b>\n\n" + expandable_blockquote(f"Nama: {account_name_for_label(target_label)}\nStatus: gagal jalan. Cek login Telegram dulu.")
        elif action == "stop":
            await stop_account_loop_runtime(target_label, persist_auto_start=True)
            audit_log(target_label, "owner_stop", "stopped by owner", user_id=user_id)
            await safe_query_answer(query, "Berhenti")
            text = "■ <b>Stop Akun</b>\n\n" + expandable_blockquote(f"Nama: {account_name_for_label(target_label)}\nStatus: berhenti")
        elif action == "status":
            await safe_query_answer(query, "Status")
            text = format_monitoring_menu(target_label, user_id)
        elif action == "clear_stuck_prompt":
            await safe_query_answer(query, "Konfirmasi")
            await reply_clean(
                query,
                "🧹 <b>Clear Stuck Akun</b>\n\n"
                + expandable_blockquote(
                    f"Nama: {account_name_for_label(target_label, user_id)}\n\n"
                    "Aksi ini membersihkan state runtime akun ini saja: verifikasi manual, pending join, sesi grup/private, waiting confirmation, dan guard klik/event.\n\n"
                    "Kalau akun sebelumnya running dan task loop mati, bot akan mencoba resume otomatis.\n"
                    "Tidak mengubah setting akun."
                ),
                reply_markup=clear_stuck_confirm_keyboard(target_label, page),
                parse_mode="HTML",
            )
            return
        elif action == "clear_stuck_confirm":
            await safe_query_answer(query, "Clear stuck...")
            ok, body = await clear_stuck_account_runtime(target_label, user_id=user_id)
            title = "✅ <b>Clear Stuck Selesai</b>" if ok else "⚠️ <b>Clear Stuck Dibatalkan</b>"
            await reply_clean(
                query,
                f"{title}\n\n" + expandable_blockquote(body),
                reply_markup=account_detail_keyboard(target_label, page),
                parse_mode="HTML",
            )
            return
        else:
            await safe_query_answer(query, "Aksi tidak valid.", show_alert=True)
            return

        await reply_clean(query, 
            text,
            reply_markup=accounts_back_keyboard(page),
            parse_mode="HTML",
        )
        return

    if data.startswith(("owner:user:start:", "owner:user:stop:", "owner:user:status:")):
        if not can_manage_admins(user_id):
            await safe_query_answer(query, "Hanya owner utama.", show_alert=True)
            return
        action, target_label = data.split(":", 3)[2], data.split(":", 3)[3]
        if not can_access_account(user_id, target_label):
            await safe_query_answer(query, "Akun tidak bisa diakses.", show_alert=True)
            return
        if action == "start":
            if maintenance_blocks_account(target_label):
                await safe_query_answer(query, "Maintenance masih ON.", show_alert=True)
                await reply_clean(query, format_owner_maintenance_text(), reply_markup=owner_maintenance_section_keyboard(), parse_mode="HTML")
                return
            client = await start_account_client(target_label)
            if client:
                await start_account_loop(target_label, client)
                audit_log(target_label, "owner_start", "started by owner", user_id=user_id)
                await safe_query_answer(query, "Jalan")
            else:
                audit_log(target_label, "owner_start_failed", "client failed", user_id=user_id)
                await safe_query_answer(query, "Gagal start", show_alert=True)
        elif action == "stop":
            await stop_account_loop_runtime(target_label, persist_auto_start=True)
            audit_log(target_label, "owner_stop", "stopped by owner", user_id=user_id)
            await safe_query_answer(query, "Berhenti")
        else:
            await safe_query_answer(query, "Status")
        await reply_clean(query, 
            format_monitoring_menu(target_label, user_id),
            reply_markup=back_keyboard("owner:users"),
            parse_mode="HTML",
        )
        return

    if data == "fish:inv" or data.startswith("fish:inv:"):
        if data.startswith("fish:inv:"):
            label = callback_label_or_selected(data, "fish:inv:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        await safe_query_answer(query, "Membaca inventory...")
        progress_msg = await reply_clean(query, 
            "🟥 <b>Inventory</b>\n\n" + blockquote("Membaca inventory, harap tunggu..."),
            reply_markup=back_keyboard(f"menu:inventory:{label}"),
            parse_mode="HTML",
        )
        fish_client = await start_account_client(label)
        if not fish_client:
            await progress_msg.edit_text(
                "❌ <b>Inventory</b>\n\n" + blockquote("Userbot akun ini belum siap/login. Tidak memakai akun main."),
                reply_markup=back_keyboard(f"menu:inventory:{label}"),
                parse_mode="HTML",
            )
            return
        raw, slots, slots_total = await read_all_inventory(fish_app=fish_client, label=label)
        if not raw:
            await progress_msg.edit_text(
                "❌ <b>Inventory</b>\n\n" + blockquote("Gagal baca inventory."),
                reply_markup=back_keyboard(f"menu:inventory:{label}"),
                parse_mode="HTML",
            )
            return
        if is_inventory_empty_text(raw):
            await progress_msg.edit_text(
                "🟥 <b>Inventory</b>\n\n" + blockquote("Inventory kosong."),
                reply_markup=back_keyboard(f"menu:inventory:{label}"),
                parse_mode="HTML",
            )
            return
        token = _current_account_label.set(label)
        try:
            save_list, parsed_items = local_filter_inventory(raw, label=label)
            if parsed_items == 0:
                await progress_msg.edit_text(
                    "❌ <b>Inventory</b>\n\n" + blockquote("Parser lokal gagal baca inventory."),
                    reply_markup=back_keyboard(f"menu:inventory:{label}"),
                    parse_mode="HTML",
                )
                return
        finally:
            _current_account_label.reset(token)
        await progress_msg.edit_text(
            "📊 <b>Inventory</b>\n\n" + expandable_blockquote(
                f"Slot terisi: {slots}/{slots_total}\n\n"
                f"Yang akan disimpan: {save_list if save_list else 'tidak ada'}"
            ),
            reply_markup=back_keyboard(f"menu:inventory:{label}"),
            parse_mode="HTML",
        )
        return

    if data == "fish:gallery" or data.startswith("fish:gallery:"):
        if data.startswith("fish:gallery:"):
            label = callback_label_or_selected(data, "fish:gallery:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        await safe_query_answer(query, "History Fav")
        await reply_clean(query, 
            format_rare_gallery_text(label),
            reply_markup=back_keyboard(f"menu:inventory:{label}"),
            parse_mode="HTML",
        )
        return

    if data == "fish:poseidon_toggle" or data.startswith("fish:poseidon_toggle:"):
        if data.startswith("fish:poseidon_toggle:"):
            label = callback_label_or_selected(data, "fish:poseidon_toggle:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        enabled = not poseidon_favorite_enabled(label)
        save_poseidon_favorite_enabled(label, enabled)
        await safe_query_answer(query, "Trisula Poseidon akan difavorite" if enabled else "Trisula Poseidon akan dijual")
        await query.edit_message_text(format_inventory_menu(label), reply_markup=inventory_menu_keyboard(label), parse_mode="HTML")
        return

    if data == "fish:clean_inventory" or data.startswith("fish:clean_inventory:"):
        if data.startswith("fish:clean_inventory:"):
            label = callback_label_or_selected(data, "fish:clean_inventory:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        await safe_query_answer(query, "Konfirmasi")
        await reply_clean(query,
            "⚠️ <b>Konfirmasi Bersihkan Inventory</b>\n\n"
            + expandable_blockquote(
                f"Nama: {account_name_for_label(label, user_id)}\n\n"
                "Pastikan anda tidak sedang aktif memancing di grup atau pun di private untuk menghindari hal hal yang tidak di inginkan."
            ),
            reply_markup=clean_inventory_confirm_keyboard(label),
            parse_mode="HTML",
        )
        return

    if data == "fish:clean_inventory_confirm" or data.startswith("fish:clean_inventory_confirm:"):
        if data.startswith("fish:clean_inventory_confirm:"):
            label = callback_label_or_selected(data, "fish:clean_inventory_confirm:", label)
            if not can_access_account(user_id, label):
                await safe_query_answer(query, "Tidak punya akses akun ini.", show_alert=True)
                return
        await safe_query_answer(query, "Bersihkan inventory")
        progress_msg = await reply_clean(query, 
            "🧹 <b>Bersihkan Inventory</b>\n\n" + blockquote(f"Nama: {account_name_for_label(label, user_id)}\nMemulai bersihkan inventory..."),
            reply_markup=back_keyboard(f"menu:inventory:{label}"),
            parse_mode="HTML",
        )
        fish_client = await start_account_client(label)
        if not fish_client:
            await progress_msg.edit_text(
                "❌ <b>Bersihkan Inventory</b>\n\n" + blockquote("Userbot akun ini belum siap/login. Tidak memakai akun main."),
                reply_markup=back_keyboard(f"menu:inventory:{label}"),
                parse_mode="HTML",
            )
            return
        set_command_mode(label, True)
        try:
            await sell_flow(fish_app=fish_client, label=label)
        finally:
            set_command_mode(label, False)
        await progress_msg.edit_text(
            "✅ <b>Bersihkan Inventory</b>\n\n" + blockquote("Bersihkan inventory selesai."),
            reply_markup=back_keyboard(f"menu:inventory:{label}"),
            parse_mode="HTML",
        )
        return

    if data in {"rules:keep_menu", "rules:sell_menu"}:
        kind = "keep" if data == "rules:keep_menu" else "sell"
        await safe_query_answer(query, "List rules")
        await reply_clean(query, format_rule_list_text(label, kind), reply_markup=rules_list_keyboard(kind), parse_mode="HTML")
        return

    if data == "rules:list_all":
        await safe_query_answer(query, "List rules")
        await reply_clean(query, format_all_rules_text(label), reply_markup=rules_back_keyboard(), parse_mode="HTML")
        return

    input_modes = {
        "rules:keep_add": ("keep_add", "Kirim nama ikan yang mau selalu disimpan.\nBisa banyak, pisahkan dengan baris baru atau koma."),
        "rules:keep_del": ("keep_del", "Kirim nama ikan yang mau dihapus dari keep list.\nBisa banyak, pisahkan dengan baris baru atau koma."),
        "rules:sell_add": ("sell_add", "Kirim nama ikan yang mau selalu dijual.\nBisa banyak, pisahkan dengan baris baru atau koma."),
        "rules:sell_del": ("sell_del", "Kirim nama ikan yang mau dihapus dari sell list.\nBisa banyak, pisahkan dengan baris baru atau koma."),
    }
    if data in input_modes:
        await safe_query_answer(query, "Mode input aktif")
        input_mode, prompt = input_modes[data]
        set_pending_input(user_id, f"{input_mode}:{label}")
        kind = "keep" if "keep" in input_mode else "sell"
        await reply_clean(query, 
            "✍️ <b>Input Rules</b>\n\n" + expandable_blockquote(f"{prompt}\n\nKirim sebagai pesan biasa. Tekan Back untuk batal."),
            reply_markup=back_keyboard(f"rules:{kind}_menu"),
            parse_mode="HTML",
        )
        return


