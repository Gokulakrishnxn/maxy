"""
Single source of truth for MAXY_HOME directory.
All Python modules import from here — never hardcode ~/maxy/ directly.

Priority: MAXY_HOME env var → ~/maxy (default / backward-compat)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

MAXY_HOME = Path(os.environ.get("MAXY_HOME", os.path.expanduser("~/maxy")))

# Create data dir if it doesn't exist yet (first install on a new machine)
MAXY_HOME.mkdir(parents=True, exist_ok=True)

# Load .env from the data directory so API keys travel with the data dir
_env_file = MAXY_HOME / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

DB_PATH     = str(MAXY_HOME / "maxy.db")
CREDS_FILE  = str(MAXY_HOME / "credentials.json")
TOKEN_FILE  = str(MAXY_HOME / "gmail_token.json")
