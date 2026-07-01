from pymongo import MongoClient

from .config import MONGO_COLLECTION, MONGO_DB, MONGO_URL


mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000) if MONGO_URL else None
mongo_col = mongo_client[MONGO_DB][MONGO_COLLECTION] if mongo_client is not None else None


def mongo_enabled() -> bool:
    return mongo_col is not None

