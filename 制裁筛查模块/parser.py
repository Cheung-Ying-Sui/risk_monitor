from lxml import etree


def parse_entity(entry, root, ns):

    # =====================
    # 1. 获取 Profile
    # =====================

    profile_id = entry.attrib["ProfileID"]

    profile = root.xpath(
        f".//ofac:Profile[@ID='{profile_id}']",
        namespaces=ns
    )[0]


    # =====================
    # 2. 提取 Names
    # =====================

    names = profile.xpath(
        ".//ofac:Alias/ofac:DocumentedName/ofac:DocumentedNamePart/ofac:NamePartValue",
        namespaces=ns
    )

    names = [
        name.text
        for name in names
        if name.text
    ]


    # =====================
    # 3. 提取 Sanctions Program
    # =====================

    programs = entry.xpath(
        ".//ofac:SanctionsMeasure/ofac:Comment",
        namespaces=ns
    )

    programs = [
        p.text
        for p in programs
        if p.text
    ]


    # =====================
    # 4. 提取 Address
    # =====================

    addresses = []


    locations = profile.xpath(
        ".//ofac:Feature[@FeatureTypeID='25']//ofac:VersionLocation",
        namespaces=ns
    )


    for loc in locations:

        location_id = loc.attrib.get(
            "LocationID"
        )

        if not location_id:
            continue


        location = root.xpath(
            f".//ofac:Location[@ID='{location_id}']",
            namespaces=ns
        )


        if location:

            parts = location[0].xpath(
                ".//ofac:LocationPart/ofac:LocationPartValue/ofac:Value",
                namespaces=ns
            )

            addresses.extend(
                [
                    p.text
                    for p in parts
                    if p.text
                ]
            )


    # =====================
    # 返回标准数据结构
    # =====================

    return {

        "profile_id": profile_id,

        "names": names,

        "addresses": addresses,

        "programs": programs

    }