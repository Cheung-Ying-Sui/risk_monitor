from supabase_client import supabase
from normalizer import normalize_name


PAGE_SIZE = 1000


def fetch_name_batch(last_id=None):
    query = (
        supabase
        .table("sanctions_names")
        .select("id,name")
        .order("id")
        .limit(PAGE_SIZE)
    )

    if last_id is not None:
        query = query.gt(
            "id",
            last_id
        )

    return query.execute().data


def recompute_normalized_names():
    total_updated = 0
    batch_no = 1
    last_id = None

    while True:
        records = fetch_name_batch(
            last_id
        )

        if not records:
            break

        print(
            f"Batch {batch_no}: recomputing {len(records)} records"
        )

        update_data = [
            {
                "id": record["id"],
                "name": record["name"],
                "normalized_name": normalize_name(
                    record["name"]
                )
            }
            for record in records
        ]

        (
            supabase
            .table("sanctions_names")
            .upsert(
                update_data,
                on_conflict="id"
            )
            .execute()
        )

        total_updated += len(records)
        last_id = records[-1]["id"]

        print(
            f"Total recomputed: {total_updated}"
        )

        batch_no += 1

    print(
        f"Recompute completed. Total recomputed: {total_updated}"
    )


if __name__ == "__main__":
    recompute_normalized_names()
