from lxml import etree
from parser import parse_entity
from supabase_insert import insert_entity


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


print("Total entries:", len(entries))


success_count = 0
failed_count = 0


for i, entry in enumerate(entries):

    try:

        entity = parse_entity(
            entry,
            root,
            ns
        )


        insert_entity(entity)


        success_count += 1


        if i % 100 == 0:

            print(
                f"Processed: {i}/{len(entries)}"
            )


    except Exception as e:

        failed_count += 1

        print(
            f"Failed at {i}:",
            e
        )


print("====================")
print("Success:", success_count)
print("Failed:", failed_count)