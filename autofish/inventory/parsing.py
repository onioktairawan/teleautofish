import re


def normalize_fish_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip().lower()
    return name


def split_rule_names(text: str) -> list[str]:
    raw_parts = re.split(r"[\n,;|]+", text or "")
    names: list[str] = []
    seen: set[str] = set()

    for part in raw_parts:
        cleaned = part.strip()
        cleaned = re.sub(r"^[\-\*\u2022]+\s*", "", cleaned)
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
        cleaned = cleaned.strip()
        normalized = normalize_fish_name(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(cleaned)

    return names


def extract_weight_kg(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*kg\b", text or "", re.I)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None

