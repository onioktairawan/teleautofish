from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


async def resolve_user_targets(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_args: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
    targets: list[tuple[int, str]] = []
    errors: list[str] = []
    seen: set[int] = set()

    replied_user = update.message.reply_to_message.from_user if update.message and update.message.reply_to_message else None
    if replied_user:
        seen.add(int(replied_user.id))
        label = replied_user.username or replied_user.full_name or str(replied_user.id)
        targets.append((int(replied_user.id), label))

    for raw in raw_args:
        value = (raw or "").strip()
        if not value:
            continue
        if value.startswith("@"):
            value = value[1:]

        user_id: int | None = None
        label = value
        if re.fullmatch(r"\d{5,20}", value):
            user_id = int(value)
            label = "User"
        else:
            try:
                chat = await context.bot.get_chat(value)
                user_id = int(chat.id)
                label = getattr(chat, "username", None) or getattr(chat, "full_name", None) or value
            except Exception as e:
                errors.append(f"{raw}: gagal resolve username ({e})")
                continue

        if user_id in seen:
            continue
        seen.add(user_id)
        targets.append((user_id, label))

    return targets, errors


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, raw_args: list[str]):
    user_id = int(update.effective_user.id)
    if not can_manage_admins(user_id):
        await update.message.reply_text("⛔ Hanya owner utama yang bisa mengelola premium.")
        return

    targets, errors = await resolve_user_targets(update, context, raw_args)
    if not targets:
        usage = f"/{action} reply user atau username.\nContoh: /{action} @username"
        if errors:
            usage += "\n\n" + "\n".join(errors[:5])
        await update.message.reply_text(usage, reply_markup=back_keyboard("owner:users"))
        return

    lines = []
    if action == "addprem":
        for target_id, label in targets:
            if target_id == OWNER_ID:
                lines.append(f"• {label}: owner utama sudah punya akses.")
                continue
            added = add_admin_id(target_id)
            state = "ditambahkan" if added else "sudah ada"
            lines.append(f"• {label}: {state}.")
        await update.message.reply_text(
            "✅ Add premium selesai.\n\n"
            + "\n".join(lines)
            + f"\n\nTotal premium/admin: {len(load_admin_ids())}",
            reply_markup=back_keyboard("owner:users"),
        )
        return

    if action == "rmprem":
        for target_id, label in targets:
            if target_id == OWNER_ID:
                lines.append(f"• {label}: owner utama tidak bisa dihapus.")
                continue
            removed_admin = remove_admin_id(target_id)
            cleanup = await remove_user_sessions(target_id)
            lines.append(
                f"• {label}: "
                f"premium {'dihapus' if removed_admin else 'tidak ada'}, "
                f"DB {cleanup['db_deleted']}, file {cleanup['files_deleted']}."
            )
        await update.message.reply_text(
            "🗑 Remove premium selesai.\n\n"
            + "\n".join(lines)
            + f"\n\nTotal premium/admin: {len(load_admin_ids())}",
            reply_markup=back_keyboard("owner:users"),
        )


async def resolve_userbot_premium_targets(client: Client, message, raw_args: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
    targets: list[tuple[int, str]] = []
    errors: list[str] = []
    seen: set[int] = set()

    replied = getattr(message, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None) if replied else None
    if replied_user:
        seen.add(int(replied_user.id))
        label = replied_user.username or replied_user.first_name or str(replied_user.id)
        targets.append((int(replied_user.id), label))

    for raw in raw_args:
        value = (raw or "").strip().strip(",;")
        if not value:
            continue
        lookup = value[1:] if value.startswith("@") else value

        if re.fullmatch(r"\d{5,20}", lookup):
            user_id = int(lookup)
            if user_id in seen:
                continue
            seen.add(user_id)
            targets.append((user_id, "User"))
            continue

        try:
            user = await client.get_users(lookup)
        except Exception as e:
            errors.append(f"{value}: gagal resolve ({e})")
            continue

        user_id = int(user.id)
        if user_id in seen:
            continue
        seen.add(user_id)
        label = user.username or user.first_name or str(user_id)
        targets.append((user_id, label))

    return targets, errors


async def handle_userbot_premium_command(client: Client, message, action: str, raw_args: list[str]):
    targets, errors = await resolve_userbot_premium_targets(client, message, raw_args)
    if not targets:
        usage = f"Pakai: `{action}` sambil reply user, atau `{action} username`."
        if errors:
            usage += "\n\n" + "\n".join(errors[:5])
        await message.reply_text(usage)
        return

    lines = []
    if action == "addprem":
        added_targets = []
        for target_id, label in targets:
            if target_id == OWNER_ID:
                added_targets.append(label)
                continue
            added = add_admin_id(target_id)
            audit_log(default_user_account_label(target_id), "addprem", f"{label} ({target_id})", user_id=OWNER_ID)
            if added:
                added_targets.append(label)
            else:
                added_targets.append(label)
        target_text = ", ".join(added_targets)
        await message.reply_text(f"User {target_text} berhasil ditambahkan, langsung pergi ke @logserpaidbot untuk aktifkan.")
        return

    if action == "rmprem":
        for target_id, label in targets:
            if target_id == OWNER_ID:
                lines.append(f"• {label}: owner utama tidak bisa dihapus.")
                continue
            removed_admin = remove_admin_id(target_id)
            cleanup = await remove_user_sessions(target_id)
            audit_log(default_user_account_label(target_id), "rmprem", f"{label} ({target_id})", user_id=OWNER_ID)
            lines.append(
                f"• {label}: "
                f"premium {'dihapus' if removed_admin else 'tidak ada'}, "
                f"DB {cleanup['db_deleted']}, file {cleanup['files_deleted']}."
            )
        await message.reply_text(
            "🗑 Remove premium selesai.\n\n"
            + "\n".join(lines)
            + f"\n\nTotal premium/admin: {len(load_admin_ids())}"
        )


async def userbot_premium_command(client, message):
    text = (message.text or "").strip()
    parts = re.split(r"[\s,;|]+", text)
    action = parts[0].casefold()
    await handle_userbot_premium_command(client, message, action, parts[1:])


async def userbot_restart_command(client, message):
    await request_userbot_restart(message)


