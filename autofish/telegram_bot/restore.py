from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def tg_restore_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.effective_user.id)
    if not can_manage_admins(user_id) or user_id not in _pending_restore_upload:
        return
    document = update.message.document
    if not document:
        return
    filename = document.file_name or "backup.json"
    filename_lower = filename.lower()
    if not filename_lower.endswith((".json", ".zip")):
        await update.message.reply_text(
            "⚠️ File restore harus berformat .json atau .zip.",
            reply_markup=back_keyboard("owner:backup"),
        )
        return

    _pending_restore_upload.discard(user_id)
    progress_msg = await update.message.reply_text(
        "♻ <b>Restore Config</b>\n\n" + blockquote("Mengunduh dan memvalidasi backup..."),
        parse_mode="HTML",
    )
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        suffix = ".zip" if filename_lower.endswith(".zip") else ".json"
        download_path = BACKUP_DIR / f"restore_upload_{user_id}_{now_wib().strftime('%Y%m%d_%H%M%S')}{suffix}"
        tg_file = await document.get_file()
        await tg_file.download_to_drive(custom_path=download_path)
        if filename_lower.endswith(".zip"):
            restored = _restore_full_backup_bundle(download_path)
        else:
            payload = json.loads(download_path.read_text(encoding="utf-8"))
            ok, msg = validate_backup_payload(payload)
            if not ok:
                raise ValueError(msg)
            restored = restore_backup_payload(payload)
        await progress_msg.edit_text(
            "✅ <b>Restore selesai</b>\n\n" + expandable_blockquote(
                f"Files: {restored.get('files', 0)}\n"
                f"Sessions: {restored.get('sessions', 0)}\n"
                "Restart bot setelah restore full bundle supaya .env dan session baru kebaca."
            ),
            reply_markup=back_keyboard("owner:backup"),
            parse_mode="HTML",
        )
    except Exception as e:
        Log.p("ERROR", f"Restore gagal: {e}")
        await send_traceback_log(e, update=update, label=selected_account_label(user_id), user_id=user_id)
        audit_log("main", "restore_failed", str(e), user_id=user_id)
        await progress_msg.edit_text(
            "❌ <b>Restore gagal</b>\n\n" + expandable_blockquote(str(e)),
            reply_markup=back_keyboard("owner:backup"),
            parse_mode="HTML",
        )


