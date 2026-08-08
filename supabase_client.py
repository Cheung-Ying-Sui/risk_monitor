import os
from pathlib import Path

from supabase import Client, create_client

try:
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(
        Path(__file__).resolve().parent / "制裁筛查模块" / ".env",
        override=False,
    )
except ImportError:
    pass


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SECRET_KEY")
)

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError(
        "Missing SUPABASE_URL and "
        "SUPABASE_SERVICE_KEY/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SECRET_KEY "
        "environment variables."
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
)
