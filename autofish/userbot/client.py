from pyrogram import Client

from autofish.config import (
    API_HASH,
    API_ID,
    BASE_DIR,
    PYRO_APP_VERSION,
    PYRO_DEVICE_MODEL,
    PYRO_SYSTEM_VERSION,
)


app = Client(
    "fishbot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    device_model=PYRO_DEVICE_MODEL,
    system_version=PYRO_SYSTEM_VERSION,
    app_version=PYRO_APP_VERSION,
    workdir=BASE_DIR,
    sleep_threshold=60,
)

