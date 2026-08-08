from lxml import etree
from parser import parse_entity


xml_path = "data/SDN_ADVANCED.XML"


tree = etree.parse(xml_path)

root = tree.getroot()


ns = {
    "ofac": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
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
# 填入之前失败的index
# ==========================

failed_indexes = [
    55,
    56,
    59,
    61,
    63
]


# ==========================
# 分析失败实体
# ==========================

for index in failed_indexes:

    print("\n======================")
    print(
        "Entry Index:",
        index
    )


    entry = entries[index]


    profile_id = entry.attrib.get(
        "ProfileID"
    )


    print(
        "Profile ID:",
        profile_id
    )


    try:

        entity = parse_entity(
            entry,
            root,
            ns
        )


        print(
            "Parsed Entity:"
        )

        print(entity)


    except Exception as e:


        print(
            "Parse Error:"
        )

        print(
            str(e)
        )


    # ======================
    # 查看原始XML
    # ======================

    print(
        "Raw SanctionsEntry:"
    )


    print(
        etree.tostring(
            entry,
            pretty_print=True,
            encoding="unicode"
        )[:3000]
    )