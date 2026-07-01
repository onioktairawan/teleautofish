from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def styled_button(text: str, callback_data: str, style: str = "primary") -> InlineKeyboardButton:
    style = infer_button_style(text, callback_data, style)
    text, icon_id = premium_button_text_and_icon(text)
    kwargs = {"text": text, "callback_data": callback_data, "style": style}
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("icon_custom_emoji_id", None)
        return InlineKeyboardButton(**kwargs)


def styled_button_with_icon(text: str, callback_data: str, icon_emoji: str, style: str = "primary") -> InlineKeyboardButton:
    style = infer_button_style(text, callback_data, style)
    kwargs = {"text": text, "callback_data": callback_data, "style": style}
    icon_id = PREMIUM_EMOJI_IDS.get(icon_emoji) if main_premium_active() else None
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("icon_custom_emoji_id", None)
        return InlineKeyboardButton(**kwargs)


def compact_inline_keyboard_rows(rows: list, columns: int = 2) -> list[list[InlineKeyboardButton]]:
    buttons = []
    for row in rows or []:
        if isinstance(row, InlineKeyboardButton):
            buttons.append(row)
            continue
        for button in row or []:
            if button:
                buttons.append(button)
    return [buttons[i:i + columns] for i in range(0, len(buttons), columns)]


def compact_inline_markup(inline_keyboard, *args, **kwargs):
    return _TelegramInlineKeyboardMarkup(compact_inline_keyboard_rows(inline_keyboard), *args, **kwargs)


def reply_button(text: str, style: str = "primary", **kwargs) -> KeyboardButton:
    style = infer_button_style(text, requested=style)
    text, icon_id = premium_button_text_and_icon(text)
    kwargs = {"text": text, "style": style, **kwargs}
    if icon_id:
        kwargs["icon_custom_emoji_id"] = icon_id
    try:
        return KeyboardButton(**kwargs)
    except TypeError:
        kwargs.pop("icon_custom_emoji_id", None)
        return KeyboardButton(**kwargs)


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [reply_button("Menu", "primary"), reply_button("Mancing", "success")],
            [reply_button("Inventory", "primary"), reply_button("Status", "primary")],
            [reply_button("Settings", "primary"), reply_button("Lapor", "danger")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Pilih shortcut atau ketik input...",
    )


async def ensure_reply_keyboard(update: Update) -> bool:
    if not update.message or not update.effective_user:
        return False
    user_id = int(update.effective_user.id)
    if user_id in _reply_keyboard_sent:
        return False
    _reply_keyboard_sent.add(user_id)
    return True


