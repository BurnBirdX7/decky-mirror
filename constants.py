import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DOMAIN = os.environ["DOMAIN"]
TARGET_STORE_DOMAIN = os.environ["TARGET_STORE_DOMAIN"]
TARGET_CDN_DOMAIN = os.environ["TARGET_CDN_DOMAIN"]
