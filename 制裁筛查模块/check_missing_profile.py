from lxml import etree

from supabase_client import supabase


# ==========================
# 1. 读取 OFAC XML
# ==========================

xml_path = "data/SDN_ADVANCED.XML"

tree = etree.parse(xml_path)

root = tree.getroot()


ns = {
    "ofac":
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


# ==========================
# 2. 获取 XML Profile IDs
# ==========================

profiles = root.xpath(
    ".//ofac:Profile",
    namespaces=ns
)


xml_profile_ids = set()


for profile in profiles:

    xml_profile_ids.add(
        profile.attrib["ID"]
    )


print(
    "XML Profiles:",
    len(xml_profile_ids)
)



# ==========================
# 3. 分页读取 Supabase
# ==========================

db_profile_ids = set()


page_size = 1000

start = 0


while True:

    result = (
        supabase
        .table("sanctions_entities")
        .select("profile_id")
        .range(
            start,
            start + page_size - 1
        )
        .execute()
    )


    data = result.data


    if not data:

        break


    for item in data:

        db_profile_ids.add(
            str(item["profile_id"])
        )


    print(
        f"Loaded {len(db_profile_ids)} profiles"
    )


    # 下一页

    start += page_size



print(
    "Database Profiles:",
    len(db_profile_ids)
)



# ==========================
# 4. 比较差异
# ==========================

missing = (
    xml_profile_ids
    -
    db_profile_ids
)


extra = (
    db_profile_ids
    -
    xml_profile_ids
)


print(
    "Missing count:",
    len(missing)
)


print(
    "Missing Profiles:"
)

print(
    list(missing)[:20]
)



print(
    "Extra count:",
    len(extra)
)