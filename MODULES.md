# Struktur Modular Autofish

`bot.py` tetap menjadi entrypoint tipis. Runtime utama sekarang dipecah ke package `autofish/`, sementara `autofish/app.py` berperan sebagai orchestrator startup/shutdown dan binder runtime antar module.

## Struktur Saat Ini

```text
bot.py
autofish/
  app.py                  # setup_telegram_bot(), bind_runtime_modules(), main()
  config.py               # env, konstanta, path file, validasi config
  db.py                   # koneksi Mongo dan status Mongo
  state.py                # state global runtime, locks, cache, guard
  accounts.py             # account doc, Mongo helpers, cache account
  admin.py                # admin/premium access, audit, maintenance state
  settings.py             # mode, grup, private bot, verification, account settings
  notifications.py        # notify/log/error/traceback/sell-flow log helpers
  runtime.py              # start/stop account, watchdog, maintenance runtime
  backup.py               # backup dan restore bundle
  broadcast.py            # broadcast user, payload, daily broadcast scheduler
  reports.py              # user report dan owner direct reply
  logging_utils.py        # Log dan now_wib()
  maintenance.py          # parser jadwal maintenance
  utils.py                # JSON, waktu WIB, chat target helpers

  telegram_bot/
    setup.py              # Application builder dan handler registration
    handlers.py           # compatibility binder kosong untuk handler lama
    commands.py           # command Telegram kecil: start/menu/status/help
    callbacks.py          # callback query handler utama
    messages.py           # shortcut keyboard, broadcast reply, owner text
    restore.py            # restore document upload handler
    keyboards.py          # semua keyboard/markup builder
    texts.py              # status/menu/help text formatter
    premium.py            # PremiumEmojiBot dan premium emoji helpers
    actions.py            # reply_clean, restart action, shared bot actions
    buttons.py            # infer_button_style()
    effects.py            # message effect IDs

  userbot/
    client.py             # Pyrogram Client utama bernama app
    login.py              # login flow, session cleanup, clear stuck
    commands.py           # command userbot addprem/rmprem/restart
    sessions.py           # helper path dan hapus file session

  fishing/
    flow.py               # fishing_loop utama
    common.py             # handler/task/delay/message helper
    private.py            # private fishing dan private boost
    group_room.py         # group room join/open flow
    special_group.py      # special group open/boost flow
    rare_catch.py         # rare catch detection/notification
    user_media.py         # backup media user log

  inventory/
    flow.py               # compatibility binder kosong untuk inventory lama
    rules.py              # rules, filtering, gallery
    reader.py             # baca inventory dan pagination
    verification.py       # captcha/manual verification
    sell.py               # favorite dan sell flow
    parsing.py            # helper parsing stateless
    constants.py          # keyword proteksi, rarity, rare catch, sell

  captcha/
    constants.py          # keyword captcha/verifikasi cepat
```

## Catatan Runtime

Beberapa module domain memakai `bind_runtime(namespace)` karena kode lama awalnya satu file dan banyak fungsi saling referensi lintas domain. Binder menjaga nama fungsi/state lama tetap tersedia tanpa mengubah flow bot.
