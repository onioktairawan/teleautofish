from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def account_doc_exists(label: str) -> bool:
    label = ctx_label(label)
    account = load_account(label)
    if account.get("last_login_error") or account.get("restored_needs_login"):
        return False
    session_name = account.get("session_name") or ("fishbot_session" if label == "main" else f"fishbot_session_{label}")
    if label == "main":
        return any(path.exists() for path in session_files_for_name(session_name))
    if mongo_enabled():
        doc = db_get_doc("account", label)
        if not doc or doc.get("last_login_error") or doc.get("restored_needs_login"):
            return False
        return safe_user_id((doc.get("telegram_user") or {}).get("id")) > 0
    return any(path.exists() for path in session_files_for_name(session_name))


def userbot_status_text(label: str = None) -> str:
    label = ctx_label(label)
    account = load_account(label)
    if account.get("restored_needs_login"):
        return "Perlu login ulang"
    if account.get("last_login_error"):
        return "Login bermasalah"
    return "Sudah login" if account_doc_exists(label) else "Belum login"


def fishing_status_text(label: str = None) -> str:
    return "Jalan" if _account_running.get(ctx_label(label)) else "Berhenti"


def mode_display_name(mode: str) -> str:
    return {
        "private": "Private",
        "group_room": "Grup",
        "all": "Grup + Private",
        "special_group": "Grup Khusus",
    }.get(str(mode or ""), str(mode or "-"))


def account_display_name(account: dict, fallback_user_id: int = None) -> str:
    tg_user = account.get("telegram_user") or {}
    first_name = tg_user.get("first_name")
    last_name = tg_user.get("last_name")
    full_name = tg_user.get("full_name")
    tg_id = tg_user.get("id") or fallback_user_id
    if first_name:
        return str(first_name)
    if last_name:
        return str(last_name)
    if full_name:
        return str(full_name)
    if safe_user_id(tg_id) == OWNER_ID:
        return "👑 Owner"
    return str(tg_id or account.get("label", "-"))


def format_account_link(name: str, user_id: int) -> str:
    safe_name = html.escape(name or str(user_id))
    return f'<a href="tg://user?id={int(user_id)}">{safe_name}</a>'


def account_name_for_label(label: str, fallback_user_id: int = 0) -> str:
    label = ctx_label(label)
    account = load_account(label)
    owner_id = safe_user_id(fallback_user_id) or account_primary_owner_id(account)
    return account_display_name(account, owner_id)


def account_names_for_labels(labels: list[str]) -> list[str]:
    return [account_name_for_label(label) for label in labels]


def admin_display_name(admin_id: int) -> str:
    admin_id = int(admin_id or 0)
    for account in load_all_accounts():
        if admin_id in set(account_owner_ids(account)):
            return account_display_name(account, admin_id)
    return "Owner" if admin_id == OWNER_ID else "Belum login"


def expandable_blockquote(text: str) -> str:
    return f"<blockquote expandable>{html.escape(text)}</blockquote>"


def blockquote(text: str) -> str:
    return f"<blockquote>{html.escape(text)}</blockquote>"


def format_accounts_text(user_id: int, page: int = 0) -> str:
    accounts, page, total_pages = account_page_bounds(user_id, page)
    if not accounts:
        return "👤 Accounts\n\nBelum ada akun yang login."
    selected = selected_account_label(user_id)
    lines = []
    page_accounts = accounts[page * ACCOUNTS_PAGE_SIZE:(page + 1) * ACCOUNTS_PAGE_SIZE]
    for account in page_accounts:
        label = account["label"]
        owner_id = account_primary_owner_id(account)
        name = account_display_name(account, owner_id)
        state = f"{account_status_emoji(label)} {userbot_status_text(label)} | Mancing: {fishing_status_text(label)}"
        marker = "&gt;" if label == selected else "-"
        display = html.escape(name)
        lines.append(f"{marker} {display} - {state}")
    summary = html.escape(f"Total: {len(accounts)}\nHalaman: {page + 1}/{total_pages}")
    return "👤 Accounts\n\n<blockquote expandable>" + summary + "\n\n" + "\n".join(lines) + "</blockquote>"


def format_userbot_text(user_id: int) -> str:
    label = preferred_login_label(user_id)
    account = load_account(label)
    name = account_display_name(account, user_id)
    userbot_status = userbot_status_text(label)
    loop_status = fishing_status_text(label)
    return (
        "🤖 Userbot\n\n"
        f"Nama: {name}\n"
        f"Akses bot: {'Aktif' if is_admin_user(user_id) else 'Belum aktif'}\n"
        f"Login Telegram: {userbot_status}\n"
        f"Auto mancing: {loop_status}\n\n"
        "Login butuh nomor HP Telegram, kode OTP, dan password 2FA kalau akun kamu pakai 2FA."
    )


