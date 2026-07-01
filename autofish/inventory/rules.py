from __future__ import annotations


def bind_runtime(namespace: dict):
    globals().update(namespace)


def load_fish_rules(label: str = None) -> dict[str, list[str]]:
    label = ctx_label(label)
    default = {"keep": [], "sell": []}
    doc = db_get_doc("rules", label)
    if doc:
        keep = sorted({normalize_fish_name(x) for x in doc.get("keep", []) if normalize_fish_name(x)})
        sell = sorted({normalize_fish_name(x) for x in doc.get("sell", []) if normalize_fish_name(x)})
        return {"keep": keep, "sell": sell}
    if not RULES_FILE.exists():
        return default

    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        keep = sorted({normalize_fish_name(x) for x in data.get("keep", []) if normalize_fish_name(x)})
        sell = sorted({normalize_fish_name(x) for x in data.get("sell", []) if normalize_fish_name(x)})
        return {"keep": keep, "sell": sell}
    except Exception as e:
        Log.p("WARN", f"Gagal baca fish_rules.json: {e}")
        return default


def save_fish_rules(rules: dict[str, list[str]], label: str = None):
    label = ctx_label(label)
    cleaned = {
        "keep": sorted({normalize_fish_name(x) for x in rules.get("keep", []) if normalize_fish_name(x)}),
        "sell": sorted({normalize_fish_name(x) for x in rules.get("sell", []) if normalize_fish_name(x)}),
    }
    if mongo_enabled():
        db_upsert_doc("rules", label, cleaned)
        return
    RULES_FILE.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")


def update_fish_rule(kind: str, name: str, add: bool, label: str = None) -> tuple[bool, str]:
    label = ctx_label(label)
    normalized = normalize_fish_name(name)
    if not normalized:
        return False, "Nama ikan kosong."

    rules = load_fish_rules(label)
    other = "sell" if kind == "keep" else "keep"

    if add:
        rules[other] = [x for x in rules[other] if x != normalized]
        if normalized not in rules[kind]:
            rules[kind].append(normalized)
        save_fish_rules(rules, label)
        label = "selalu disimpan" if kind == "keep" else "selalu dijual"
        return True, f"`{normalized}` ditambahkan ke daftar {label}."

    if normalized not in rules[kind]:
        return False, f"`{normalized}` tidak ada di daftar."

    rules[kind] = [x for x in rules[kind] if x != normalized]
    save_fish_rules(rules, label)
    return True, f"`{normalized}` dihapus dari daftar."


def update_fish_rules_batch(kind: str, names: list[str], add: bool, label: str = None) -> tuple[int, list[str]]:
    results = []
    success = 0
    for name in names:
        ok, msg = update_fish_rule(kind, name, add, label=label)
        if ok:
            success += 1
        results.append(msg)
    return success, results


def parse_inventory_items(raw_inventory: str) -> list[dict]:
    items = []
    pattern = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$", re.M)
    matches = list(pattern.finditer(raw_inventory or ""))
    for index, match in enumerate(matches):
        number = int(match.group(1))
        name = re.sub(r"^[^\w\d]+", "", match.group(2), flags=re.UNICODE).strip()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_inventory or "")
        item_text = (raw_inventory or "")[match.start():block_end].strip()
        items.append({
            "number": number,
            "name": name,
            "normalized": normalize_fish_name(name),
            "text": item_text,
            "span": (match.start(), block_end),
        })
    return items


def inventory_page_sections(raw_inventory: str) -> list[dict]:
    raw_inventory = raw_inventory or ""
    pattern = re.compile(r"^---\s*Halaman\s+(\d+)\s*/\s*(\d+)\s*---\s*$", re.M)
    matches = list(pattern.finditer(raw_inventory))
    if not matches:
        page_number, total_pages = parse_inventory_page_info(raw_inventory)
        return [{
            "page": page_number,
            "total_pages": total_pages,
            "text": raw_inventory,
            "items": parse_inventory_items(raw_inventory),
        }]

    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_inventory)
        text = raw_inventory[start:end].strip()
        sections.append({
            "page": int(match.group(1)),
            "total_pages": int(match.group(2)),
            "text": text,
            "items": parse_inventory_items(text),
        })
    return sections


