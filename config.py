import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {
    int(admin_id.strip())
    for admin_id in _raw_admins.split(",")
    if admin_id.strip().isdigit()
}

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан в .env")