def format_welcome_text(user_id: int, first_name: str = None) -> str:
    is_premium = is_admin_user(user_id)
    label = selected_account_label(user_id) if is_premium else default_user_account_label(user_id)
    account = load_account(label)
    name = first_name or account_display_name(account, user_id)
    has_userbot = account_doc_exists(label)
    status = "Aktif" if is_premium else "Belum aktif"
    body = (
        f"Selamat datang, {name}.\n\n"
        "Bot ini membantu auto mancing, bersihkan inventory, dan menyimpan item penting otomatis.\n\n"
        f"Akses bot: {status}\n"
        f"Login Telegram: {userbot_status_text(label)}"
    )
    if not is_premium:
        body += "\n\nHubungi owner untuk aktivasi premium."
    elif not has_userbot:
        body += "\n\nKlik Login Userbot untuk login Telegram dulu."
    else:
        body += "\n\nGunakan keyboard bawah atau tombol menu untuk kontrol bot."
    return "🎣 <b>Fish Bot</b>\n\n" + blockquote(body)


def format_owner_dashboard() -> str:
    admins = load_admin_ids()
    accounts = load_all_accounts()
    premium_count = max(0, len(admins) - 1)
    userbot_active = sum(1 for account in accounts if account.get("label") != "main")
    running_count = len(running_labels())
    not_login = max(0, premium_count - userbot_active)
    body = (
        f"User aktif: {premium_count}\n"
        f"Sudah login Telegram: {userbot_active}\n"
        f"Auto mancing jalan: {running_count}\n"
        f"Belum login: {not_login}\n"
        f"Maintenance: {'ON' if maintenance_enabled() else 'OFF'}"
    )
    return "👥 <b>Users Dashboard</b>\n\n" + expandable_blockquote(body)


def format_owner_maintenance_text() -> str:
    resume = maintenance_resume_labels() if maintenance_enabled() else []
    schedule_enabled, schedule_start, schedule_end = maintenance_schedule_settings()
    schedule_now, _ = maintenance_schedule_active_now()
    schedule_text = f"ON {schedule_start}-{schedule_end} WIB" if schedule_enabled else "OFF"
    if schedule_enabled:
        schedule_text += f" (sekarang: {'aktif' if schedule_now else 'di luar jadwal'})"
    body = (
        f"Status: {'ON' if maintenance_enabled() else 'OFF'}\n"
        f"Loop berjalan: {len(running_labels())}\n"
        f"Resume nanti: {len(resume)} akun\n\n"
        f"Jadwal: {schedule_text}\n\n"
        "Saat ON, semua fitur user/premium diblokir dan loop mancing tidak bisa start. Bot owner tetap aktif untuk kontrol."
    )
    return "🛠 <b>Maintenance</b>\n\n" + expandable_blockquote(body)


def format_status_rows(rows: list[tuple[str, str]], limit: int = 12) -> str:
    if not rows:
        return "-"
    visible = rows[:limit]
    name_width = min(18, max(len(name) for name, _ in visible))
    lines = []
    for name, status in visible:
        padded_name = name.ljust(name_width)
        lines.append(f"{padded_name} | {status}" if status else padded_name)
    if len(rows) > limit:
        lines.append(f"... dan {len(rows) - limit} akun lagi")
    return "\n".join(lines)


def compact_age(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def seconds_since_iso(value: str) -> int | None:
    if not value:
        return None
    try:
        detected_at = datetime.fromisoformat(str(value))
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=WIB)
        return int((now_wib() - detected_at.astimezone(WIB)).total_seconds())
    except Exception:
        return None


def format_compact_rows(rows: list[tuple[str, str]], limit: int = 6) -> str:
    if not rows:
        return "-"
    visible = rows[:limit]
    lines = [f"{name} | {status}" if status else name for name, status in visible]
    if len(rows) > limit:
        lines.append(f"... +{len(rows) - limit} akun")
    return "\n".join(lines)


