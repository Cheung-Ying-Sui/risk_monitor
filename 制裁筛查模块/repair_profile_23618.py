from lxml import etree

from parser import parse_entity
from supabase_insert import insert_entity


xml_path = "data/SDN_ADVANCED.XML"


tree = etree.parse(
    xml_path
)

root = tree.getroot()


ns = {
    "ofac":
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


profile_id = "23618"


# ==========================
# 查找对应 SanctionsEntry
# ==========================

entries = root.xpath(
    f".//ofac:SanctionsEntry[@ProfileID='{profile_id}']",
    namespaces=ns
)


if not entries:

    raise Exception(
        "Profile not found"
    )


entry = entries[0]


# ==========================
# 解析实体
# ==========================

entity = parse_entity(
    entry,
    root,
    ns
)


print(
    "Parsed Entity:"
)

print(entity)



# ==========================
# 写入 Supabase
# ==========================

entity_id = insert_entity(
    entity
)


print(
    "Inserted entity id:"
)

print(entity_id)