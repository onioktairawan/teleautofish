from __future__ import annotations

import html
import random
import re

from telegram import Bot, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest

_TelegramInlineKeyboardMarkup = InlineKeyboardMarkup


def bind_runtime(namespace: dict):
    globals().update(namespace)


PREMIUM_EMOJI_IDS = {
    "🎣": "5343609421316521960",
    "👀": "5210956306952758910",
    "🙂": "5461117441612462242",
    "⚡️": "5456140674028019486",
    "☄️": "5224607267797606837",
    "🛍": "5229064374403998351",
    "⛔️": "5260293700088511294",
    "🚫": "5240241223632954241",
    "❗️": "5274099962655816924",
    "‼️": "5440660757194744323",
    "⁉️": "5314504236132747481",
    "❓": "5436113877181941026",
    "⚠️": "5447644880824181073",
    "🌐": "5447410659077661506",
    "🌏": "5298508644051072797",
    "💬": "5443038326535759644",
    "💭": "5467538555158943525",
    "📊": "5231200819986047254",
    "🔼": "5449683594425410231",
    "🔽": "5447183459602669338",
    "🕯": "5451882707875276247",
    "📈": "5244837092042750681",
    "📉": "5246762912428603768",
    "✔️": "5206607081334906820",
    "❌": "5210952531676504517",
    "🆒": "5222079954421818267",
    "🔔": "5458603043203327669",
    "🥸": "5391112412445288650",
    "🤡": "5269531045165816230",
    "🫦": "5395444514028529554",
    "❤️": "5318836994845973679",
    "📌": "5397782960512444700",
    "💵": "5409048419211682843",
    "💸": "5233326571099534068",
    "💱": "5402186569006210455",
    "▶️": "5264919878082509254",
    "🔴": "4926956800005112527",
    "🟢": "6267030057131184941",
    "🟡": "5021618274345943603",
    "🟥": "5472315641123851828",
    "➡️": "5416117059207572332",
    "🔥": "5424972470023104089",
    "💥": "5276032951342088188",
    "🎙": "5294339927318739359",
    "🎤": "5224736245665511429",
    "📣": "5424818078833715060",
    "🤫": "5431609822288033666",
    "👎": "5449875686837726134",
    "🗣️": "5460795800101594035",
    "🔍": "5231012545799666522",
    "🛡": "5251203410396458957",
    "🔗": "5271604874419647061",
    "🖥": "5282843764451195532",
    "©": "5323442290708985472",
    "ℹ️": "5334544901428229844",
    "👍": "5337080053119336309",
    "⏸": "5359543311897998264",
    "💯": "5341498088408234504",
    "🔄": "5116468787377341336",
    "🔝": "5415655814079723871",
    "🆕": "5382357040008021292",
    "🔜": "5440621591387980068",
    "📍": "5391032818111363540",
    "➕": "5397916757333654639",
    "💎": "5427168083074628963",
    "⭐️": "5438496463044752972",
    "✨": "5325547803936572038",
    "👑": "5467406098367521267",
    "🗑": "5445267414562389170",
    "🔖": "5222444124698853913",
    "✉️": "5253742260054409879",
    "🔒": "5296369303661067030",
    "😮": "5303479226882603449",
    "📎": "5305265301917549162",
    "⚙️": "5341715473882955310",
    "🎮": "5361741454685256344",
    "🔈": "5388632425314140043",
    "⌛": "5386367538735104399",
    "⬇️": "5406745015365943482",
    "☀️": "5402477260982731644",
    "🌧": "5399913388845322366",
    "🌛": "5449569374065152798",
    "❄️": "5449449325434266744",
    "🌈": "5409109841538994759",
    "💧": "5393512611968995988",
    "🗓": "5413879192267805083",
    "💡": "5422439311196834318",
    "🥇": "5440539497383087970",
    "🥈": "5447203607294265305",
    "🥉": "5453902265922376865",
    "🎵": "5463107823946717464",
    "🆓": "5406756500108501710",
    "✏️": "5395444784611480792",
    "🚨": "5395695537687123235",
    "🏠": "5416041192905265756",
    "🚩": "5460755126761312667",
    "🎉": "5461151367559141950",
}