def format_owner_users_section() -> str:
    accounts = load_all_accounts()
    active_rows: list[tuple[str, str]] = []
    recent_rows: list[tuple[int, str, str]] = []
    check_rows: list[tuple[str, str]] = []
    stopped_rows: list[tuple[str, str]] = []
    login_rows: list[tuple[str, str]] = []
    active_mode_counts: dict[str, int] = {}

    for account in accounts:
        label = safe_label(account.get("label", "main"))
        owner_id = account_primary_owner_id(account)
        name = account_display_name(account, owner_id)
        if account.get("restored_needs_login") or not account_doc_exists(label):
            login_rows.append((name, "belum login"))
            continue

        running = bool(_account_running.get(label))
        inactive = seconds_since_activity(label)
        inactive_text = compact_age(inactive)
        mode_name = mode_display_name(current_fish_mode(label))
        if account.get("verification_required"):
            verify_age = compact_age(seconds_since_iso(account.get("verification_detected_at", "")))
            check_rows.append((name, f"{mode_name} | verifikasi {verify_age}"))
            continue
        if not running:
            stopped_rows.append((name, "belum jalan"))
            continue
        if inactive is not None and inactive >= WATCHDOG_TIMEOUT:
            check_rows.append((name, f"{mode_name} | tidak aktif {inactive_text}"))
            continue
        active_rows.append((name, f"{mode_name} | {inactive_text}"))
        recent_rows.append((inactive if inactive is not None else 10**9, name, inactive_text))
        active_mode_counts[mode_name] = active_mode_counts.get(mode_name, 0) + 1

    recent_rows.sort(key=lambda row: row[0])
    mode_summary = "\n".join(f"{mode}: {count}" for mode, count in sorted(active_mode_counts.items())) or "-"
    recent_summary = " · ".join(f"{name} {age}" for _, name, age in recent_rows[:5]) or "-"
    off_login_count = len(stopped_rows) + len(login_rows)
    body = (
        f"🟢 {len(active_rows)} jalan  ·  🟡 {len(check_rows)} cek  ·  🔴 {off_login_count} off/login\n"
        f"{now_wib().strftime('%H:%M')} WIB · Total {len(accounts)} akun\n\n"
        "🟡 PERLU DICEK\n"
        f"{format_compact_rows(check_rows, limit=8)}\n\n"
        "🟢 AKTIF\n"
        f"{mode_summary}\n\n"
        "📍 Terakhir aktif\n"
        f"{recent_summary}"
    )
    extra_sections = []
    if stopped_rows:
        extra_sections.append("⏸ BELUM JALAN\n" + format_compact_rows(stopped_rows, limit=5))
    if login_rows:
        extra_sections.append("🔐 BELUM LOGIN\n" + format_compact_rows(login_rows, limit=5))
    if extra_sections:
        body += "\n\n" + "\n\n".join(extra_sections)
    return "👥 <b>Users</b>\n\n" + expandable_blockquote(body)


def format_backup_menu_text() -> str:
    body = (
        "Backup menyimpan file lokal, session Pyrogram, dan .env ke ZIP lalu mengirimnya ke owner.\n\n"
        "Yang ikut backup: file config lokal, session, dan .env.\n\n"
        "Yang tidak ikut backup: data Mongo, login Telegram, token bot, API hash, dan credential Google. "
        "Kalau server baru pakai Mongo URL yang sama, data Mongo tetap aman."
    )
    return "💾 <b>Backup & Restore</b>\n\n" + expandable_blockquote(body)


def bulk_special_target_labels() -> list[str]:
    labels = []
    for account in load_all_accounts():
        label = safe_label(account.get("label", "main"))
        if not account.get("enabled", True):
            continue
        if account.get("restored_needs_login"):
            continue
        labels.append(label)
    return sorted(set(labels))


def owner_bulk_target_labels() -> list[str]:
    return bulk_special_target_labels()


def format_bulk_special_text() -> str:
    labels = bulk_special_target_labels()
    names = account_names_for_labels(labels)
    body = (
        f"Target akun: {len(labels)} enabled dan siap setting\n"
        f"Nama: {', '.join(names[:20]) or '-'}"
    )
    if len(labels) > 20:
        body += f"\n... dan {len(labels) - 20} akun lagi"
    body += (
        "\n\nOperasi ini hanya mengubah setting. "
        "Loop tidak akan otomatis distart."
    )
    return "🎯 <b>Bulk Grup Khusus</b>\n\n" + expandable_blockquote(body)


def format_bulk_result_text(title: str, changed: list[str], skipped: list[str] = None, failed: list[str] = None) -> str:
    skipped = skipped or []
    failed = failed or []
    changed_names = account_names_for_labels(changed)
    skipped_names = account_names_for_labels(skipped)
    body = (
        f"Berhasil: {len(changed)}\n"
        f"Skip: {len(skipped)}\n"
        f"Gagal: {len(failed)}\n\n"
        f"Berhasil: {', '.join(changed_names[:20]) or '-'}"
    )
    if len(changed) > 20:
        body += f"\n... dan {len(changed) - 20} akun berhasil lagi"
    if skipped:
        body += f"\n\nSkip: {', '.join(skipped_names[:20])}"
    if failed:
        body += f"\n\nGagal: {', '.join(failed[:20])}"
    return f"✅ <b>{title}</b>\n\n" + expandable_blockquote(body)


def format_owner_account_summary() -> str:
    accounts = load_all_accounts()
    rows = []
    total = len(accounts)
    running = 0
    stopped = 0
    needs_login = 0
    for account in accounts:
        label = safe_label(account.get("label", "main"))
        owner_id = account_primary_owner_id(account)
        name = account_display_name(account, owner_id)
        is_running = bool(_account_running.get(label))
        if is_running:
            running += 1
        else:
            stopped += 1
        if account.get("restored_needs_login"):
            needs_login += 1
        inactive = seconds_since_activity(label)
        last_seen = f"{inactive}s" if inactive is not None else "-"
        state = "JALAN" if is_running else "BERHENTI"
        if account.get("restored_needs_login"):
            state = "BELUM LOGIN"
        rows.append(f"• {name} | {state} | {mode_display_name(current_fish_mode(label))} | aktif {last_seen} lalu")
    body = (
        f"Total akun: {total}\n"
        f"Sedang jalan: {running}\n"
        f"Berhenti: {stopped}\n"
        f"Belum login: {needs_login}\n"
        f"Jam WIB: {now_wib().strftime('%H:%M')}\n\n"
        + ("\n".join(rows[:30]) if rows else "Tidak ada akun.")
    )
    if len(rows) > 30:
        body += f"\n... dan {len(rows) - 30} akun lagi"
    return "📊 <b>Ringkasan Semua Akun</b>\n\n" + expandable_blockquote(body)


