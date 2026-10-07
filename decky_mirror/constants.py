import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

RESOURCE_SIGNING_KEY = os.environ.get("RESOURCE_SIGNING_KEY")
if not RESOURCE_SIGNING_KEY:
    raise RuntimeError("RESOURCE_SIGNING_KEY must be set to a nonempty secret or 'random'")

DOMAIN = os.environ["DOMAIN"]
TARGET_STORE_DOMAIN = os.environ["TARGET_STORE_DOMAIN"]
TARGET_CDN_DOMAIN = os.environ["TARGET_CDN_DOMAIN"]
