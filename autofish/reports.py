from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def user_report_prompt_text() -> str:
    return (
        "🐞 <b>Lapor Bug / Masalah</b>\n\n"
        + expandable_blockquote(
            "Kirim detail masalah dalam satu pesan.\n"
            "Sertakan nama akun, mode, waktu kejadian, dan error/gejala kalau ada.\n\n"
            "Ketik batal untuk membatalkan."
        )
    )


async def start_user_report_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    user_id = int(update.effective_user.id)
    set_pending_input(user_id, "user_report")
    if query:
        await safe_query_answer(query, "Kirim laporan")
        try:
            await query.edit_message_text(user_report_prompt_text(), reply_markup=back_keyboard("report:cancel"), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat.id, text=user_report_prompt_text(), reply_markup=back_keyboard("report:cancel"), parse_mode="HTML")
        return
    await update.message.reply_text(user_report_prompt_text(), reply_markup=main_reply_keyboard(), parse_mode="HTML")


async def send_user_report(update: Update, context: ContextTypes.DEFAULT_TYPE, report_text: str):
    user = update.effective_user
    user_id = safe_user_id(getattr(user, "id", 0))
    name = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part) or str(user_id)
    username = f"@{user.username}" if getattr(user, "username", None) else "-"
    label = selected_account_label(user_id)
    account_name = account_name_for_label(label, user_id)
    body = (
        f"Dari: {name}\n"
        f"Username: {username}\n"
        f"User ID: {user_id}\n"
        f"Akun terpilih: {account_name} ({label})\n"
        f"Maintenance: {'ON' if maintenance_enabled() else 'OFF'}\n"
        f"Waktu: {now_wib().strftime('%d/%m/%Y %H:%M:%S WIB')}\n\n"
        f"Laporan:\n{report_text[:2500]}"
    )
    message = "🐞 <b>Laporan User</b>\n\n" + expandable_blockquote(body)
    try:
        sent_owner_msg = await context.bot.send_message(chat_id=OWNER_ID, text=message[:4000], parse_mode="HTML")
        _owner_reply_targets[int(sent_owner_msg.message_id)] = {
            "user_id": user_id,
            "source": "user_report",
            "name": name,
        }
    except Exception as e:
        Log.p("WARN", f"Gagal kirim laporan user ke owner: {e}")
    audit_log(label, "user_report", report_text[:500], user_id=user_id)
    await update.message.reply_text(
        "✅ Laporan sudah dikirim ke owner. Terima kasih.",
        reply_markup=main_reply_keyboard() if is_admin_user(user_id) else None,
    )


async def handle_user_report_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.effective_user:
        return False
    user_id = int(update.effective_user.id)
    text = (update.message.text or "").strip()
    pending_input = get_pending_input(user_id)
    if pending_input == "user_report":
        if text.casefold() in {"batal", "cancel", "/cancel"}:
            clear_pending_input(user_id)
            await update.message.reply_text("Laporan dibatalkan.", reply_markup=main_reply_keyboard() if is_admin_user(user_id) else None)
            return True
        if not text:
            await update.message.reply_text(user_report_prompt_text(), parse_mode="HTML")
            return True
        clear_pending_input(user_id)
        register_broadcast_user(update.effective_user, source="report")
        await send_user_report(update, context, text)
        return True

    if text.casefold() in {"lapor", "🐞 lapor", "/lapor"}:
        register_broadcast_user(update.effective_user, source="report_start")
        await start_user_report_flow(update, context)
        return True

    return False


async def handle_owner_direct_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    if not message or not message.reply_to_message or not can_manage_admins(update.effective_user.id):
        return False
    target = _owner_reply_targets.get(int(message.reply_to_message.message_id))
    if not target:
        return False
    target_user_id = safe_user_id(target.get("user_id"))
    if not target_user_id:
        return False
    reply_text = (message.text or message.caption or "").strip()
    if not reply_text:
        await message.reply_text("⚠️ Balasan harus berupa teks.")
        return True
    try:
        sent_msg = await context.bot.send_message(chat_id=target_user_id, text=reply_text)
        record_broadcast_message(
            target_user_id,
            sent_msg.message_id,
            {"type": "text", "text": reply_text, "preview": reply_text.replace("\n", " ")[:300]},
            "owner_reply",
            update.effective_user.id,
        )
        mark_broadcast_user_blocked(target_user_id, False)
        await message.reply_text("✅ Balasan sudah dikirim ke user.")
        audit_log("main", "owner_reply_user", f"to={target_user_id}, source={target.get('source', '-')}", user_id=update.effective_user.id)
    except Exception as e:
        mark_broadcast_user_blocked(target_user_id, True)
        Log.p("WARN", f"Gagal kirim balasan owner ke {target_user_id}: {e}")
        await message.reply_text(f"❌ Gagal kirim balasan ke user: {e}")
    return True


