from datetime import datetime, timezone

from supabase_client import supabase
from normalizer import normalize_name


def insert_entity(entity, import_batch_id=None, return_details=False):
    seen_at = datetime.now(
        timezone.utc
    ).isoformat()


    # =====================
    # 1. 插入 / 获取主体
    # =====================

    try:

        result = supabase.table(
            "sanctions_entities"
        ).select("*").eq(
            "profile_id",
            entity["profile_id"]
        ).execute()


        if result.data:

            existing_entity = result.data[0]
            entity_id = existing_entity["id"]
            inserted = False
            was_active = bool(
                existing_entity.get("is_active", True)
            )

            update_payload = {
                "source": "OFAC",
                "is_active": True,
                "last_seen_at": seen_at,
                "removed_at": None
            }

            if import_batch_id:
                update_payload["last_import_batch_id"] = import_batch_id

            supabase.table(
                "sanctions_entities"
            ).update(
                update_payload
            ).eq(
                "id",
                entity_id
            ).execute()


        else:

            inserted = True
            was_active = False

            insert_payload = {
                "profile_id": entity["profile_id"],
                "source": "OFAC",
                "is_active": True,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "removed_at": None
            }

            if import_batch_id:
                insert_payload["last_import_batch_id"] = import_batch_id

            result = supabase.table(
                "sanctions_entities"
            ).insert(
                insert_payload
            ).execute()


            entity_id = result.data[0]["id"]


    except Exception as e:

        print(
            "Entity insert failed:",
            entity["profile_id"]
        )

        raise e



    # =====================
    # 2. Names 去重 + 插入
    # =====================

    names = list(
        dict.fromkeys(
            entity["names"]
        )
    )


    if names:

        try:

            supabase.table(
                "sanctions_names"
            ).upsert(
                [
                    {
                        "entity_id": entity_id,
                        "name": name,
                        "normalized_name": normalize_name(name)
                    }
                    for name in names
                ],
                on_conflict="entity_id,name"
            ).execute()


        except Exception as e:

            print(
                "Names insert failed:",
                entity["profile_id"]
            )

            print(
                "Names:",
                names
            )

            raise e



    # =====================
    # 3. Addresses 去重 + 插入
    # =====================

    addresses = list(
        dict.fromkeys(
            entity["addresses"]
        )
    )


    if addresses:

        try:

            supabase.table(
                "sanctions_addresses"
            ).upsert(
                [
                    {
                        "entity_id": entity_id,
                        "address": address
                    }
                    for address in addresses
                ],
                on_conflict="entity_id,address"
            ).execute()


        except Exception as e:

            print(
                "Address insert failed:",
                entity["profile_id"]
            )

            print(
                "Addresses:",
                addresses
            )

            raise e



    # =====================
    # 4. Programs 去重 + 插入
    # =====================

    programs = list(
        dict.fromkeys(
            entity["programs"]
        )
    )


    if programs:

        try:

            supabase.table(
                "sanctions_programs"
            ).upsert(
                [
                    {
                        "entity_id": entity_id,
                        "program": program
                    }
                    for program in programs
                ],
                on_conflict="entity_id,program"
            ).execute()


        except Exception as e:

            print(
                "Program insert failed:",
                entity["profile_id"]
            )

            print(
                "Programs:",
                programs
            )

            raise e



    if return_details:
        return {
            "entity_id": entity_id,
            "inserted": inserted,
            "reactivated": (not inserted) and (not was_active)
        }

    return entity_id