def account_page_bounds(user_id: int, page: int = 0) -> tuple[list[dict], int, int]:
    accounts = load_accounts_for_user(user_id)
    total_pages = max(1, (len(accounts) + ACCOUNTS_PAGE_SIZE - 1) // ACCOUNTS_PAGE_SIZE)
    page = max(0, min(int(page or 0), total_pages - 1))
    return accounts, page, total_pages


def account_status_emoji(label: str) -> str:
    label = ctx_label(label)
    account = load_account(label)
    if _account_running.get(label):
        return "🟢"
    if account.get("restored_needs_login") or account.get("last_login_error") or not account_doc_exists(label):
        return "🟡"
    return "🔴"


def accounts_menu_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    accounts, page, total_pages = account_page_bounds(user_id, page)
    page_accounts = accounts[page * ACCOUNTS_PAGE_SIZE:(page + 1) * ACCOUNTS_PAGE_SIZE]
    rows = []
    for i in range(0, len(page_accounts), 2):
        row = []
        for account in page_accounts[i:i + 2]:
            label = account["label"]
            state = account_status_emoji(label)
            owner_id = account_primary_owner_id(account)
            name = account_display_name(account, owner_id)
            if label == "main" or owner_id == OWNER_ID:
                row.append(styled_button_with_icon(f"{state} Owner", f"account:select:{page}:{label}", "👑", "primary"))
            else:
                row.append(styled_button(f"{state} {name}", f"account:select:{page}:{label}", "primary"))
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(styled_button("⬅ Prev", f"account:page:{page - 1}", "primary"))
    if total_pages > 1:
        nav.append(styled_button(f"{page + 1}/{total_pages}", f"account:page:{page}", "primary"))
    if page < total_pages - 1:
        nav.append(styled_button("Next ➡", f"account:page:{page + 1}", "primary"))
    if nav:
        rows.append(nav)
    rows.append([styled_button("🏠 Main", "menu:main", "primary")])
    return compact_inline_markup(rows)


def account_detail_keyboard(label: str, page: int = 0) -> InlineKeyboardMarkup:
    safe = label.replace(":", "_")
    return compact_inline_markup([
        [
            styled_button("▶ Start", f"account:action:start:{page}:{safe}", "success"),
            styled_button("■ Stop", f"account:action:stop:{page}:{safe}", "danger"),
        ],
        [
            styled_button("📊 Status", f"account:action:status:{page}:{safe}", "primary"),
            styled_button("🧹 Clear Stuck", f"account:action:clear_stuck_prompt:{page}:{safe}", "danger"),
        ],
        [
            styled_button("⬅ Back", f"account:page:{page}", "primary"),
        ],
    ])


def clear_stuck_confirm_keyboard(label: str, page: int = 0) -> InlineKeyboardMarkup:
    safe = label.replace(":", "_")
    return compact_inline_markup([
        [
            styled_button("✅ Ya, Clear Stuck", f"account:action:clear_stuck_confirm:{page}:{safe}", "danger"),
        ],
        [
            styled_button("Batal", f"account:select:{page}:{safe}", "primary"),
        ],
    ])


def accounts_back_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", f"account:page:{page}", "primary")]])


def back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", callback_data, "primary")]])


def clean_inventory_confirm_keyboard(label: str = None) -> InlineKeyboardMarkup:
    label = ctx_label(label)
    return compact_inline_markup([
        [
            styled_button("✅ Setuju", f"fish:clean_inventory_confirm:{label}", "danger"),
            styled_button("❌ Batal", f"menu:inventory:{label}", "primary"),
        ],
    ])


def main_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    is_owner = user_id is None or can_manage_admins(user_id)
    rows = []
    if is_owner:
        rows.append([
            styled_button("👥 Accounts", "menu:accounts", "primary"),
            styled_button("🛡 Owner Panel", "owner:users", "danger"),
        ])
    rows.extend([
        [
            styled_button("🎣 Fishing", "menu:fishing", "success"),
            styled_button("🟥 Inventory", "menu:inventory", "primary"),
        ],
        [
            styled_button("❤️ Rules", "menu:rules", "primary"),
            styled_button("📊 Monitoring", "menu:monitoring", "primary"),
        ],
        [
            styled_button("🛠 Settings", "menu:settings", "primary"),
            styled_button("❔ Help", "fish:help", "primary"),
        ],
        [styled_button("🐞 Lapor", "report:start", "danger")],
    ])
    if not is_owner:
        rows.append([styled_button("👤 Akun Saya", "menu:account_status", "primary")])
    return compact_inline_markup(rows)


def welcome_keyboard(is_premium: bool, has_userbot: bool, user_id: int) -> InlineKeyboardMarkup:
    if not is_premium:
        return compact_inline_markup([
            [styled_button("🐞 Lapor", "report:start", "danger")],
            [InlineKeyboardButton("Hubungi Owner", url=f"tg://user?id={OWNER_ID}", style="primary")],
        ])
    if not has_userbot:
        return compact_inline_markup([
            [styled_button("🛠 Settings", "menu:settings", "primary"), styled_button("❔ Help", "fish:help", "primary")],
            [styled_button("🔐 Login Userbot", "userbot:login", "success")],
            [styled_button("🐞 Lapor", "report:start", "danger")],
        ])
    return compact_inline_markup([
        [styled_button("🎣 Mancing", "menu:fishing", "success"), styled_button("🟥 Inventory", "menu:inventory", "primary")],
        [styled_button("🏠 Menu", "menu:main", "primary"), styled_button("❔ Help", "fish:help", "primary")],
        [styled_button("🐞 Lapor", "report:start", "danger")],
    ])


def owner_users_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("👥 Users", "owner:section:users", "primary"),
            styled_button("⚙️ Operasi", "owner:section:ops", "success"),
        ],
        [
            styled_button("🎯 Grup Khusus", "owner:bulk_special", "primary"),
        ],
        [
            styled_button("🛠 Maintenance", "owner:section:maintenance", "primary"),
            styled_button("👤 Admin", "owner:section:admin", "primary"),
        ],
        [
            styled_button("📣 Broadcast", "owner:broadcast", "danger"),
        ],
        [
            styled_button("⏰ Daily Broadcast", "owner:daily:menu", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:main", "primary"),
        ],
    ])


