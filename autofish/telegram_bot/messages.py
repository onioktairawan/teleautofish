from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def handle_reply_keyboard_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    text = (update.message.text or "").strip().casefold()
    user_id = int(update.effective_user.id)
    label = selected_account_label(user_id)

    if text == "menu":
        accounts = load_accounts_for_user(user_id)
        if len(accounts) > 1:
            await update.message.reply_text(format_accounts_text(user_id), reply_markup=accounts_menu_keyboard(user_id), parse_mode="HTML")
        elif not accounts and user_id != OWNER_ID:
            await update.message.reply_text(format_userbot_text(user_id), reply_markup=userbot_menu_keyboard(label))
        else:
            await update.message.reply_text(format_main_menu(label, user_id), reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return True

    if text == "mancing":
        if not can_access_account(user_id, label):
            await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        else:
            await update.message.reply_text(format_fishing_menu(label), reply_markup=fishing_menu_keyboard(), parse_mode="HTML")
        return True

    if text == "inventory":
        if not can_access_account(user_id, label):
            await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        else:
            await update.message.reply_text(format_inventory_menu(label), reply_markup=inventory_menu_keyboard(label), parse_mode="HTML")
        return True

    if text == "status":
        if not can_access_account(user_id, label):
            await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        else:
            await update.message.reply_text(format_monitoring_menu(label, user_id), reply_markup=monitoring_menu_keyboard(user_id), parse_mode="HTML")
        return True

    if text == "settings":
        await update.message.reply_text(format_settings_menu(label, user_id), reply_markup=settings_menu_keyboard(user_id), parse_mode="HTML")
        return True

    return False


async def handle_broadcast_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    if not message or not message.reply_to_message or not update.effective_user:
        return False
    user_id = safe_user_id(update.effective_user.id)
    if not user_id or user_id == OWNER_ID:
        return False
    original_id = getattr(message.reply_to_message, "message_id", 0)
    broadcast_doc = find_broadcast_message(user_id, original_id)
    if not broadcast_doc:
        return False

    register_broadcast_user(update.effective_user, source="broadcast_reply")
    user = update.effective_user
    name = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part) or str(user_id)
    username = f"@{user.username}" if getattr(user, "username", None) else "-"
    reply_text = (message.text or message.caption or "").strip() or "(non-teks)"
    body = (
        f"Dari: {name}\n"
        f"Username: {username}\n"
        f"User ID: {user_id}\n"
        f"Target broadcast: {broadcast_doc.get('target_kind', '-')}\n\n"
        f"Broadcast:\n{broadcast_doc.get('preview', '-')}\n\n"
        f"Balasan:\n{reply_text}"
    )
    try:
        sent_owner_msg = await context.bot.send_message(
            chat_id=OWNER_ID,
            text="📩 <b>Balasan Broadcast</b>\n\n" + expandable_blockquote(body),
            parse_mode="HTML",
        )
        _owner_reply_targets[int(sent_owner_msg.message_id)] = {
            "user_id": user_id,
            "source": "broadcast_reply",
            "name": name,
        }
        await log_event("BROADCAST_REPLY", "main", f"Dari: {user_id}\nBalasan: {reply_text[:500]}")
    except Exception as e:
        Log.p("WARN", f"Gagal kirim balasan broadcast ke owner: {e}")
        await message.reply_text("❌ Balasan belum berhasil dikirim. Coba lagi nanti.")
        return True
    await message.reply_text("✅ Balasan sudah dikirim ke owner.")
    return True