def validate_inventory_snapshot(raw_inventory: str, slots_used: int, slots_total: int, label: str = "main") -> tuple[bool, str, dict]:
    label = ctx_label(label)
    slots_used = int(slots_used or 0)
    slots_total = int(slots_total or 0)
    items = parse_inventory_items(raw_inventory)
    parsed_count = len(items)
    summary = {
        "slots_used": slots_used,
        "slots_total": slots_total,
        "parsed_count": parsed_count,
        "pages": [],
        "missing": [],
        "duplicates": [],
    }

    if slots_used <= 0:
        return False, "Slot terisi tidak terbaca.", summary
    if parsed_count != slots_used:
        return False, f"Jumlah item terbaca tidak cocok: parsed={parsed_count}, slot={slots_used}.", summary

    numbers = [item["number"] for item in items]
    duplicate_numbers = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicate_numbers:
        summary["duplicates"] = duplicate_numbers
        return False, f"Nomor inventory duplikat: {duplicate_numbers[:20]}.", summary

    expected_numbers = set(range(1, slots_used + 1))
    actual_numbers = set(numbers)
    missing = sorted(expected_numbers - actual_numbers)
    extra = sorted(actual_numbers - expected_numbers)
    summary["missing"] = missing
    if missing or extra:
        detail = []
        if missing:
            detail.append(f"hilang={missing[:20]}")
        if extra:
            detail.append(f"di luar range={extra[:20]}")
        return False, "Nomor inventory tidak lengkap: " + ", ".join(detail), summary

    expected_pages = max(1, (slots_used + 19) // 20)
    sections = inventory_page_sections(raw_inventory)
    page_numbers = [section["page"] for section in sections]
    summary["pages"] = page_numbers
    if sorted(page_numbers) != list(range(1, expected_pages + 1)):
        return False, f"Halaman inventory tidak lengkap: terbaca={sorted(page_numbers)}, expected=1..{expected_pages}.", summary

    declared_totals = {section["total_pages"] for section in sections if section["total_pages"]}
    if declared_totals and declared_totals != {expected_pages}:
        return False, f"Total halaman tidak cocok: declared={sorted(declared_totals)}, expected={expected_pages}.", summary

    for section in sections:
        page = section["page"]
        page_items = section["items"]
        expected_start = (page - 1) * 20 + 1
        expected_end = min(page * 20, slots_used)
        expected_page_numbers = list(range(expected_start, expected_end + 1))
        actual_page_numbers = [item["number"] for item in page_items]
        if actual_page_numbers != expected_page_numbers:
            return (
                False,
                f"Nomor halaman {page} tidak cocok: actual={actual_page_numbers[:25]}, expected={expected_start}..{expected_end}.",
                summary,
            )

    Log.p("INV", f"[{label}] Snapshot inventory valid: slot={slots_used}/{slots_total}, pages={expected_pages}, items={parsed_count}")
    return True, "OK", summary


def name_matches_rule(name: str, rules: list[str]) -> bool:
    normalized = normalize_fish_name(name)
    return any(rule and (rule in normalized or normalized in rule) for rule in rules)


def is_poseidon_trident_item(text: str) -> bool:
    tl = normalize_fish_name(text)
    return "trisula poseidon" in tl


def should_sell_poseidon_trident(text: str, label: str = None) -> bool:
    return is_poseidon_trident_item(text) and not poseidon_favorite_enabled(label)


def is_never_sell_item(text: str, label: str = None) -> bool:
    tl = normalize_fish_name(text)
    if should_sell_poseidon_trident(tl, label=label):
        return False
    return any(keyword in tl for keyword in NEVER_SELL_KEYWORDS)


def has_known_inventory_rarity(text: str) -> bool:
    tl = normalize_fish_name(text)
    return any(re.search(rf"\b{re.escape(keyword)}\b", tl) for keyword in KNOWN_RARITY_KEYWORDS)


def has_inventory_rarity_marker(text: str) -> bool:
    tl = normalize_fish_name(text)
    return any(marker in tl for marker in ["rarity", "kelangkaan", "rare", "jenis"])


def is_always_sell_item(text: str, label: str = None) -> bool:
    tl = normalize_fish_name(text)
    return not is_never_sell_item(tl, label=label) and any(keyword in tl for keyword in ALWAYS_SELL_KEYWORDS)


def infer_item_policy(text: str, label: str = None) -> str | None:
    if is_never_sell_item(text, label=label):
        return "keep"
    if is_always_sell_item(text, label=label):
        return "sell"
    return None


def local_filter_inventory(raw_inventory: str, label: str = "main") -> tuple[list[int], int]:
    rules = load_fish_rules(label)
    save_numbers: set[int] = set()
    keep_added = []
    sell_removed = []
    poseidon_removed = []
    protected_added = []
    unknown_rarity_added = []
    items = parse_inventory_items(raw_inventory)

    for item in items:
        number = item["number"]
        name = item["normalized"]
        item_text = item.get("text") or name
        never_sell = is_never_sell_item(item_text, label=label)
        always_sell = is_always_sell_item(item_text, label=label)

        if never_sell:
            save_numbers.add(number)
            protected_added.append(number)
        elif always_sell:
            save_numbers.discard(number)

        if name_matches_rule(name, rules["keep"]) and not always_sell:
            save_numbers.add(number)
            keep_added.append(number)

        if (
            not never_sell
            and not always_sell
            and has_inventory_rarity_marker(item_text)
            and not has_known_inventory_rarity(item_text)
        ):
            save_numbers.add(number)
            unknown_rarity_added.append(number)

        if name_matches_rule(name, rules["sell"]) and not never_sell:
            if number in save_numbers:
                sell_removed.append(number)
            save_numbers.discard(number)

        if should_sell_poseidon_trident(item_text, label=label):
            if number in save_numbers:
                poseidon_removed.append(number)
            save_numbers.discard(number)

    Log.p(
        "SELL",
        f"[{label}] Local filter: items={len(items)}, protected={protected_added}, keep={keep_added}, unknown_rarity={unknown_rarity_added}, sell_remove={sell_removed}, poseidon_sell={poseidon_removed}, save={sorted(save_numbers)}",
    )
    return sorted(save_numbers), len(items)


def protected_inventory_items(raw_inventory: str, label: str = "main") -> list[dict]:
    label = ctx_label(label)
    protected = []
    for item in parse_inventory_items(raw_inventory):
        item_text = item.get("text") or item.get("name", "")
        if is_never_sell_item(item_text, label=label):
            protected.append(item)
    return protected


def validate_protected_save_list(raw_inventory: str, save_list: list[int], label: str = "main") -> tuple[bool, str, list[dict]]:
    protected = protected_inventory_items(raw_inventory, label=label)
    protected_numbers = {item["number"] for item in protected}
    missing = sorted(protected_numbers - set(save_list))
    if missing:
        names = ", ".join(f"#{item['number']} {item['name']}" for item in protected if item["number"] in missing)
        return False, f"Item protected belum masuk favorite target: {names}", protected
    return True, "OK", protected


def find_rare_catch_items(save_list: list[int], raw_inventory: str) -> list[dict]:
    save_numbers = set(save_list)
    rare_items = []

    for item in parse_inventory_items(raw_inventory):
        number = item["number"]
        if number not in save_numbers:
            continue

        item_text = item.get("text") or item["name"]
        tl = normalize_fish_name(item_text)
        matched_keyword = next((keyword for keyword in RARE_CATCH_NOTIFY_KEYWORDS if keyword in tl), None)
        if not matched_keyword:
            continue

        rare_items.append({
            "number": number,
            "name": item["name"],
            "keyword": matched_keyword,
            "text": item_text.replace("\n", " ")[:160],
        })

    return rare_items


def favorite_history_items(save_list: list[int], raw_inventory: str, label: str = "main") -> list[dict]:
    save_numbers = set(save_list)
    rules = load_fish_rules(label)
    items = []

    for item in parse_inventory_items(raw_inventory):
        number = item["number"]
        if number not in save_numbers:
            continue
        item_text = item.get("text") or item["name"]
        normalized = item["normalized"]
        if is_never_sell_item(item_text, label=label):
            reason = "proteksi Trisula Poseidon" if is_poseidon_trident_item(item_text) else "proteksi global"
        elif name_matches_rule(normalized, rules.get("keep", [])):
            reason = "keep rules"
        elif has_inventory_rarity_marker(item_text) and not has_known_inventory_rarity(item_text):
            reason = "rarity tidak dikenal"
        else:
            reason = "filter lokal"
        items.append({
            "number": number,
            "name": item["name"],
            "reason": reason,
            "text": item_text.replace("\n", " ")[:180],
        })

    return items


def load_rare_gallery(label: str = None, limit: int = 20) -> list[dict]:
    label = ctx_label(label)
    limit = max(1, min(100, int(limit or 20)))
    if mongo_enabled():
        try:
            return list(
                mongo_col.find({"type": "rare_gallery", "label": label})
                .sort("created_at", -1)
                .limit(limit)
            )
        except PyMongoError as e:
            Log.p("WARN", f"Mongo rare gallery gagal: {e}")
            return []

    data = load_json_file(RARE_GALLERY_FILE, {"items": []})
    rows = [item for item in data.get("items", []) if item.get("label") == label]
    return rows[-limit:][::-1]


def save_favorite_gallery(items: list[dict], label: str = "main"):
    if not items:
        return
    label = ctx_label(label)
    now = now_wib()
    account = load_account(label)
    owner_id = account_primary_owner_id(account)
    docs = []
    for item in items:
        docs.append({
            "type": "rare_gallery",
            "label": label,
            "owner_id": owner_id,
            "number": int(item.get("number", 0) or 0),
            "name": str(item.get("name", "-")),
            "reason": str(item.get("reason", "-")),
            "text": str(item.get("text", ""))[:180],
            "created_at": now,
        })

    if mongo_enabled():
        try:
            if docs:
                mongo_col.insert_many(docs)
            old_docs = list(
                mongo_col.find({"type": "rare_gallery", "label": label}, {"_id": 1})
                .sort("created_at", -1)
                .skip(RARE_GALLERY_LIMIT)
            )
            old_ids = [doc["_id"] for doc in old_docs]
            if old_ids:
                mongo_col.delete_many({"_id": {"$in": old_ids}})
        except PyMongoError as e:
            Log.p("WARN", f"Mongo simpan rare gallery gagal: {e}")
        return

    data = load_json_file(RARE_GALLERY_FILE, {"items": []})
    all_items = data.get("items", [])
    all_items.extend(json_safe(docs))
    per_label = [item for item in all_items if item.get("label") == label][-RARE_GALLERY_LIMIT:]
    others = [item for item in all_items if item.get("label") != label]
    RARE_GALLERY_FILE.write_text(
        json.dumps({"items": others + per_label}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def notify_rare_catches(rare_items: list[dict], label: str = "main"):
    if not rare_items:
        return

    lines = [
        f"• #{item['number']} {item['name']}"
        for item in rare_items[:15]
    ]
    if len(rare_items) > 15:
        lines.append(f"... dan {len(rare_items) - 15} item lagi")

    Log.p("NOTIF", f"[{label}] Rare catch terdeteksi: {', '.join(str(item['number']) for item in rare_items)}")
    await notify(
        f"🌟 [{label}] Rare catch masuk daftar simpan!\n\n"
        + "\n".join(lines)
        + "\n\nBot akan favorite item ini sebelum jual."
    )


def apply_fish_rules(save_list: list[int], raw_inventory: str, label: str = None) -> list[int]:
    rules = load_fish_rules(label)

    final = set(save_list)
    keep_added = []
    sell_removed = []
    poseidon_removed = []

    items = parse_inventory_items(raw_inventory)
    for index, item in enumerate(items):
        number = item["number"]
        name = item["normalized"]
        item_text = item.get("text") or name
        never_sell = is_never_sell_item(item_text, label=label)
        always_sell = is_always_sell_item(item_text, label=label)

        policy = "keep" if never_sell else ("sell" if always_sell else None)
        if policy == "keep":
            if number not in final:
                keep_added.append(number)
            final.add(number)
        elif policy == "sell" and always_sell:
            if number in final:
                sell_removed.append(number)
            final.discard(number)

        if name_matches_rule(name, rules["keep"]) and not always_sell:
            if number not in final:
                keep_added.append(number)
            final.add(number)
        if name_matches_rule(name, rules["sell"]) and not never_sell:
            if number in final:
                sell_removed.append(number)
            final.discard(number)

        if should_sell_poseidon_trident(item_text, label=label):
            if number in final:
                poseidon_removed.append(number)
            final.discard(number)

    if keep_added or sell_removed or poseidon_removed:
        Log.p("SELL", f"Rules apply: keep tambah={keep_added}, sell buang={sell_removed}, poseidon buang={poseidon_removed}")

    return sorted(final)