def format_health_dashboard() -> str:
    accounts = load_all_accounts()
    total = len(accounts)
    running = len(running_labels())
    not_login = sum(1 for account in accounts if account.get("label") != "main" and not account_doc_exists(account.get("label", "main")))
    inactive_rows = []
    for account in accounts:
        label = account.get("label", "main")
        inactive = seconds_since_activity(label)
        if _account_running.get(label) and inactive is not None and inactive >= WATCHDOG_TIMEOUT:
            name = account_display_name(account, account_primary_owner_id(account))
            inactive_rows.append(f"• {name}: tidak ada aktivitas {inactive}s")
    body = (
        f"Total akun: {total}\n"
        f"Sedang jalan: {running}\n"
        f"Berhenti: {max(0, total - running)}\n"
        f"Belum login: {not_login}\n"
        f"Database: {'aktif' if mongo_enabled() else 'off'}\n"
        "Solver: lokal\n"
        f"Batas tidak aktif: {WATCHDOG_TIMEOUT}s\n\n"
        "Perlu dicek:\n"
        + ("\n".join(inactive_rows[:20]) if inactive_rows else "Tidak ada.")
    )
    return "🩺 <b>Health Dashboard</b>\n\n" + expandable_blockquote(body)


def format_owner_user_list(kind: str = "all") -> str:
    accounts = load_all_accounts()
    known_owner_ids = {owner_id for account in accounts for owner_id in account_owner_ids(account)}
    rows = []
    for account in accounts:
        label = account.get("label", "main")
        if label == "main":
            continue
        owner_id = account_primary_owner_id(account)
        if kind == "running" and not _account_running.get(label):
            continue
        if kind == "not_login" and account_doc_exists(label):
            continue
        name = account_display_name(account, owner_id)
        state = "jalan" if _account_running.get(label) else "berhenti"
        rows.append(f"• {name} - {state}")
    if kind in {"all", "not_login"}:
        for admin_id in admin_user_ids(include_owner=False):
            if admin_id in known_owner_ids:
                continue
            if kind == "all":
                rows.append("• Belum login")
            elif kind == "not_login":
                rows.append("• Belum login")
    title = {"running": "🟢 User Sedang Jalan", "not_login": "🟡 Butuh Tindakan"}.get(kind, "📋 List User")
    body = "\n".join(rows) or "Tidak ada data."
    return f"<b>{title}</b>\n\n" + expandable_blockquote(body)


def audit_display_name(label: str) -> str:
    label = ctx_label(label)
    account = load_account(label)
    owner_id = account_primary_owner_id(account)
    name = account_display_name(account, owner_id)
    return name or label


def format_audit_text(limit: int = 10, issues_only: bool = True) -> str:
    logs = load_audit_logs(limit=limit, issues_only=issues_only)
    if not logs:
        body = "Belum ada issue/verifikasi gagal yang perlu dicek." if issues_only else "Belum ada audit log."
    else:
        lines = []
        for log in logs:
            created_text = format_wib_time(log.get("created_at"))
            message = str(log.get("message", "-")).replace("\n", " ")[:140]
            name = audit_display_name(log.get("label", "main"))
            lines.append(f"• {created_text} [{name}] {log.get('event', '-')}: {message}")
        body = "\n".join(lines)
    title = "🧾 <b>Issue Log</b>" if issues_only else "🧾 <b>Audit Log</b>"
    return title + "\n\n" + expandable_blockquote(body)


def format_fishing_menu(label: str = None) -> str:
    label = ctx_label(label)
    mode = current_fish_mode(label)
    status = fishing_status_text(label)
    body = (
        f"Auto mancing: {status}\n"
        f"Mode mancing: {mode_display_name(mode)}\n"
        f"Aksi terakhir: {_account_last_action.get(label, '-')}\n"
        f"Kabar terakhir: {_account_last_event.get(label, '-')}"
    )
    return "🎣 <b>Fishing</b>\n\n" + expandable_blockquote(body)


def format_inventory_menu(label: str = None) -> str:
    label = ctx_label(label)
    sell_lock = _account_sell_locks.get(label)
    sell_state = "sedang bersih-bersih" if sell_lock and sell_lock.locked() else "tidak berjalan"
    poseidon_status = "difavorite" if poseidon_favorite_enabled(label) else "ikut dijual"
    body = (
        f"Bersihkan inventory: {sell_state}\n"
        f"Trisula Poseidon: {poseidon_status}\n"
        f"Jual terakhir: {_account_last_sell.get(label, '-')}\n\n"
        "Preview filter untuk cek item yang akan disimpan sebelum inventory dibersihkan."
    )
    return "🟥 <b>Inventory</b>\n\n" + expandable_blockquote(body)


