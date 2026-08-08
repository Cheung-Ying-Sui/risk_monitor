from lxml import etree


xml_path="data/SDN_ADVANCED.XML"

tree=etree.parse(xml_path)

root=tree.getroot()


ns={
"ofac":
"https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


entries=root.xpath(
".//ofac:SanctionsEntry",
namespaces=ns
)


profiles=root.xpath(
".//ofac:Profile",
namespaces=ns
)


print(
"SanctionsEntry:",
len(entries)
)


print(
"Profile:",
len(profiles)
)