from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_broadcast_user(update.effective_user, source="start")
    if maintenance_enabled() and not can_manage_admins(user_id):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=maintenance_message_text(),
            reply_markup=maintenance_keyboard(),
            parse_mode="HTML",
        )
        return
    is_premium = is_admin_user(user_id)
    label = selected_account_label(user_id) if is_premium else default_user_account_label(user_id)
    has_userbot = account_doc_exists(label)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=format_welcome_text(user_id, update.effective_user.first_name),
        reply_markup=main_reply_keyboard() if is_premium else welcome_keyboard(is_premium, has_userbot, user_id),
        parse_mode="HTML",
    )
    _reply_keyboard_sent.add(int(user_id))


async def tg_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    user_id = update.effective_user.id
    label = selected_account_label(user_id)
    await update.message.reply_text(format_main_menu(label, user_id), reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")


async def tg_mancing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    label = selected_account_label(update.effective_user.id)
    if not can_access_account(update.effective_user.id, label):
        await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        return
    await update.message.reply_text(format_fishing_menu(label), reply_markup=fishing_menu_keyboard(), parse_mode="HTML")


async def tg_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    label = selected_account_label(update.effective_user.id)
    if not can_access_account(update.effective_user.id, label):
        await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        return
    await update.message.reply_text(format_inventory_menu(label), reply_markup=inventory_menu_keyboard(label), parse_mode="HTML")


async def tg_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    label = selected_account_label(update.effective_user.id)
    if not can_access_account(update.effective_user.id, label):
        await update.message.reply_text("⚠️ Login Telegram dulu lewat Settings → Userbot.", reply_markup=userbot_menu_keyboard(label))
        return
    await update.message.reply_text(format_monitoring_menu(label, update.effective_user.id), reply_markup=monitoring_menu_keyboard(update.effective_user.id), parse_mode="HTML")


async def tg_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    label = selected_account_label(update.effective_user.id)
    await update.message.reply_text(format_settings_menu(label, update.effective_user.id), reply_markup=settings_menu_keyboard(update.effective_user.id), parse_mode="HTML")


async def tg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_reply_keyboard(update)
    user_id = update.effective_user.id
    await update.message.reply_text(
        format_help_html(),
        reply_markup=help_main_keyboard(user_id),
        parse_mode="HTML",
    )


async def tg_lapor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_broadcast_user(update.effective_user, source="report_command")
    await start_user_report_flow(update, context)


