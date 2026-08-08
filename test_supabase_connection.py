import sys
from postgrest.exceptions import APIError

try:
    from supabase_client import supabase
except Exception as exc:
    print("Failed to initialize Supabase client.")
    print(f"Reason: {exc}")
    sys.exit(1)


def main():
    try:
        result = (
            supabase
            .schema("ingest")
            .table("data_sources")
            .select("*")
            .execute()
        )
    except APIError as exc:
        error_payload = getattr(
            exc,
            "args",
            [{}],
        )[0]

        print("Connected to Supabase, but the query failed.")
        print(f"Reason: {error_payload}")

        if "PGRST106" in str(error_payload):
            print(
                "The ingest schema is not exposed through the Supabase Data API. "
                "Expose the ingest schema in Supabase API settings, then rerun this test."
            )

        sys.exit(1)
    except Exception as exc:
        print("Failed to query Supabase table ingest.data_sources.")
        print(f"Reason: {exc}")
        sys.exit(1)

    print("Supabase connection succeeded.")
    print("ingest.data_sources query result:")
    print(result.data)


if __name__ == "__main__":
    main()