def owner_users_section_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("📊 Ringkasan", "owner:users:summary", "success"),
        ],
        [
            styled_button("📋 Semua User", "owner:users:list", "primary"),
            styled_button("🟢 Sedang Jalan", "owner:users:running", "success"),
        ],
        [
            styled_button("🟡 Butuh Tindakan", "owner:users:not_login", "primary"),
        ],
        [
            styled_button("⬅ Owner", "owner:users", "primary"),
        ],
    ])


def owner_ops_section_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("▶ Start Semua", "owner:all:start", "success"),
            styled_button("■ Stop Semua", "owner:all:stop", "danger"),
        ],
        [
            styled_button("🔄 Restart Bot", "fish:restart", "danger"),
        ],
        [
            styled_button("⬅ Owner", "owner:users", "primary"),
        ],
    ])


def owner_bulk_special_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("Set Grup Semua", "owner:bulk_special:set_group", "success"),
            styled_button("Mode Grup Semua", "owner:bulk_special:mode", "primary"),
        ],
        [
            styled_button("Auto Open ON", "owner:bulk_special:auto_on", "success"),
            styled_button("Auto Open OFF", "owner:bulk_special:auto_off", "danger"),
        ],
        [
            styled_button("Boost ON", "owner:bulk_special:boost_on", "success"),
            styled_button("Boost OFF", "owner:bulk_special:boost_off", "danger"),
        ],
        [
            styled_button("Set Delay Semua", "owner:bulk_special:delay", "primary"),
        ],
        [
            styled_button("⬅ Owner", "owner:users", "primary"),
        ],
    ])


def owner_maintenance_section_keyboard() -> InlineKeyboardMarkup:
    enabled = maintenance_enabled()
    return compact_inline_markup([
        [
            styled_button("Maintenance ON" if enabled else "Maintenance OFF", "owner:maintenance:toggle", "danger" if enabled else "success"),
        ],
        [
            styled_button("⏰ Set Jadwal", "owner:maintenance:schedule_set", "primary"),
            styled_button("🗑 Clear Jadwal", "owner:maintenance:schedule_clear", "danger"),
        ],
        [
            styled_button("🧾 Issue Log", "owner:audit", "primary"),
            styled_button("🩺 Health", "owner:health", "success"),
        ],
        [
            styled_button("💾 Backup", "owner:backup", "primary"),
        ],
        [
            styled_button("⬅ Owner", "owner:users", "primary"),
        ],
    ])


def owner_admin_section_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("👥 Admin List", "admin:list", "primary"),
            styled_button("👤 Tambah Admin", "admin:add", "primary"),
        ],
        [
            styled_button("⬅ Owner", "owner:users", "primary"),
        ],
    ])


def owner_user_action_keyboard(label: str) -> InlineKeyboardMarkup:
    safe = label.replace(":", "_")
    return compact_inline_markup([
        [
            styled_button("▶ Start", f"owner:user:start:{safe}", "success"),
            styled_button("■ Stop", f"owner:user:stop:{safe}", "danger"),
        ],
        [
            styled_button("📊 Status", f"owner:user:status:{safe}", "primary"),
            styled_button("⬅ Users", "owner:users", "primary"),
        ],
    ])


def broadcast_preview_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("🌐 Kirim Public", "owner:broadcast:send:public", "danger"),
        ],
        [
            styled_button("⭐ Kirim Premium", "owner:broadcast:send:premium", "danger"),
        ],
        [
            styled_button("Batal", "owner:broadcast:cancel", "primary"),
        ],
    ])


