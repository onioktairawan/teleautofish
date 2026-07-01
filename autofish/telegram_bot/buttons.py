import re


def infer_button_style(text: str, callback_data: str = "", requested: str = "primary") -> str:
    label = (text or "").casefold()
    callback = (callback_data or "").casefold()

    danger_words = (
        "batal", "cancel", "stop", "hapus", "remove", "delete", "clear",
        "reset", "restart", "restore", "bersihkan", "clean",
    )
    success_words = (
        "setuju", "konfirmasi", "confirm", "oke", "ok", "yes",
        "sudah verifikasi", "verified", "done",
    )

    danger_callbacks = (
        ":stop", ":clear", ":cancel", ":reset", ":del", ":delete", ":remove",
        ":restore", ":restart",
    )

    if (
        any(word in label for word in danger_words)
        or any(token in callback for token in danger_callbacks)
        or callback.endswith(":off")
    ):
        return "danger"
    if re.search(r"(^|\s)off(\s|$)", label):
        return "danger"
    if any(word in label for word in success_words):
        return "success"
    return "primary"

