from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = int(update.effective_user.id)
        if maintenance_enabled() and not can_manage_admins(user_id):
            await update.message.reply_text(maintenance_message_text(), parse_mode="HTML")
            return
        if not is_admin_user(user_id):
            await update.message.reply_text("⛔ Kamu tidak memiliki akses ke bot ini.")
            return
        await func(update, context)
    return wrapper


async def send_or_edit_menu(update: Update, text: str, keyboard: InlineKeyboardMarkup):
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text=text, reply_markup=keyboard)


async def reply_clean(query, text: str, reply_markup=None, parse_mode: str = "HTML"):
    sent = await query.message.chat.send_message(
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    try:
        await query.message.delete()
    except Exception:
        pass
    return sent


async def restart_current_process(delay: float = 1.0, chat_id: int = None, message_id: int = None, source: str = "bot"):
    Log.p("BOT", "Restart bot diminta dari tombol Telegram")
    _shutdown_event.set()
    payload = {
        "requested_at": now_wib().isoformat(),
        "chat_id": int(chat_id or 0),
        "message_id": int(message_id or 0),
        "source": source,
    }
    try:
        RESTART_FLAG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        Log.p("WARN", f"Gagal tulis restart flag: {e}")
    await asyncio.sleep(delay)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        Log.p("ERROR", f"Restart gagal: {e}")
        try:
            RESTART_FLAG_FILE.unlink()
        except Exception:
            pass
        if _tg_app and _tg_app.bot and chat_id:
            text = "❌ <b>Restart Bot</b>\n\n" + blockquote(f"Restart gagal.\n\n{e}")
            try:
                await _tg_app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
            except Exception:
                if message_id:
                    try:
                        await _tg_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except Exception:
                        pass
                await _tg_app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )


async def complete_pending_restart_notification(success: bool = True, message: str = None):
    if not RESTART_FLAG_FILE.exists():
        Log.p("STARTUP", "Fish Bot online")
        return

    raw = ""
    payload = {}
    try:
        raw = RESTART_FLAG_FILE.read_text(encoding="utf-8").strip()
        payload = json.loads(raw) if raw.startswith("{") else {"requested_at": raw}
    except Exception as e:
        Log.p("WARN", f"Gagal baca restart flag: {e}")
        payload = {}

    chat_id = int(payload.get("chat_id") or 0)
    message_id = int(payload.get("message_id") or 0)
    source = str(payload.get("source") or "bot")
    if success:
        text = "✅ <b>Restart Bot</b>\n\n" + blockquote(message or "Restart berhasil. Kode terbaru aktif.")
    else:
        text = "❌ <b>Restart Bot</b>\n\n" + blockquote(message or "Restart gagal.")

    if _tg_app and _tg_app.bot and chat_id:
        if source == "userbot" and message_id:
            try:
                if _account_clients.get("main") is app:
                    await app.delete_messages(chat_id, message_id)
            except Exception as e:
                Log.p("WARN", f"Gagal hapus pesan proses restart: {e}")
            try:
                await _tg_app.bot.send_message(
                    chat_id=OWNER_ID,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
            except Exception as e:
                Log.p("WARN", f"Gagal kirim hasil restart ke owner: {e}")
            try:
                RESTART_FLAG_FILE.unlink()
            except Exception as e:
                Log.p("WARN", f"Gagal hapus restart flag: {e}")
            Log.p("STARTUP", "Restart flag terdeteksi, kode terbaru aktif")
            return

        try:
            if message_id:
                await _tg_app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
            else:
                await _tg_app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
        except Exception as e:
            Log.p("WARN", f"Gagal edit pesan restart, kirim pesan baru: {e}")
            try:
                if message_id:
                    try:
                        await _tg_app.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except Exception:
                        pass
                await _tg_app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=back_keyboard("owner:users"),
                    parse_mode="HTML",
                )
            except Exception as e2:
                Log.p("WARN", f"Gagal kirim pesan restart berhasil: {e2}")

    try:
        RESTART_FLAG_FILE.unlink()
    except Exception as e:
        Log.p("WARN", f"Gagal hapus restart flag: {e}")
    Log.p("STARTUP", "Restart flag terdeteksi, kode terbaru aktif")


async def request_bot_restart(chat_id: int, send_message_func, user_id: int):
    clear_pending_input(user_id)
    _pending_restore_upload.discard(int(user_id))
    _shutdown_event.set()
    await stop_all_accounts()
    progress_msg = await send_message_func(
        "🔄 <b>Restart Bot</b>\n\n" + blockquote("Restart sedang diproses."),
        parse_mode="HTML",
    )
    asyncio.create_task(
        restart_current_process(
            chat_id=progress_msg.chat.id,
            message_id=progress_msg.message_id,
            source="bot",
        )
    )