def daily_broadcast_keyboard() -> InlineKeyboardMarkup:
    config = load_daily_broadcast_config()
    enabled = config.get("enabled", False)
    return compact_inline_markup([
        [
            styled_button("Set Pesan/Media", "owner:daily:set_payload", "primary"),
        ],
        [
            styled_button("Set Jam (Sekarang: " + config.get("time", "20:00") + ")", "owner:daily:set_time", "primary"),
        ],
        [
            styled_button("Target: " + config.get("target", "premium").capitalize(), "owner:daily:toggle_target", "primary"),
        ],
        [
            styled_button("Test Kirim (Preview)", "owner:daily:preview", "primary"),
        ],
        [
            styled_button("Status: " + ("ON" if enabled else "OFF"), "owner:daily:toggle_status", "success" if enabled else "danger"),
        ],
        [
            styled_button("⬅ Back", "owner:users", "primary"),
        ],
    ])


def backup_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("💾 Backup Sekarang", "owner:backup:create", "success"),
        ],
        [
            styled_button("♻ Restore Config", "owner:backup:restore", "danger"),
        ],
        [
            styled_button("⬅ Back", "owner:users", "primary"),
        ],
    ])


def fishing_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("▶ Start", "fish:start", "success"),
            styled_button("■ Stop", "fish:stop", "danger"),
        ],
        [
            styled_button("📊 Status", "fish:status", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:main", "primary"),
        ],
    ])


def inventory_menu_keyboard(label: str = None) -> InlineKeyboardMarkup:
    label = ctx_label(label)
    poseidon_enabled = poseidon_favorite_enabled(label)
    return compact_inline_markup([
        [
            styled_button("🟢 Preview Filter", f"fish:inv:{label}", "primary"),
            styled_button("🧹 Bersihkan", f"fish:clean_inventory:{label}", "danger"),
        ],
        [
            styled_button("🌟 History Fav", f"fish:gallery:{label}", "primary"),
        ],
        [
            styled_button(
                "🔱 Trisula: Fav" if poseidon_enabled else "🔱 Trisula: Jual",
                f"fish:poseidon_toggle:{label}",
                "success" if poseidon_enabled else "danger",
            ),
        ],
        [
            styled_button("⬅ Back", "menu:main", "primary"),
        ],
    ])


def callback_label_or_selected(data: str, prefix: str, fallback_label: str) -> str:
    raw = (data or "")[len(prefix):].strip()
    return safe_label(raw) if raw else ctx_label(fallback_label)


def monitoring_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    rows = [[styled_button("📊 Refresh Status", "fish:status", "primary")]]
    if user_id is None or can_manage_admins(user_id):
        rows.append([styled_button("📈 Stats", "fish:stats", "primary")])
    rows.append([styled_button("⬅ Back", "menu:main", "primary")])
    return compact_inline_markup(rows)


def settings_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("🔁 Mode", "menu:mode", "primary"),
            styled_button("🌏 Groups", "menu:groups", "primary"),
        ],
        [
            styled_button("🎯 Grup Khusus", "menu:special_group", "primary"),
            styled_button("🎣 Private", "menu:private", "primary"),
        ],
        [
            styled_button("🤖 Userbot", "menu:userbot", "success"),
        ],
        [
            styled_button("⬅ Back", "menu:main", "primary"),
        ],
    ])


def mode_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("Private", "mode:set:private", "primary"),
            styled_button("Group", "mode:set:group_room", "primary"),
        ],
        [
            styled_button("All / Hybrid", "mode:set:all", "success"),
            styled_button("Grup Khusus", "mode:set:special_group", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:settings", "primary"),
        ],
    ])


def rules_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("✅ List Keep", "rules:keep_menu", "success"),
            styled_button("🚫 List Sell", "rules:sell_menu", "danger"),
        ],
        [
            styled_button("📋 List Rules", "rules:list_all", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:main", "primary"),
        ],
    ])


def rules_list_keyboard(kind: str) -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("➕ Add List", f"rules:{kind}_add", "success"),
            styled_button("🗑 Remove List", f"rules:{kind}_del", "danger"),
        ],
        [
            styled_button("⬅ Back", "menu:rules", "primary"),
        ],
    ])


def rules_back_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", "menu:rules", "primary")]])


def main_back_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", "menu:main", "primary")]])


