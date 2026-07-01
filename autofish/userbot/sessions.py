from pathlib import Path

from autofish.config import BASE_DIR
from autofish.logging_utils import Log


def session_files_for_name(session_name: str) -> list[Path]:
    if not session_name:
        return []
    base = Path(session_name)
    if not base.is_absolute():
        base = BASE_DIR / base
    return [
        base.with_suffix(".session"),
        base.with_suffix(".session-journal"),
    ]


def remove_session_files(session_name: str) -> int:
    removed = 0
    for path in session_files_for_name(session_name):
        try:
            if path.exists() and path.is_file():
                path.unlink()
                removed += 1
        except Exception as e:
            Log.p("WARN", f"Gagal hapus session file {path}: {e}")
    return removed

