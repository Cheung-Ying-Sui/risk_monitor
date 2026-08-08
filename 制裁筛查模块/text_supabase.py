import os
from supabase import create_client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SECRET_KEY")

if not url or not key:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SECRET_KEY environment variable.")


supabase = create_client(
    url,
    key
)


result = supabase.table(
    "sanctions_entities"
).select("*").execute()


print(result)