def format_rare_gallery_text(label: str = None) -> str:
    label = ctx_label(label)
    rows = load_rare_gallery(label, limit=10)
    if not rows:
        body = "Belum ada history item yang difavorite."
    else:
        lines = []
        for row in rows:
            created_text = format_wib_time(row.get("created_at"))
            lines.append(
                f"• {created_text} | {row.get('name', '-')}\n"
                f"  Reason: {row.get('reason', '-')}\n"
                f"  Detail: {row.get('text', '-')}"
            )
        body = "\n\n".join(lines)
    return "🌟 <b>History Fav</b>\n\n" + expandable_blockquote(body)


def format_monitoring_menu(label: str = None, user_id: int = None) -> str:
    label = ctx_label(label)
    inactive = seconds_since_activity(label)
    last_seen = f"{inactive}s lalu" if inactive is not None else "-"
    account = load_account(label)
    owner_id = safe_user_id(user_id) or account_primary_owner_id(account)
    name = account_display_name(account, owner_id)
    body = (
        f"Nama: {name}\n"
        f"Akses bot: {'Aktif' if owner_id and is_admin_user(owner_id) else '-'}\n"
        f"Login Telegram: {userbot_status_text(label)}\n"
        f"Auto mancing: {fishing_status_text(label)}\n"
        f"Mode mancing: {mode_display_name(current_fish_mode(label))}\n"
        f"Jam WIB: {now_wib().strftime('%H:%M')}\n"
        f"Grup khusus: {load_special_group_chat(label) or '-'}\n"
        f"Inventory: {int(account.get('inventory_slots_used', 0) or 0)}/{int(account.get('inventory_slots_total', 0) or 0)}\n"
        "Jual otomatis: saat inventory penuh\n"
        f"Terakhir aktif: {last_seen}\n"
        f"Kabar terakhir: {_account_last_event.get(label, '-')}"
    )
    return "📊 <b>Status Akun</b>\n\n" + expandable_blockquote(body)


def format_settings_menu(label: str = None, user_id: int = None) -> str:
    label = ctx_label(label)
    account = load_account(label)
    owner_id = safe_user_id(user_id) or account_primary_owner_id(account)
    name = account_display_name(account, owner_id)
    body = (
        f"Nama: {name}\n"
        f"Akses bot: {'Aktif' if owner_id and is_admin_user(owner_id) else '-'}\n"
        f"Login Telegram: {userbot_status_text(label)}\n"
        f"Mode mancing: {mode_display_name(current_fish_mode(label))}\n"
        f"Boost private: {private_boost_status_text(label)}\n"
        f"Jumlah grup: {len(configured_group_chats(label))}\n"
        f"Grup khusus: {load_special_group_chat(label) or '-'}\n"
        "Jual otomatis: saat inventory penuh\n"
        f"Jam WIB: {now_wib().strftime('%H:%M')}"
    )
    return "🛠 <b>Settings</b>\n\n" + expandable_blockquote(body)


def private_boost_status_text(label: str = None) -> str:
    label = ctx_label(label)
    if not private_auto_boost_enabled(label):
        return "OFF"
    if private_boost_paused(label):
        return "Paused - fragment kurang"
    boost_until = _account_private_boost_until.get(label)
    if boost_until and now_wib() < boost_until:
        remaining = int((boost_until - now_wib()).total_seconds())
        minutes, seconds = divmod(max(0, remaining), 60)
        return f"Sisa waktu: {minutes:02d}:{seconds:02d}:00"
    return "Siap dicoba"


def format_private_settings_text(label: str = None) -> str:
    label = ctx_label(label)
    private_bot = saved_private_bot_username(label)
    active_bot = private_command_bot_username(label)
    private_bot_note = "aktif di mode private" if current_fish_mode(label) == "private" else "hanya aktif saat mode private"
    body = (
        f"Nama: {account_name_for_label(label)}\n"
        f"Auto Boost Private: {'ON' if private_auto_boost_enabled(label) else 'OFF'}\n"
        f"Boost Status: {private_boost_status_text(label)}\n"
        f"Bot private: {private_bot} ({private_bot_note})\n"
        f"Bot aktif sekarang: {active_bot}\n"
        f"Bot global: {FISH_BOT_USERNAME}\n"
        f"Terakhir boost: {_account_private_boost_last.get(label, '-')}\n\n"
        "Boost private berjalan sebagai bonus. Gagal atau timeout tidak menghentikan /mancing."
    )
    return "🎣 <b>Private Settings</b>\n\n" + expandable_blockquote(body)


