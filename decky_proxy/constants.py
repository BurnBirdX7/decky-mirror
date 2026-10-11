import os
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env")

VERSION = version("decky-proxy")

RESOURCE_SIGNING_KEY = os.environ["RESOURCE_SIGNING_KEY"]  # set to non-empty string or `random`
DOMAIN = os.environ["DOMAIN"]
TARGET_STORE_DOMAIN = os.environ["TARGET_STORE_DOMAIN"]
TARGET_CDN_DOMAIN = os.environ["TARGET_CDN_DOMAIN"]
