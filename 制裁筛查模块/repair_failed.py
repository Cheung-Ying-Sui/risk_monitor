from lxml import etree

from parser import parse_entity
from supabase_insert import insert_entity


# ==========================
# 1. 读取 OFAC XML
# ==========================

xml_path = "data/SDN_ADVANCED.XML"


tree = etree.parse(
    xml_path
)

root = tree.getroot()


ns = {
    "ofac":
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


entries = root.xpath(
    ".//ofac:SanctionsEntry",
    namespaces=ns
)


print(
    "Total entries:",
    len(entries)
)


# ==========================
# 2. 失败实体 Profile ID
# ==========================

failed_profile_ids = [
    "2676",
    "2677",
    "2681",
    "2683",
    "2686"
]


# ==========================
# 3. 重新解析并写入
# ==========================

success_count = 0
failed_count = 0


for entry in entries:

    profile_id = entry.attrib.get(
        "ProfileID"
    )


    if profile_id not in failed_profile_ids:
        continue


    print("\n====================")
    print(
        "Repair Profile ID:",
        profile_id
    )


    try:

        # 解析实体
        entity = parse_entity(
            entry,
            root,
            ns
        )


        print(
            "Parsed Entity:"
        )

        print(entity)


        # 写入 Supabase
        entity_id = insert_entity(
            entity
        )


        print(
            "Inserted entity id:",
            entity_id
        )


        success_count += 1


    except Exception as e:


        failed_count += 1


        print(
            "Repair failed:",
            profile_id
        )


        print(
            "Error:",
            str(e)
        )



# ==========================
# 4. 输出结果
# ==========================

print("\n====================")
print(
    "Repair finished"
)

print(
    "Success:",
    success_count
)

print(
    "Failed:",
    failed_count
)