def format_main_menu(label: str = None, user_id: int = None) -> str:
    label = ctx_label(label)
    status = "🟢 Jalan" if _account_running.get(label) else "🔴 Berhenti"
    rules = load_fish_rules(label)
    inactive = seconds_since_activity(label)
    last_seen = f"{inactive}s lalu" if inactive is not None else "-"
    account = load_account(label)
    owner_id = safe_user_id(user_id) or account_primary_owner_id(account)
    name = account_display_name(account, owner_id)
    body = (
        f"Nama: {name}\n"
        f"Akses bot: {'Aktif' if owner_id and is_admin_user(owner_id) else '-'}\n"
        f"Login Telegram: {userbot_status_text(label)}\n"
        f"Auto mancing: {status}\n"
        f"Mode mancing: {mode_display_name(current_fish_mode(label))}\n"
        f"Jam WIB: {now_wib().strftime('%H:%M')}\n"
        f"Grup khusus: {load_special_group_chat(label) or '-'}\n"
        f"Inventory: {int(account.get('inventory_slots_used', 0) or 0)}/{int(account.get('inventory_slots_total', 0) or 0)}\n"
        "Jual otomatis: saat inventory penuh\n"
        f"Kabar terakhir: {_account_last_event.get(label, '-')}\n"
        f"Terakhir aktif: {last_seen}\n"
        f"List simpan: {len(rules['keep'])}\n"
        f"List jual: {len(rules['sell'])}"
    )
    return "🎣 <b>Fish Bot</b>\n\n" + expandable_blockquote(body)


def format_detailed_status(label: str = None) -> str:
    primary_label = ctx_label(label)
    stats = load_stats(primary_label)
    status = fishing_status_text(primary_label)
    labels = running_labels()
    inactive = seconds_since_activity(primary_label)
    last_seen = f"{inactive}s lalu" if inactive is not None else "-"
    mode = current_fish_mode(primary_label)
    group_line = f"Jumlah grup: {len(configured_group_chats(primary_label))}\nGrup aktif: {active_group_chat_target(primary_label) or '-'}\n" if mode in {"group_room", "all"} else ""
    group_count = _account_group_sessions_done.get(primary_label, 0)
    group_active = "ya" if _account_group_active.get(primary_label) else "tidak"
    sell_lock = _account_sell_locks.get(primary_label)
    sell_state = "sedang bersih-bersih" if sell_lock and sell_lock.locked() else "tidak berjalan"

    if _shutdown_event.is_set():
        runtime_state = "sedang berhenti"
    elif sell_lock and sell_lock.locked():
        runtime_state = "sedang bersihkan inventory"
    elif mode == "group_room" and is_any_running():
        runtime_state = "menunggu room grup atau hasil sesi"
    elif mode == "all" and is_any_running():
        runtime_state = "prioritas grup, lalu private kalau tidak ada room"
    elif is_any_running():
        runtime_state = "mancing private"
    else:
        runtime_state = "berhenti"

    return (
        "📊 Status Detail\n\n"
        f"Auto mancing: {status}\n"
        f"Mode mancing: {mode_display_name(mode)}\n"
        f"Jam WIB: {now_wib().strftime('%H:%M')}\n"
        f"Kondisi: {runtime_state}\n"
        f"Akun yang jalan: {', '.join(account_names_for_labels(labels)) if labels else '-'}\n"
        f"{group_line}"
        f"Sesi grup selesai: {group_count}\n"
        f"Sesi grup sedang jalan: {group_active}\n"
        f"Bersihkan inventory: {sell_state}\n\n"
        f"Aksi terakhir: {_account_last_action.get(primary_label, '-')}\n"
        f"Kabar terakhir: {_account_last_event.get(primary_label, '-')}\n"
        f"Jual terakhir: {_account_last_sell.get(primary_label, '-')}\n"
        f"Terakhir aktif: {last_seen}\n\n"
        f"Sesi selesai: {stats['sessions_done']}\n"
        f"Inventory full: {stats['inventory_full']}\n"
        f"Sell sukses: {stats['sell_success']}\n"
        f"Verifikasi berhasil/gagal: {stats['captcha_solved']}/{stats['captcha_failed']}"
    )


def format_mode_text(label: str = None) -> str:
    label = ctx_label(label)
    mode = current_fish_mode(label)
    labels = {
        "private": "Private",
        "group_room": "Group",
        "all": "All / Hybrid",
        "special_group": "Grup Khusus",
    }
    return (
        "🔁 Mode Mancing\n\n"
        f"Nama: {account_name_for_label(label)}\n"
        f"Mode saat ini: {labels.get(mode, mode)}\n\n"
        "Private: hanya /mancing private, grup diabaikan.\n"
        "Group: hanya daftar room grup, tidak kirim /mancing private.\n"
        f"All: tunggu room grup {ALL_MODE_GROUP_WAIT}s; kalau tidak ada, jalan 1 sesi private.\n"
        "Grup Khusus: hanya pantau 1 grup khusus, daftar room di sana, dan bisa open room otomatis."
    )


def format_groups_text(label: str = None) -> str:
    label = ctx_label(label)
    all_groups = configured_group_chats(label)
    active = active_group_chat_target(label)
    lines = "\n".join(f"• {group}" for group in all_groups) or "Belum ada."
    body = (
        f"Total: {len(all_groups)}\n"
        f"Active group: {active or '-'}\n\n"
        f"{lines}"
    )
    return "🎣 <b>Groups Mancing</b>\n\n" + expandable_blockquote(body)


