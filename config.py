"""
Central configuration. Reads from environment variables / .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# ── SolarZero / AWS Cognito (constants discovered from the portal) ──────────
COGNITO_URL    = "https://cognito-idp.us-west-2.amazonaws.com/"
COGNITO_CLIENT = "4fdav47mqupph3uireujs64clr"
API_BASE       = "https://api-web.solarzero.co.nz/v1"
TIMEZONE       = "Pacific/Auckland"

# ── Site ────────────────────────────────────────────────────────────────────
SITE_ID = os.environ.get("SOLARZERO_SITE_ID", "SC-23-097707")

# ── Credentials ───────────────────────────────────────────────────────────────
SOLARZERO_EMAIL    = os.environ.get("SOLARZERO_EMAIL", "")
SOLARZERO_PASSWORD = os.environ.get("SOLARZERO_PASSWORD", "")

# ── Supabase / Postgres connection ────────────────────────────────────────────
# Use the Supabase "Connection string" (Transaction or Session pooler), e.g.:
#   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Data go-live (system first produced power)
SYSTEM_GO_LIVE = os.environ.get("SYSTEM_GO_LIVE", "2023-11-05")

# Local data dir for CSV exports / HTML output
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def require(*names: str) -> None:
    """Raise a helpful error if required env vars are missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            f"Missing required config: {', '.join(missing)}.\n"
            f"Set them in {PROJECT_ROOT / '.env'} (copy .env.example)."
        )