PREMIUM_EMOJI_IDS.update({
    "‼": PREMIUM_EMOJI_IDS["‼️"],
    "⁉": PREMIUM_EMOJI_IDS["⁉️"],
    "▶": PREMIUM_EMOJI_IDS["▶️"],
    "☀": PREMIUM_EMOJI_IDS["☀️"],
    "☄": PREMIUM_EMOJI_IDS["☄️"],
    "⚙": PREMIUM_EMOJI_IDS["⚙️"],
    "⚠": PREMIUM_EMOJI_IDS["⚠️"],
    "⚡": PREMIUM_EMOJI_IDS["⚡️"],
    "⛔": PREMIUM_EMOJI_IDS["⛔️"],
    "✅": PREMIUM_EMOJI_IDS["✔️"],
    "✉": PREMIUM_EMOJI_IDS["✉️"],
    "✏": PREMIUM_EMOJI_IDS["✏️"],
    "✔": PREMIUM_EMOJI_IDS["✔️"],
    "❄": PREMIUM_EMOJI_IDS["❄️"],
    "❔": PREMIUM_EMOJI_IDS["❓"],
    "➡": PREMIUM_EMOJI_IDS["➡️"],
    "⬇": PREMIUM_EMOJI_IDS["⬇️"],
    "⭐": PREMIUM_EMOJI_IDS["⭐️"],
    "🗣": PREMIUM_EMOJI_IDS["🗣️"],
    "🌟": PREMIUM_EMOJI_IDS["⭐️"],
    "📦": PREMIUM_EMOJI_IDS["🟥"],
    "🔐": PREMIUM_EMOJI_IDS["🔒"],
    "🛠": PREMIUM_EMOJI_IDS["⚙️"],
    "🛑": PREMIUM_EMOJI_IDS["⛔️"],
    "⏭": PREMIUM_EMOJI_IDS["▶️"],
    "⏰": PREMIUM_EMOJI_IDS["⌛"],
    "⏱": PREMIUM_EMOJI_IDS["⌛"],
    "🎯": PREMIUM_EMOJI_IDS["🔍"],
    "🐞": PREMIUM_EMOJI_IDS["🚨"],
    "👤": PREMIUM_EMOJI_IDS["🥸"],
    "👥": PREMIUM_EMOJI_IDS["🥸"],
    "💾": PREMIUM_EMOJI_IDS["📎"],
    "📋": PREMIUM_EMOJI_IDS["📎"],
    "📩": PREMIUM_EMOJI_IDS["✉️"],
    "📱": PREMIUM_EMOJI_IDS["🖥"],
    "🔁": PREMIUM_EMOJI_IDS["🔄"],
    "🔱": PREMIUM_EMOJI_IDS["💎"],
    "🧹": PREMIUM_EMOJI_IDS["🗑"],
    "🧾": PREMIUM_EMOJI_IDS["📎"],
    "🩺": PREMIUM_EMOJI_IDS["ℹ️"],
    "🤖": PREMIUM_EMOJI_IDS["🙂"],
    "◀": PREMIUM_EMOJI_IDS["➡️"],
    "⬅": PREMIUM_EMOJI_IDS["➡️"],
    "♻": PREMIUM_EMOJI_IDS["🔄"],
    "⚪": PREMIUM_EMOJI_IDS["ℹ️"],
    "✍": PREMIUM_EMOJI_IDS["✏️"],
})

PREMIUM_EMOJI_RE = re.compile(
    "|".join(re.escape(emoji) for emoji in sorted(PREMIUM_EMOJI_IDS, key=len, reverse=True))
)
TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji\s+emoji-id="[^"]+">(.*?)</tg-emoji>', re.S)


def premium_emoji(emoji: str) -> str:
    emoji_id = PREMIUM_EMOJI_IDS.get(emoji)
    if not emoji_id:
        return emoji
    return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'


def premiumize_emoji_html(text: str) -> str:
    if not isinstance(text, str) or not text or "<tg-emoji" in text:
        return text
    return PREMIUM_EMOJI_RE.sub(lambda match: premium_emoji(match.group(0)), text)