def format_special_group_text(label: str = None) -> str:
    label = ctx_label(label)
    target = load_special_group_chat(label)
    active = active_group_chat_target(label)
    delay_min, delay_max = special_open_delay_range(label)
    auto_text = (
        f"Setelah sesi selesai, bot menunggu {delay_min:.0f}-{delay_max:.0f}s. "
        "Kalau tidak ada room baru, salah satu userbot aktif di grup yang sama akan kirim open room."
        if special_auto_open_enabled(label)
        else "Auto open sedang OFF. Bot tetap daftar room yang muncul, tapi tidak membuka room otomatis."
    )
    body = (
        f"Nama: {account_name_for_label(label)}\n"
        f"Grup khusus: {target or 'Belum diset'}\n"
        f"Auto open: {'ON' if special_auto_open_enabled(label) else 'OFF'}\n"
        f"Auto boost: {'ON' if special_auto_boost_enabled(label) else 'OFF'}\n"
        f"Waktu tunggu: {delay_min:.0f}-{delay_max:.0f}s\n"
        f"Active group: {active or '-'}\n\n"
        "Mode Grup Khusus hanya memantau grup ini. Bot akan daftar room yang muncul di grup ini saja.\n"
        f"{auto_text}"
    )
    return "🎯 <b>Grup Khusus</b>\n\n" + expandable_blockquote(body)


def format_stats_text(label: str = None) -> str:
    label = ctx_label(label)
    stats = load_stats(label)
    inactive = seconds_since_activity(label)
    last_seen = f"{inactive}s lalu" if inactive is not None else "-"
    body = (
        f"Nama: {account_name_for_label(label)}\n"
        f"Akun yang jalan: {', '.join(account_names_for_labels(running_labels())) or '-'}\n"
        f"/mancing terkirim: {stats['mancing_sent']}\n"
        f"Sesi selesai: {stats['sessions_done']}\n"
        f"Inventory penuh: {stats['inventory_full']}\n"
        f"Jual sukses: {stats['sell_success']}\n"
        f"Verifikasi berhasil: {stats['captcha_solved']}\n"
        f"Verifikasi gagal: {stats['captcha_failed']}\n"
        f"Cek otomatis: {stats['watchdog_pokes']}\n\n"
        f"Aksi terakhir: {_account_last_action.get(label, '-')}\n"
        f"Kabar terakhir: {_account_last_event.get(label, '-')}\n"
        f"Jual terakhir: {_account_last_sell.get(label, '-')}\n"
        f"Terakhir aktif: {last_seen}"
    )
    return "📈 <b>Fish Bot Stats</b>\n\n" + expandable_blockquote(body)


def format_rules_text(label: str = None) -> str:
    label = ctx_label(label)
    rules = load_fish_rules(label)
    poseidon_status = "ON" if poseidon_favorite_enabled(label) else "OFF"
    body = (
        "Proteksi global: Secret, Secret Shiny, Celestial, Artefak, Artifact selalu disimpan.\n"
        f"Trisula Poseidon favorite: {poseidon_status}.\n\n"
        f"Keep list: {len(rules['keep'])}\n"
        f"Sell list: {len(rules['sell'])}\n\n"
        "Pilih daftar yang mau dilihat atau diubah."
    )
    return "❤️ <b>Rules Ikan</b>\n\n" + expandable_blockquote(body)


def format_rule_list_text(label: str, kind: str) -> str:
    rules = load_fish_rules(label)
    title = "✅ List Keep" if kind == "keep" else "🚫 List Sell"
    desc = "Item yang selalu disimpan:" if kind == "keep" else "Item yang selalu dijual:"
    values = "\n".join(f"• {x}" for x in rules[kind]) or "Belum ada."
    return f"<b>{title}</b>\n\n" + expandable_blockquote(f"{desc}\n{values}")


def format_all_rules_text(label: str = None) -> str:
    label = ctx_label(label)
    rules = load_fish_rules(label)
    keep = "\n".join(f"• {x}" for x in rules["keep"]) or "Belum ada."
    sell = "\n".join(f"• {x}" for x in rules["sell"]) or "Belum ada."
    protection = "\n".join([
        "• Secret",
        "• Secret Shiny",
        "• Celestial",
        "• Artefak",
        "• Artifact",
        f"• Trisula Poseidon: {'Favorite' if poseidon_favorite_enabled(label) else 'Jual'}",
    ])
    return (
        "📋 <b>List Rules</b>\n\n"
        "<b>✅ Keep</b>\n"
        f"{expandable_blockquote(keep)}\n\n"
        "<b>🚫 Sell</b>\n"
        f"{expandable_blockquote(sell)}\n\n"
        "<b>🛡 Proteksi Global</b>\n"
        f"{expandable_blockquote(protection)}"
    )