def help_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    rows = [
        [
            styled_button("🔐 Login", "help:topic:login", "primary"),
            styled_button("🎣 Start/Stop", "help:topic:fishing", "success"),
        ],
        [
            styled_button("🔁 Mode", "help:topic:mode", "primary"),
            styled_button("🟥 Inventory", "help:topic:inventory", "primary"),
        ],
        [
            styled_button("❤️ Rules", "help:topic:rules", "primary"),
            styled_button("🎯 Grup Khusus", "help:topic:special", "primary"),
        ],
        [
            styled_button("📊 Monitoring", "help:topic:monitoring", "primary"),
        ],
    ]
    if user_id is None or is_admin_user(user_id):
        rows.append([styled_button("⬅ Back", "menu:main", "primary")])
    return compact_inline_markup(rows)


def help_topic_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    rows = [[styled_button("⬅ Help", "fish:help", "primary")]]
    if user_id is None or is_admin_user(user_id):
        rows.append([styled_button("🏠 Menu", "menu:main", "primary")])
    return compact_inline_markup(rows)


def groups_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("📋 List", "groups:list", "primary"),
            styled_button("➕ Add", "groups:add", "success"),
        ],
        [
            styled_button("🗑 Remove", "groups:del", "danger"),
        ],
        [
            styled_button("⬅ Back", "menu:settings", "primary"),
        ],
    ])


def groups_back_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", "menu:groups", "primary")]])


def special_group_menu_keyboard(label: str = None) -> InlineKeyboardMarkup:
    label = ctx_label(label)
    auto_label = "Auto Open: ON" if special_auto_open_enabled(label) else "Auto Open: OFF"
    boost_label = "Boost: ON" if special_auto_boost_enabled(label) else "Boost: OFF"
    return compact_inline_markup([
        [
            styled_button("✏️ Set Grup", "special:set", "success"),
            styled_button("🗑 Hapus", "special:clear", "danger"),
        ],
        [
            styled_button(auto_label, "special:auto_toggle", "success" if special_auto_open_enabled(label) else "danger"),
            styled_button("⏱ Waktu Tunggu", "special:delay", "primary"),
        ],
        [
            styled_button(boost_label, "special:boost_toggle", "success" if special_auto_boost_enabled(label) else "danger"),
        ],
        [
            styled_button("⬅ Back", "menu:settings", "primary"),
        ],
    ])


def special_delay_menu_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("9-12s", "special:delay:set:9:12", "primary"),
            styled_button("15-18s", "special:delay:set:15:18", "success"),
        ],
        [
            styled_button("20-23s", "special:delay:set:20:23", "primary"),
            styled_button("25-28s", "special:delay:set:25:28", "primary"),
        ],
        [
            styled_button("Custom", "special:delay:custom", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:special_group", "primary"),
        ],
    ])


def special_group_back_keyboard() -> InlineKeyboardMarkup:
    return compact_inline_markup([[styled_button("⬅ Back", "menu:special_group", "primary")]])


def private_settings_keyboard(label: str = None) -> InlineKeyboardMarkup:
    label = ctx_label(label)
    enabled = private_auto_boost_enabled(label)
    return compact_inline_markup([
        [
            styled_button("Ubah Bot Private", "private:bot_set", "primary"),
            styled_button("Reset Default", "private:bot_reset", "danger"),
        ],
        [
            styled_button(f"Auto Boost: {'ON' if enabled else 'OFF'}", "private:boost_toggle", "success" if enabled else "danger"),
        ],
        [
            styled_button("Coba Boost Lagi", "private:boost_reset", "primary"),
        ],
        [
            styled_button("Refresh", "private:refresh", "primary"),
        ],
        [
            styled_button("⬅ Back", "menu:settings", "primary"),
        ],
    ])


def userbot_menu_keyboard(label: str = None) -> InlineKeyboardMarkup:
    label = ctx_label(label)
    rows = []
    if not account_doc_exists(label):
        rows.append([styled_button("🔐 Login Userbot", "userbot:login", "success")])
    rows.append([
        styled_button("⬅ Back", "menu:settings", "primary"),
    ])
    return compact_inline_markup(rows)


def input_flow_keyboard(back_callback: str = "menu:settings") -> InlineKeyboardMarkup:
    return compact_inline_markup([
        [
            styled_button("⬅ Back", back_callback, "primary"),
        ],
    ])


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[reply_button("📱 Kontak Gua", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Kirim kontak atau ketik nomor...",
    )