def premiumize_emoji_plain(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    return premiumize_emoji_html(html.escape(text))


def main_premium_active() -> bool:
    if _main_premium_active is not None:
        return bool(_main_premium_active)
    account = load_account("main")
    tg_user = account.get("telegram_user") or {}
    return bool(tg_user.get("is_premium") or tg_user.get("premium"))


def telegram_user_premium_flag(user) -> bool:
    return bool(
        getattr(user, "is_premium", False)
        or getattr(user, "premium", False)
    )


def set_main_premium_status_from_user(user, label: str = "main"):
    global _main_premium_active, _main_premium_checked_at
    if ctx_label(label) != "main" or user is None:
        return
    active = telegram_user_premium_flag(user)
    _main_premium_active = active
    _main_premium_checked_at = now_wib()
    if mongo_enabled():
        db_upsert_doc("account", "main", {
            "telegram_user.is_premium": active,
            "telegram_user.premium_checked_at": _main_premium_checked_at,
        })
    Log.p("STARTUP", f"Premium main: {'aktif' if active else 'tidak aktif'}")


def _prepare_premium_text(args, kwargs, text_index: int, field: str = "text"):
    args = list(args)
    has_positional_text = len(args) > text_index
    text = args[text_index] if has_positional_text else kwargs.get(field)
    if not isinstance(text, str):
        return tuple(args), kwargs

    parse_mode = kwargs.get("parse_mode")
    if not main_premium_active():
        text = strip_custom_emoji_tags(text)
    elif isinstance(parse_mode, str) and parse_mode.upper() == "HTML":
        text = premiumize_emoji_html(text)
    elif parse_mode is None:
        text = premiumize_emoji_plain(text)
        kwargs["parse_mode"] = "HTML"
    else:
        return tuple(args), kwargs

    if has_positional_text:
        args[text_index] = text
    else:
        kwargs[field] = text
    return tuple(args), kwargs


def custom_emoji_icon_error(error: Exception) -> bool:
    msg = str(error).casefold()
    return (
        "icon_custom_emoji_id" in msg
        or "custom emoji" in msg
        or "custom_emoji" in msg
        or "emoji id" in msg
    )


def message_not_modified_error(error: Exception) -> bool:
    return "message is not modified" in str(error or "").casefold()


def strip_button_custom_emoji_icons(markup):
    if not markup:
        return markup
    try:
        data = markup.to_dict()
    except Exception:
        return markup

    changed = False
    if "inline_keyboard" in data:
        for row in data.get("inline_keyboard") or []:
            for button in row or []:
                if button.pop("icon_custom_emoji_id", None) is not None:
                    changed = True
        return _TelegramInlineKeyboardMarkup.de_json(data, None) if changed else markup

    if "keyboard" in data:
        for row in data.get("keyboard") or []:
            for button in row or []:
                if isinstance(button, dict) and button.pop("icon_custom_emoji_id", None) is not None:
                    changed = True
        return ReplyKeyboardMarkup.de_json(data, None) if changed else markup

    return markup


def strip_reply_markup_custom_emoji_icons(kwargs: dict) -> bool:
    if "reply_markup" not in kwargs:
        return False
    stripped = strip_button_custom_emoji_icons(kwargs.get("reply_markup"))
    if stripped is kwargs.get("reply_markup"):
        return False
    kwargs["reply_markup"] = stripped
    return True


def strip_custom_emoji_tags(text: str) -> str:
    if not isinstance(text, str) or "<tg-emoji" not in text:
        return text
    return TG_EMOJI_TAG_RE.sub(lambda match: match.group(1), text)


def strip_custom_emoji_text(args, kwargs: dict, text_index: int, field: str = "text"):
    args = list(args)
    has_positional_text = len(args) > text_index
    text = args[text_index] if has_positional_text else kwargs.get(field)
    stripped = strip_custom_emoji_tags(text)
    if stripped is text or stripped == text:
        return tuple(args), False
    if has_positional_text:
        args[text_index] = stripped
    else:
        kwargs[field] = stripped
    return tuple(args), True


def private_chat_id(chat_id) -> bool:
    try:
        return int(chat_id) > 0
    except (TypeError, ValueError):
        return False


def send_message_chat_id(args, kwargs):
    if "chat_id" in kwargs:
        return kwargs.get("chat_id")
    return args[0] if args else None


def should_add_message_effect(args, kwargs: dict) -> bool:
    return "message_effect_id" not in kwargs and private_chat_id(send_message_chat_id(args, kwargs))


def add_random_message_effect(kwargs: dict, effect_ids=None) -> str | None:
    if effect_ids is None:
        effect_ids = ALL_MESSAGE_EFFECT_IDS if main_premium_active() else FREE_MESSAGE_EFFECT_IDS
    if not effect_ids:
        return None
    effect_id = random.choice(effect_ids)
    kwargs["message_effect_id"] = effect_id
    return effect_id


def message_effect_error(error: Exception) -> bool:
    msg = str(error or "").casefold()
    return (
        "message_effect" in msg
        or "effect" in msg
        or "premium" in msg
        or "not enough rights" in msg
        or "can't use" in msg
        or "cannot use" in msg
    )


class PremiumEmojiBot(Bot):
    async def send_message(self, *args, **kwargs):
        args, kwargs = _prepare_premium_text(args, kwargs, 1, "text")
        auto_effect = should_add_message_effect(args, kwargs)
        used_effect = None
        if auto_effect:
            used_effect = add_random_message_effect(kwargs)

        try:
            return await super().send_message(*args, **kwargs)
        except BadRequest as e:
            if custom_emoji_icon_error(e):
                icon_stripped = strip_reply_markup_custom_emoji_icons(kwargs)
                args, text_stripped = strip_custom_emoji_text(args, kwargs, 1, "text")
                if icon_stripped or text_stripped:
                    Log.p("WARN", "Custom emoji ditolak Telegram, retry dengan emoji biasa")
                    try:
                        return await super().send_message(*args, **kwargs)
                    except BadRequest as retry_error:
                        if not auto_effect or not message_effect_error(retry_error):
                            raise
                        e = retry_error
            if auto_effect and used_effect and message_effect_error(e):
                kwargs["message_effect_id"] = random.choice(FREE_MESSAGE_EFFECT_IDS)
                try:
                    return await super().send_message(*args, **kwargs)
                except BadRequest as free_error:
                    if not message_effect_error(free_error):
                        raise
                    kwargs.pop("message_effect_id", None)
                    Log.p("WARN", "Message effect ditolak Telegram, retry tanpa effect")
                    return await super().send_message(*args, **kwargs)
            raise

    async def edit_message_text(self, *args, **kwargs):
        args, kwargs = _prepare_premium_text(args, kwargs, 0, "text")
        try:
            return await super().edit_message_text(*args, **kwargs)
        except BadRequest as e:
            if message_not_modified_error(e):
                return True
            if custom_emoji_icon_error(e):
                icon_stripped = strip_reply_markup_custom_emoji_icons(kwargs)
                args, text_stripped = strip_custom_emoji_text(args, kwargs, 0, "text")
                if icon_stripped or text_stripped:
                    Log.p("WARN", "Custom emoji edit ditolak Telegram, retry dengan emoji biasa")
                    try:
                        return await super().edit_message_text(*args, **kwargs)
                    except BadRequest as retry_error:
                        if message_not_modified_error(retry_error):
                            return True
                        raise
            raise

    async def send_document(self, *args, **kwargs):
        args, kwargs = _prepare_premium_text(args, kwargs, 2, "caption")
        auto_effect = should_add_message_effect(args, kwargs)
        used_effect = None
        if auto_effect:
            used_effect = add_random_message_effect(kwargs)

        try:
            return await super().send_document(*args, **kwargs)
        except BadRequest as e:
            if custom_emoji_icon_error(e):
                icon_stripped = strip_reply_markup_custom_emoji_icons(kwargs)
                args, text_stripped = strip_custom_emoji_text(args, kwargs, 2, "caption")
                if icon_stripped or text_stripped:
                    Log.p("WARN", "Custom emoji dokumen ditolak Telegram, retry dengan emoji biasa")
                    try:
                        return await super().send_document(*args, **kwargs)
                    except BadRequest as retry_error:
                        if not auto_effect or not message_effect_error(retry_error):
                            raise
                        e = retry_error
            if auto_effect and used_effect and message_effect_error(e):
                kwargs["message_effect_id"] = random.choice(FREE_MESSAGE_EFFECT_IDS)
                try:
                    return await super().send_document(*args, **kwargs)
                except BadRequest as free_error:
                    if not message_effect_error(free_error):
                        raise
                    kwargs.pop("message_effect_id", None)
                    Log.p("WARN", "Message effect dokumen ditolak Telegram, retry tanpa effect")
                    return await super().send_document(*args, **kwargs)
            raise


def premium_button_text_and_icon(text: str) -> tuple[str, str | None]:
    if not isinstance(text, str) or not text:
        return text, None
    match = PREMIUM_EMOJI_RE.search(text)
    if not match:
        return text, None
    emoji = match.group(0)
    icon_id = PREMIUM_EMOJI_IDS.get(emoji) if main_premium_active() else None
    cleaned = (text[:match.start()] + text[match.end():]).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    if icon_id:
        return cleaned or text, icon_id
    return text, None