def format_help_html() -> str:
    return (
        "<b>❔ Help Fish Bot</b>\n\n"
        "<blockquote expandable>"
        "Bot ini menjalankan Fish It otomatis dari akun Telegram kamu.\n\n"
        "Cara kerja utama:\n"
        "1. Login Userbot sekali lewat Settings.\n"
        "2. Pilih Mode Mancing.\n"
        "3. Klik Start.\n"
        "4. Bot akan mancing otomatis sesuai mode yang dipilih.\n"
        "5. Kalau inventory penuh, bot otomatis membaca semua halaman inventory.\n"
        "6. Bot otomatis memilih item penting untuk disimpan.\n"
        "7. Item penting akan dimasukkan ke Favorite dulu.\n"
        "8. Setelah Favorite sukses, bot otomatis menjual ikan/item sisanya.\n"
        "9. Kalau Favorite gagal, Favorite penuh, atau inventory gagal dibaca, bot tidak lanjut jual demi keamanan.\n"
        "10. Kalau ada verifikasi tombol, bot akan pause akun itu dan minta kamu selesaikan verifikasi manual dari chat Fish It.\n"
        "11. Klik Stop untuk menghentikan auto mancing tanpa logout dan tanpa menghapus session.\n\n"
        "Kamu tidak perlu pencet Bersihkan Inventory saat auto mancing jalan. Tombol Bersihkan hanya untuk membersihkan manual.\n\n"
        "Pilih topik di bawah untuk penjelasan detail."
        "</blockquote>"
    )


def format_help_topic_html(topic: str) -> str:
    topics = {
        "login": (
            "🔐 <b>Help: Login Userbot</b>",
            "Login Userbot menghubungkan akun Telegram kamu ke bot.\n\n"
            "Yang perlu disiapkan:\n"
            "• nomor HP akun Telegram\n"
            "• kode OTP dari Telegram\n"
            "• password 2FA kalau aktif\n\n"
            "Login cukup dilakukan sekali. Setelah berhasil, bot bisa menjalankan Fish It dari akun kamu. "
            "Stop auto mancing tidak menghapus session dan tidak logout."
        ),
        "fishing": (
            "🎣 <b>Help: Start / Stop</b>",
            "Start menjalankan auto mancing untuk akun yang sedang dipilih.\n\n"
            "Saat Start:\n"
            "• bot berjalan sesuai Mode Mancing\n"
            "• inventory penuh akan dibersihkan otomatis\n"
            "• kalau muncul verifikasi, akun akan dipause dan panel akan minta konfirmasi manual\n\n"
            "Stop menghentikan auto mancing akun itu. Stop tidak logout, tidak hapus session, dan akun bisa dijalankan lagi dengan Start."
        ),
        "mode": (
            "🔁 <b>Help: Mode Mancing</b>",
            "Mode menentukan cara bot mancing.\n\n"
            "Private: bot fokus mancing private.\n"
            "Group: bot hanya menunggu dan daftar room grup.\n"
            "All / Hybrid: bot prioritaskan room grup, lalu private kalau tidak ada room.\n"
            "Grup Khusus: bot hanya fokus ke satu grup khusus yang kamu set."
        ),
        "inventory": (
            "🟥 <b>Help: Inventory & Jual</b>",
            "Saat inventory penuh, bot akan otomatis membaca inventory, memilih item penting, memasukkannya ke Favorite, lalu menjual sisanya.\n\n"
            "Preview Filter: cek item yang akan disimpan.\n"
            "Bersihkan: menjalankan proses bersih inventory secara manual.\n"
            "History Fav: melihat item penting yang pernah difavorite.\n\n"
            "Bot tidak lanjut jual kalau inventory gagal dibaca, Favorite penuh, atau Favorite belum terkonfirmasi sukses."
        ),
        "rules": (
            "❤️ <b>Help: Rules & Proteksi</b>",
            "Rules membantu menentukan item yang harus disimpan.\n\n"
            "Keep List: nama ikan/item yang selalu disimpan.\n"
            "Sell List: nama ikan/item yang tidak perlu disimpan.\n\n"
            "Proteksi global selalu menang. Rarity Secret, Secret Shiny, Celestial, Artefak, dan Artifact tetap disimpan untuk semua user.\n"
            "Khusus Trisula Poseidon bisa diubah dari menu Inventory."
        ),
        "special": (
            "🎯 <b>Help: Grup Khusus</b>",
            "Grup Khusus dipakai kalau kamu ingin bot fokus ke satu grup tertentu.\n\n"
            "Saat mode ini aktif:\n"
            "• bot hanya pantau grup khusus itu\n"
            "• bot daftar room yang muncul di grup itu\n"
            "• Auto Open bisa membuka room otomatis kalau tidak ada room baru\n"
            "• Auto Boost bisa membantu boost grup\n\n"
            "Kalau akun tidak bisa kirim pesan ke grup, akun itu akan diskip dari tugas open/boost."
        ),
        "monitoring": (
            "📊 <b>Help: Monitoring</b>",
            "Monitoring dipakai untuk melihat kondisi akun.\n\n"
            "Yang bisa dicek:\n"
            "• login userbot\n"
            "• status auto mancing\n"
            "• mode mancing\n"
            "• inventory terakhir\n"
            "• kabar terakhir\n"
            "• aktivitas terakhir\n\n"
            "Kalau akun terlihat berhenti, cek login userbot lalu klik Start lagi."
        ),
    }
    title, body = topics.get(topic, ("❔ <b>Help</b>", "Topik bantuan tidak ditemukan."))
    return f"{title}\n\n" + expandable_blockquote(body)


