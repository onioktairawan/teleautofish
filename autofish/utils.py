import json
import re
from datetime import datetime
from pathlib import Path

from .config import WIB
from .logging_utils import Log


def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def load_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        Log.p("WARN", f"Gagal baca {path.name}: {e}")
        return default


def format_wib_time(value) -> str:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=WIB)
        return dt.astimezone(WIB).strftime("%d/%m %H:%M WIB")
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=WIB)
        return dt.astimezone(WIB).strftime("%d/%m %H:%M WIB")
    except ValueError:
        return text[:16]


def parse_chat_target(chat: str):
    chat = (chat or "").strip()
    if re.fullmatch(r"-?\d+", chat):
        return int(chat)
    return chat


def split_chat_targets(text: str) -> list[str]:
    targets = []
    seen = set()
    for raw in re.split(r"[\s,;|]+", text or ""):
        target = raw.strip()
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets
