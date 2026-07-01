from datetime import datetime

from .config import WIB


def now_wib() -> datetime:
    return datetime.now(WIB)


class Log:
    LEVELS = {
        "STARTUP": ("STARTUP", "\033[94m"),
        "FISH": ("FISH   ", "\033[96m"),
        "INV": ("INV    ", "\033[94m"),
        "AI": ("AI     ", "\033[96m"),
        "SELL": ("SELL   ", "\033[92m"),
        "NOTIF": ("NOTIF  ", "\033[92m"),
        "BOT": ("BOT    ", "\033[92m"),
        "WARN": ("WARN   ", "\033[93m"),
        "ERROR": ("ERROR  ", "\033[91m"),
        "SHUTDOWN": ("SHUTDWN", "\033[93m"),
    }

    @staticmethod
    def p(level: str, msg: str):
        label, color = Log.LEVELS.get(level, (level[:7].ljust(7), "\033[94m"))
        ts = now_wib().strftime("%H:%M:%S")
        print(f"\033[1m{color}[{ts}] [{label}]\033[0m  {msg}", flush=True)

