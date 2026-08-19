from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Secrets live outside the OneDrive-synced project tree so they are never
# uploaded to cloud storage. A repo-local .env still works and wins on
# conflicts (load_dotenv does not override already-set variables).
GLOBAL_ENV_FILE = Path.home() / ".baboon" / ".env"


def load_env() -> None:
    load_dotenv(find_dotenv())
    load_dotenv(GLOBAL_ENV_FILE)
