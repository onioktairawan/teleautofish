from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler as TgMessageHandler,
    filters as TgFilters,
)

from autofish.logging_utils import Log


async def build_telegram_bot(bot_token: str, bot_class, handlers: dict) -> Application:
    tg_app = Application.builder().bot(bot_class(token=bot_token)).build()

    tg_app.add_handler(CommandHandler("start", handlers["tg_start"]))
    tg_app.add_handler(CommandHandler("menu", handlers["tg_menu"]))
    tg_app.add_handler(CommandHandler("mancing", handlers["tg_mancing"]))
    tg_app.add_handler(CommandHandler("inventory", handlers["tg_inventory"]))
    tg_app.add_handler(CommandHandler("status", handlers["tg_status"]))
    tg_app.add_handler(CommandHandler("settings", handlers["tg_settings"]))
    tg_app.add_handler(CommandHandler("help", handlers["tg_help"]))
    tg_app.add_handler(CommandHandler("lapor", handlers["tg_lapor"]))
    tg_app.add_handler(CallbackQueryHandler(handlers["tg_button_handler"]))
    tg_app.add_handler(TgMessageHandler(TgFilters.CONTACT, handlers["handle_userbot_login_contact"]))
    tg_app.add_handler(TgMessageHandler(TgFilters.ALL & ~TgFilters.COMMAND, handlers["tg_owner_text_handler"]))
    tg_app.add_error_handler(handlers["tg_error_handler"])

    commands = [
        BotCommand("start", "Buka panel utama"),
        BotCommand("menu", "Kembali ke menu utama"),
        BotCommand("mancing", "Kontrol start/stop mancing"),
        BotCommand("inventory", "Inventory, materials, equipment"),
        BotCommand("status", "Status loop dan monitoring"),
        BotCommand("settings", "Login Telegram, mode, dan grup"),
        BotCommand("help", "Bantuan singkat"),
        BotCommand("lapor", "Lapor bug atau masalah"),
    ]
    await tg_app.bot.set_my_commands(commands)
    Log.p("BOT", "Menu commands terdaftar di Telegram")

    return tg_app

