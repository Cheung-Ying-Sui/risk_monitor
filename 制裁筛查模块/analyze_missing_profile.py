from lxml import etree

from parser import parse_entity


xml_path = "data/SDN_ADVANCED.XML"


tree = etree.parse(xml_path)

root = tree.getroot()


ns = {
    "ofac":
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


profile_id = "23618"


# ==========================
# 1. 查找 SanctionsEntry
# ==========================

entries = root.xpath(
    f".//ofac:SanctionsEntry[@ProfileID='{profile_id}']",
    namespaces=ns
)


print(
    "SanctionsEntry count:",
    len(entries)
)


for entry in entries:

    print(
        etree.tostring(
            entry,
            pretty_print=True,
            encoding="unicode"
        )
    )



# ==========================
# 2. 调用 parser
# ==========================

if entries:

    try:

        entity = parse_entity(
            entries[0],
            root,
            ns
        )


        print("\nParsed Entity:")
        print(entity)


    except Exception as e:

        print(
            "Parser Error:"
        )

        print(e)