import re


def parse_hhmm(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{1,2}))?\s*", str(value or ""))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_maintenance_schedule_input(text: str) -> tuple[str, str] | None:
    matches = re.findall(r"\d{1,2}(?::\d{1,2})?", text or "")
    if len(matches) < 2:
        return None
    start = parse_hhmm(matches[0])
    end = parse_hhmm(matches[1])
    if not start or not end or start == end:
        return None
    return start, end

