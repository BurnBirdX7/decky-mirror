import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

with (PROJECT_ROOT / "pyproject.toml").open("rb") as metadata:
    VERSION = tomllib.load(metadata)["project"]["version"]

RESOURCE_SIGNING_KEY = os.environ["RESOURCE_SIGNING_KEY"]  # set to non-empty string or `random`
DOMAIN = os.environ["DOMAIN"]
TARGET_STORE_DOMAIN = os.environ["TARGET_STORE_DOMAIN"]
TARGET_CDN_DOMAIN = os.environ["TARGET_CDN_DOMAIN"]