async def tg_owner_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    effective_user = update.effective_user
    if not message or not effective_user:
        return

    user_id = effective_user.id
    if user_id in _pending_restore_upload and getattr(message, "document", None):
        await tg_restore_document_handler(update, context)
        return
    if await handle_user_report_text(update, context):
        return
    if await handle_broadcast_reply(update, context):
        return
    if maintenance_enabled() and not can_manage_admins(user_id):
        await update.message.reply_text(maintenance_message_text(), reply_markup=maintenance_keyboard(), parse_mode="HTML")
        return
    if not is_admin_user(user_id):
        return
    if await handle_owner_direct_reply(update, context):
        return
    if await handle_userbot_login_text(update, context):
        return
    pending_input = get_pending_input(user_id)
    if not pending_input:
        text = (update.message.text or "").strip()
        parts = re.split(r"\s+", text)
        if parts and parts[0].casefold() in {"addprem", "rmprem"}:
            await premium_command(update, context, parts[0].casefold(), parts[1:])
            return
        if await handle_reply_keyboard_shortcut(update, context):
            return
        return

    text = (update.message.text or "").strip()
    mode = pending_input
    clear_pending_input(user_id)
    pending_label = selected_account_label(user_id)

    if mode == "broadcast":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama yang bisa broadcast.", reply_markup=back_keyboard("menu:main"))
        is_forwarded = bool(
            getattr(update.message, "forward_origin", None)
            or getattr(update.message, "forward_from", None)
            or getattr(update.message, "forward_from_chat", None)
        )
        public_count = len(broadcast_user_ids("public"))
        premium_count = len(broadcast_user_ids("premium"))
        if is_forwarded:
            payload = {
                "type": "forward",
                "from_chat_id": update.message.chat_id,
                "message_id": update.message.message_id,
                "kind": broadcast_message_kind(update.message),
            }
            _pending_broadcast[user_id] = payload
            await update.message.reply_text(
                "📣 <b>Preview Broadcast Forward</b>\n\n"
                + expandable_blockquote(f"Target public: {public_count}\nTarget premium: {premium_count}\n\nPesan di bawah akan diteruskan ke target."),
                reply_markup=broadcast_preview_keyboard(),
                parse_mode="HTML",
            )
            try:
                await context.bot.forward_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            except Exception as e:
                _pending_broadcast.pop(user_id, None)
                return await update.message.reply_text(
                    "⚠️ Preview forward gagal.\n\n" + expandable_blockquote(str(e)),
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
            )
            return
        if not text:
            payload = {
                "type": "copy",
                "from_chat_id": update.message.chat_id,
                "message_id": update.message.message_id,
                "kind": broadcast_message_kind(update.message),
                "caption": (update.message.caption or "").strip(),
            }
            _pending_broadcast[user_id] = payload
            await update.message.reply_text(
                "📣 <b>Preview Broadcast Media</b>\n\n"
                + expandable_blockquote(
                    f"Jenis: {payload['kind']}\n"
                    f"Target public: {public_count}\n"
                    f"Target premium: {premium_count}\n\n"
                    "Pesan di bawah akan disalin ke target."
                ),
                reply_markup=broadcast_preview_keyboard(),
                parse_mode="HTML",
            )
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=payload["from_chat_id"],
                    message_id=payload["message_id"],
                )
            except Exception as e:
                _pending_broadcast.pop(user_id, None)
                return await update.message.reply_text(
                    "⚠️ Preview media gagal.\n\n" + expandable_blockquote(str(e)),
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
            return
        _pending_broadcast[user_id] = {"type": "text", "text": text}
        try:
            return await update.message.reply_text(
                "📣 <b>Preview Broadcast</b>\n\n"
                + expandable_blockquote(f"Target public: {public_count}\nTarget premium: {premium_count}")
                + "\n\n"
                + text,
                reply_markup=broadcast_preview_keyboard(),
                parse_mode="HTML",
            )
        except Exception as e:
            _pending_broadcast.pop(user_id, None)
            return await update.message.reply_text(
                "⚠️ HTML broadcast tidak valid.\n\n" + expandable_blockquote(str(e)),
                reply_markup=back_keyboard("owner:users"),
                parse_mode="HTML",
            )


    if mode == "daily_broadcast_time":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama.", reply_markup=back_keyboard("owner:daily:menu"))
        
        match = re.match(r"^([01][0-9]|2[0-3])[:. ]?([0-5][0-9])$", text.strip())
        if not match:
            return await update.message.reply_text("⚠️ Format jam salah. Contoh: 20:00", reply_markup=back_keyboard("owner:daily:menu"))
            
        h, m = match.groups()
        time_str = f"{h}:{m}"
        
        config = load_daily_broadcast_config()
        config["time"] = time_str
        save_daily_broadcast_config(config)
        clear_pending_input(user_id)
        await refresh_daily_broadcast_scheduler()
        return await update.message.reply_text(f"✅ Waktu berhasil diubah menjadi jam {time_str} WIB.", reply_markup=back_keyboard("owner:daily:menu"))

    if mode == "daily_broadcast_payload":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama.", reply_markup=back_keyboard("owner:daily:menu"))
            
        if getattr(update.message, "forward_origin", None) or getattr(update.message, "forward_date", None):
            payload = {
                "type": "forward",
                "from_chat_id": update.message.chat_id,
                "message_id": update.message.message_id,
            }
        elif not text:
            payload = {
                "type": "copy",
                "from_chat_id": update.message.chat_id,
                "message_id": update.message.message_id,
                "kind": broadcast_message_kind(update.message),
                "caption": (update.message.caption or "").strip(),
            }
        else:
            # check html
            try:
                # dummy send to test html (won't actually send since we catch exception if parse mode fails usually, but here we just store it and let preview test it)
                pass
            except Exception:
                pass
            payload = {"type": "text", "text": text}
            
        config = load_daily_broadcast_config()
        config["payload"] = payload
        save_daily_broadcast_config(config)
        clear_pending_input(user_id)
        
        return await update.message.reply_text(
            "✅ Pesan daily broadcast berhasil disimpan! Silakan cek dengan tombol <b>Test Kirim (Preview)</b>.",
            reply_markup=back_keyboard("owner:daily:menu"),
            parse_mode="HTML"
        )

    if mode == "maintenance_schedule_set":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama.", reply_markup=back_keyboard("owner:users"))
        parsed = parse_maintenance_schedule_input(text)
        if not parsed:
            return await update.message.reply_text(
                "⚠️ Format jadwal tidak valid. Contoh: 18:00-20:00 atau 18 20.",
                reply_markup=back_keyboard("owner:section:maintenance"),
            )
        start, end = parsed
        save_maintenance_schedule(True, start=start, end=end, user_id=user_id)
        return await update.message.reply_text(
            "✅ <b>Jadwal Maintenance Diset</b>\n\n"
            + blockquote(f"Jam: {start}-{end} WIB\nStatus: aktif")
            + "\n\n"
            + format_owner_maintenance_text(),
            reply_markup=back_keyboard("owner:section:maintenance"),
            parse_mode="HTML",
        )

    if ":" in mode:
        mode, pending_label = mode.split(":", 1)
        if not can_access_account(user_id, pending_label):
            return await update.message.reply_text("⛔ Tidak punya akses ke akun ini.", reply_markup=back_keyboard("menu:main"))

    if mode == "admin_add":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama yang bisa tambah admin.", reply_markup=back_keyboard("owner:users"))

        raw_ids = re.split(r"[\s,;|]+", text)
        added = []
        invalid = []
        for raw_id in raw_ids:
            if not raw_id:
                continue
            if not re.fullmatch(r"\d+", raw_id):
                invalid.append(raw_id)
                continue
            admin_id = int(raw_id)
            if add_admin_id(admin_id):
                added.append(admin_id)

        admins = "\n".join(f"• {admin_display_name(admin_id)}" for admin_id in sorted(load_admin_ids()))
        added_text = f"{len(added)} admin baru" if added else "tidak ada yang baru"
        invalid_text = f"\nInvalid: {', '.join(invalid)}" if invalid else ""
        return await update.message.reply_text(
            f"✅ Admin ditambahkan: {added_text}{invalid_text}\n\n👥 Admin aktif:\n{admins}",
            reply_markup=back_keyboard("owner:users"),
        )

    if mode == "bulk_special_group_set":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama.", reply_markup=back_keyboard("owner:users"))
        chats = split_chat_targets(text)
        if not chats:
            return await update.message.reply_text("⚠️ Grup khusus tidak valid.", reply_markup=back_keyboard("owner:bulk_special"))
        target = chats[0]
        changed = []
        failed = []
        for target_label in bulk_special_target_labels():
            try:
                save_special_group_chat(target, label=target_label)
                audit_log(target_label, "bulk_special_group", f"group={target}", user_id=user_id)
                changed.append(target_label)
            except Exception as e:
                failed.append(f"{target_label} ({e})")
        return await update.message.reply_text(
            format_bulk_result_text(f"Bulk Set Grup Khusus: {target}", changed, failed=failed),
            reply_markup=back_keyboard("owner:bulk_special"),
            parse_mode="HTML",
        )

    if mode == "bulk_special_delay_set":
        if not can_manage_admins(user_id):
            return await update.message.reply_text("⛔ Hanya owner utama.", reply_markup=back_keyboard("owner:users"))
        values = re.findall(r"\d+", text)
        if len(values) < 2:
            return await update.message.reply_text(
                "⚠️ Format waktu tidak valid. Contoh: 9-12 atau 9 12.",
                reply_markup=back_keyboard("owner:bulk_special"),
            )
        low, high = int(values[0]), int(values[1])
        if low < 1 or high < 1 or low > 300 or high > 300:
            return await update.message.reply_text(
                "⚠️ Waktu harus di antara 1 sampai 300 detik.",
                reply_markup=back_keyboard("owner:bulk_special"),
            )
        changed = []
        failed = []
        for target_label in bulk_special_target_labels():
            try:
                save_special_open_delay(target_label, low, high)
                audit_log(target_label, "bulk_special_delay", f"{low}-{high}s", user_id=user_id)
                changed.append(target_label)
            except Exception as e:
                failed.append(f"{target_label} ({e})")
        return await update.message.reply_text(
            format_bulk_result_text(f"Bulk Set Delay: {low}-{high}s", changed, failed=failed),
            reply_markup=back_keyboard("owner:bulk_special"),
            parse_mode="HTML",
        )

    if mode in {"group_add", "group_del"}:
        chats = split_chat_targets(text)
        if not chats:
            return await update.message.reply_text("⚠️ Tidak ada group yang valid.", reply_markup=groups_back_keyboard())

        results = []
        success_count = 0
        for chat in chats:
            ok, msg = add_group_chat(chat, label=pending_label) if mode == "group_add" else remove_group_chat(chat, label=pending_label)
            if ok:
                success_count += 1
            results.append(msg)

        label = "ditambahkan" if mode == "group_add" else "dihapus"
        detail = "\n".join(results[:10])
        if len(results) > 10:
            detail += f"\n... dan {len(results) - 10} item lagi"
        await log_event("GROUPS", pending_label, f"Aksi: {mode}\nBerhasil: {success_count}/{len(chats)}\nOleh: {user_id}")
        return await update.message.reply_text(
            f"✅ {success_count}/{len(chats)} group berhasil {label}.\n\n"
            f"{expandable_blockquote(detail)}\n\n"
            f"{format_groups_text(pending_label)}",
            reply_markup=back_keyboard("menu:groups"),
            parse_mode="HTML",
        )

    if mode == "special_group_set":
        chats = split_chat_targets(text)
        if not chats:
            return await update.message.reply_text("⚠️ Grup khusus tidak valid.", reply_markup=special_group_back_keyboard())

        save_special_group_chat(chats[0], label=pending_label)
        await log_event("SPECIAL_GROUP", pending_label, f"Grup khusus diset: {chats[0]}\nOleh: {user_id}")
        detail = f"Nama: {account_name_for_label(pending_label, user_id)}\nGrup khusus: {chats[0]}"
        return await update.message.reply_text(
            "✅ <b>Grup Khusus Diset</b>\n\n"
            f"{blockquote(detail)}\n\n"
            f"{format_special_group_text(pending_label)}",
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )

    if mode == "private_bot_set":
        normalized = normalize_bot_username(text)
        if not normalized:
            return await update.message.reply_text(
                "⚠️ Username bot tidak valid. Contoh: @fish_it_vip5_bot",
                reply_markup=back_keyboard("menu:private"),
            )
        save_private_bot_username(pending_label, normalized)
        await log_event("PRIVATE_BOT", pending_label, f"Bot private diset: {normalized}\nOleh: {user_id}")
        detail = (
            f"Nama: {account_name_for_label(pending_label, user_id)}\n"
            f"Bot private: {normalized}\n"
            "Catatan: hanya dipakai saat mode private."
        )
        return await update.message.reply_text(
            "✅ <b>Bot Private Diset</b>\n\n"
            f"{blockquote(detail)}\n\n"
            f"{format_private_settings_text(pending_label)}",
            reply_markup=back_keyboard("menu:private"),
            parse_mode="HTML",
        )

    if mode == "special_delay_custom":
        values = re.findall(r"\d+", text)
        if len(values) < 2:
            return await update.message.reply_text(
                "⚠️ Format waktu tidak valid. Contoh: 9-12 atau 9 12.",
                reply_markup=special_group_back_keyboard(),
            )
        low, high = int(values[0]), int(values[1])
        if low < 1 or high < 1 or low > 300 or high > 300:
            return await update.message.reply_text(
                "⚠️ Waktu harus di antara 1 sampai 300 detik.",
                reply_markup=special_group_back_keyboard(),
            )
        save_special_open_delay(pending_label, low, high)
        low, high = special_open_delay_range(pending_label)
        detail = f"Nama: {account_name_for_label(pending_label, user_id)}\nWaktu tunggu: {low:.0f}-{high:.0f}s"
        return await update.message.reply_text(
            "✅ <b>Waktu Tunggu Diset</b>\n\n"
            f"{blockquote(detail)}\n\n"
            f"{format_special_group_text(pending_label)}",
            reply_markup=back_keyboard("menu:special_group"),
            parse_mode="HTML",
        )

    names = split_rule_names(text)
    if not names:
        kind = "keep" if "keep" in mode else "sell"
        return await update.message.reply_text("⚠️ Tidak ada nama ikan yang valid.", reply_markup=back_keyboard(f"rules:{kind}_menu"))

    kind = "keep" if "keep" in mode else "sell"
    add = mode.endswith("_add")
    success_count, results = update_fish_rules_batch(kind, names, add, label=pending_label)
    total = len(names)
    label = "ditambah" if add else "dihapus"
    header = f"✅ {success_count}/{total} nama berhasil {label}." if success_count else f"⚠️ Tidak ada nama yang berhasil {label}."
    detail = "\n".join(results[:10])
    if len(results) > 10:
        detail += f"\n... dan {len(results) - 10} item lagi"
    await log_event(
        "RULES",
        pending_label,
        f"List: {kind}\nAksi: {label}\nBerhasil: {success_count}/{total}\nNama: {', '.join(names[:10])}\nOleh: {user_id}",
    )
    await update.message.reply_text(
        f"{html.escape(header)}\n\n{expandable_blockquote(detail)}\n\n{format_rule_list_text(pending_label, kind)}",
        reply_markup=back_keyboard(f"rules:{kind}_menu"),
        parse_mode="HTML",
    )


