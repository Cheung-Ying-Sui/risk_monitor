from supabase_client import supabase
from normalizer import normalize_name


PAGE_SIZE = 1000


def fetch_null_normalized_names():
    return (
        supabase
        .table("sanctions_names")
        .select("id,name")
        .is_("normalized_name", None)
        .limit(PAGE_SIZE)
        .execute()
        .data
    )


def repair_null_normalized_names():
    total_repaired = 0
    batch_no = 1

    while True:
        records = fetch_null_normalized_names()

        if not records:
            break

        print(
            f"Batch {batch_no}: repairing {len(records)} records"
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

        total_repaired += len(records)

        print(
            f"Total repaired: {total_repaired}"
        )

        batch_no += 1

    print(
        f"Repair completed. Total repaired: {total_repaired}"
    )


if __name__ == "__main__":
    repair_null_normalized_names()
