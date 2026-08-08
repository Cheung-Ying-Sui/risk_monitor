import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from lxml import etree

from normalizer import normalize_name
from supabase_client import supabase

try:
    from dotenv import load_dotenv
    load_dotenv(
        Path(__file__).resolve().parent / ".env",
        override=True
    )
except ImportError:
    pass


SOURCE = "OFAC"
SOURCE_NAME = "OFAC_SDN_ADVANCED_XML"
DEFAULT_OFAC_ADVANCED_XML_URLS = [
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/sdn_advanced.xml",
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML",
    "http://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml",
    "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml"
]
OFAC_ADVANCED_XML_URL_VALUE = os.getenv(
    "OFAC_ADVANCED_XML_URLS",
    os.getenv(
        "OFAC_ADVANCED_XML_URL",
        ",".join(
            DEFAULT_OFAC_ADVANCED_XML_URLS
        )
    )
)
OFAC_ADVANCED_XML_URLS = [
    url.strip()
    for url in OFAC_ADVANCED_XML_URL_VALUE.split(
        ","
    )
    if url.strip()
]
OFAC_ADVANCED_XML_URL = (
    OFAC_ADVANCED_XML_URLS[0]
    if OFAC_ADVANCED_XML_URLS
    else DEFAULT_OFAC_ADVANCED_XML_URLS[0]
)
OFAC_ALLOW_INSECURE_DOWNLOAD = os.getenv(
    "OFAC_ALLOW_INSECURE_DOWNLOAD",
    "false"
).lower() == "true"
OFAC_USE_LOCAL_XML = os.getenv(
    "OFAC_USE_LOCAL_XML",
    "false"
).lower() == "true"
OFAC_FALLBACK_TO_LOCAL_XML = os.getenv(
    "OFAC_FALLBACK_TO_LOCAL_XML",
    "false"
).lower() == "true"
OFAC_DOWNLOAD_METHOD = os.getenv(
    "OFAC_DOWNLOAD_METHOD",
    "auto"
).lower()
OFAC_CURL_MAX_TIME = os.getenv(
    "OFAC_CURL_MAX_TIME",
    "900"
)
OFAC_CURL_LOW_SPEED_LIMIT = os.getenv(
    "OFAC_CURL_LOW_SPEED_LIMIT",
    "10240"
)
OFAC_CURL_LOW_SPEED_TIME = os.getenv(
    "OFAC_CURL_LOW_SPEED_TIME",
    "60"
)
DATA_DIR = Path(__file__).resolve().parent / "data"
LOCAL_XML_PATH = DATA_DIR / "sdn_advanced.xml"
TEMP_XML_PATH = DATA_DIR / "sdn_advanced.xml.tmp"
BATCH_SIZE = 1000
USER_AGENT = "Mozilla/5.0 risk-monitor-ofac-sync/1.0"
OFAC_NS = {
    "ofac": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
}


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def format_mb(byte_count):
    return byte_count / 1024 / 1024


def download_response_to_file(response, url):
    total_bytes = int(
        response.headers.get(
            "content-length",
            0
        )
        or 0
    )
    downloaded_bytes = 0
    last_reported_mb = -1

    with TEMP_XML_PATH.open(
        "wb"
    ) as file:
        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):
            if not chunk:
                continue

            file.write(
                chunk
            )
            downloaded_bytes += len(
                chunk
            )

            downloaded_mb = int(
                format_mb(
                    downloaded_bytes
                )
            )

            if downloaded_mb == last_reported_mb:
                continue

            last_reported_mb = downloaded_mb

            if total_bytes:
                percent = downloaded_bytes / total_bytes * 100
                print(
                    f"Downloading OFAC XML: {format_mb(downloaded_bytes):.1f}/"
                    f"{format_mb(total_bytes):.1f} MB ({percent:.1f}%)"
                )
            else:
                print(
                    f"Downloading OFAC XML: {format_mb(downloaded_bytes):.1f} MB"
                )

    content = TEMP_XML_PATH.read_bytes()

    if not content.lstrip().startswith(
        b"<"
    ):
        TEMP_XML_PATH.unlink(
            missing_ok=True
        )
        raise ValueError(
            f"{url}: response did not look like XML"
        )

    TEMP_XML_PATH.replace(
        LOCAL_XML_PATH
    )

    return content


def validate_and_save_temp_xml(url):
    content = TEMP_XML_PATH.read_bytes()

    if not content.lstrip().startswith(
        b"<"
    ):
        TEMP_XML_PATH.unlink(
            missing_ok=True
        )
        raise ValueError(
            f"{url}: response did not look like XML"
        )

    TEMP_XML_PATH.replace(
        LOCAL_XML_PATH
    )

    return content


def download_with_requests(url, request_kwargs):
    response = requests.get(
        url,
        **request_kwargs
    )
    response.raise_for_status()

    return download_response_to_file(
        response,
        url
    )


def download_with_curl(url):
    if TEMP_XML_PATH.exists():
        print(
            f"Resuming partial download: {TEMP_XML_PATH} "
            f"({format_mb(TEMP_XML_PATH.stat().st_size):.1f} MB)"
        )

    command = [
        "curl",
        "--fail",
        "--location",
        "--show-error",
        "--continue-at",
        "-",
        "--connect-timeout",
        "20",
        "--max-time",
        OFAC_CURL_MAX_TIME,
        "--speed-limit",
        OFAC_CURL_LOW_SPEED_LIMIT,
        "--speed-time",
        OFAC_CURL_LOW_SPEED_TIME,
        "--retry",
        "2",
        "--retry-delay",
        "3",
        "--user-agent",
        USER_AGENT,
        "--output",
        str(
            TEMP_XML_PATH
        ),
        url
    ]

    if OFAC_ALLOW_INSECURE_DOWNLOAD:
        command.insert(
            1,
            "--insecure"
        )

    subprocess.run(
        command,
        check=True
    )

    return validate_and_save_temp_xml(
        url
    )


def download_latest_xml():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if OFAC_USE_LOCAL_XML:
        if not LOCAL_XML_PATH.exists():
            raise FileNotFoundError(
                f"Local OFAC XML not found: {LOCAL_XML_PATH}"
            )

        return LOCAL_XML_PATH.read_bytes()

    request_kwargs = {
        "headers": {
            "User-Agent": USER_AGENT
        },
        "timeout": (
            20,
            120
        ),
        "stream": True
    }

    if OFAC_ALLOW_INSECURE_DOWNLOAD:
        request_kwargs["verify"] = False

    errors = []

    for url in OFAC_ADVANCED_XML_URLS:
        methods = (
            ["requests", "curl"]
            if OFAC_DOWNLOAD_METHOD == "auto"
            else [OFAC_DOWNLOAD_METHOD]
        )

        for method in methods:
            try:
                print(
                    f"Attempting OFAC download with {method}: {url}"
                )

                if method == "requests":
                    content = download_with_requests(
                        url,
                        request_kwargs
                    )
                elif method == "curl":
                    content = download_with_curl(
                        url
                    )
                else:
                    raise ValueError(
                        "OFAC_DOWNLOAD_METHOD must be one of: "
                        "auto, requests, curl"
                    )
            except (
                requests.exceptions.RequestException,
                subprocess.CalledProcessError,
                ValueError
            ) as exc:
                errors.append(
                    f"{method} {url}: {exc}"
                )
                continue

            print(
                f"Downloaded OFAC XML from: {url}"
            )
            print(
                f"Saved OFAC XML to: {LOCAL_XML_PATH}"
            )

            return content

    if OFAC_FALLBACK_TO_LOCAL_XML and LOCAL_XML_PATH.exists():
        print(
            "OFAC download failed; falling back to local XML because "
            "OFAC_FALLBACK_TO_LOCAL_XML=true."
        )
        print(
            "Download errors:"
        )

        for error in errors:
            print(
                f"- {error}"
            )

        return LOCAL_XML_PATH.read_bytes()

    raise RuntimeError(
        "Failed to download OFAC SDN Advanced XML from all configured URLs. "
        "For local development, set OFAC_USE_LOCAL_XML=true to use the "
        "existing local file, or set OFAC_FALLBACK_TO_LOCAL_XML=true to "
        "fall back when download fails. For production, fix the network/TLS "
        "path instead of relying on local fallback. "
        f"Attempted URLs: {OFAC_ADVANCED_XML_URLS}. "
        f"Errors: {errors}"
    )


def sha256_hex(content):
    return hashlib.sha256(
        content
    ).hexdigest()


def create_import_batch(file_hash):
    result = (
        supabase
        .table("sanctions_import_batches")
        .insert(
            {
                "source": SOURCE_NAME,
                "source_url": OFAC_ADVANCED_XML_URL,
                "file_hash": file_hash,
                "downloaded_at": utc_now(),
                "started_at": utc_now(),
                "status": "running",
            }
        )
        .execute()
    )

    return result.data[0]["id"]


def update_import_batch(batch_id, payload):
    (
        supabase
        .table("sanctions_import_batches")
        .update(
            payload
        )
        .eq(
            "id",
            batch_id
        )
        .execute()
    )


def parse_entries(xml_path):
    tree = etree.parse(
        str(xml_path)
    )
    root = tree.getroot()

    return (
        root,
        root.xpath(
            ".//ofac:SanctionsEntry",
            namespaces=OFAC_NS
        )
    )


def build_xml_indexes(root):
    profiles = {
        profile.attrib["ID"]: profile
        for profile in root.xpath(
            ".//ofac:Profile",
            namespaces=OFAC_NS
        )
        if profile.attrib.get(
            "ID"
        )
    }
    locations = {
        location.attrib["ID"]: location
        for location in root.xpath(
            ".//ofac:Location",
            namespaces=OFAC_NS
        )
        if location.attrib.get(
            "ID"
        )
    }

    return {
        "profiles": profiles,
        "locations": locations
    }


def parse_entity_from_indexes(entry, indexes):
    profile_id = entry.attrib["ProfileID"]
    profile = indexes["profiles"].get(
        profile_id
    )

    if profile is None:
        raise ValueError(
            f"Profile not found: {profile_id}"
        )

    names = [
        name.text
        for name in profile.xpath(
            ".//ofac:Alias/ofac:DocumentedName/"
            "ofac:DocumentedNamePart/ofac:NamePartValue",
            namespaces=OFAC_NS
        )
        if name.text
    ]
    programs = [
        program.text
        for program in entry.xpath(
            ".//ofac:SanctionsMeasure/ofac:Comment",
            namespaces=OFAC_NS
        )
        if program.text
    ]
    addresses = []

    version_locations = profile.xpath(
        ".//ofac:Feature[@FeatureTypeID='25']//ofac:VersionLocation",
        namespaces=OFAC_NS
    )

    for version_location in version_locations:
        location_id = version_location.attrib.get(
            "LocationID"
        )

        if not location_id:
            continue

        location = indexes["locations"].get(
            location_id
        )

        if location is None:
            continue

        addresses.extend(
            [
                part.text
                for part in location.xpath(
                    ".//ofac:LocationPart/ofac:LocationPartValue/ofac:Value",
                    namespaces=OFAC_NS
                )
                if part.text
            ]
        )

    return {
        "profile_id": profile_id,
        "names": names,
        "addresses": addresses,
        "programs": programs
    }


def mark_missing_entities_inactive(batch_id):
    result = (
        supabase
        .rpc(
            "mark_ofac_entities_inactive",
            {
                "current_batch_id": batch_id
            }
        )
        .execute()
    )

    if result.data is None:
        return 0

    return int(
        result.data
    )


def chunks(items, size):
    for start in range(
        0,
        len(items),
        size
    ):
        yield items[start:start + size]


def unique_values(values):
    return list(
        dict.fromkeys(
            value
            for value in values
            if value
        )
    )


def merge_entities_by_profile_id(entities):
    merged = {}

    for entity in entities:
        profile_id = entity["profile_id"]

        if profile_id not in merged:
            merged[profile_id] = {
                "profile_id": profile_id,
                "names": [],
                "addresses": [],
                "programs": []
            }

        merged_entity = merged[profile_id]
        merged_entity["names"].extend(
            entity["names"]
        )
        merged_entity["addresses"].extend(
            entity["addresses"]
        )
        merged_entity["programs"].extend(
            entity["programs"]
        )

    for merged_entity in merged.values():
        merged_entity["names"] = unique_values(
            merged_entity["names"]
        )
        merged_entity["addresses"] = unique_values(
            merged_entity["addresses"]
        )
        merged_entity["programs"] = unique_values(
            merged_entity["programs"]
        )

    return list(
        merged.values()
    )


def fetch_existing_entities(profile_ids):
    existing = {}

    for batch in chunks(
        profile_ids,
        BATCH_SIZE
    ):
        result = (
            supabase
            .table("sanctions_entities")
            .select("id,profile_id,is_active")
            .in_(
                "profile_id",
                batch
            )
            .execute()
        )

        for row in result.data or []:
            existing[row["profile_id"]] = row

    return existing


def batch_upsert(table_name, rows, on_conflict, label):
    if not rows:
        return

    total_rows = len(
        rows
    )

    for index, batch in enumerate(
        chunks(
            rows,
            BATCH_SIZE
        ),
        start=1
    ):
        (
            supabase
            .table(table_name)
            .upsert(
                batch,
                on_conflict=on_conflict
            )
            .execute()
        )

        print(
            f"{label}: upserted {min(index * BATCH_SIZE, total_rows)}/{total_rows}"
        )


def upsert_entities(parsed_entities, existing_entities, batch_id, seen_at):
    new_rows = []
    existing_rows = []

    for entity in parsed_entities:
        profile_id = entity["profile_id"]
        row = {
            "profile_id": profile_id,
            "source": SOURCE,
            "is_active": True,
            "last_seen_at": seen_at,
            "removed_at": None
        }

        if batch_id:
            row["last_import_batch_id"] = batch_id

        if profile_id in existing_entities:
            existing_rows.append(
                row
            )
        else:
            insert_row = {
                **row,
                "first_seen_at": seen_at
            }
            new_rows.append(
                insert_row
            )

    batch_upsert(
        "sanctions_entities",
        new_rows,
        "profile_id",
        "Entities inserted"
    )
    batch_upsert(
        "sanctions_entities",
        existing_rows,
        "profile_id",
        "Entities updated"
    )

    inserted_count = len(
        new_rows
    )
    reactivated_count = sum(
        1
        for entity in parsed_entities
        if entity["profile_id"] in existing_entities
        and not bool(
            existing_entities[entity["profile_id"]].get(
                "is_active",
                True
            )
        )
    )

    return (
        inserted_count,
        reactivated_count
    )


def fetch_entity_id_map(profile_ids):
    entity_id_map = {}

    for batch in chunks(
        profile_ids,
        BATCH_SIZE
    ):
        result = (
            supabase
            .table("sanctions_entities")
            .select("id,profile_id")
            .in_(
                "profile_id",
                batch
            )
            .execute()
        )

        for row in result.data or []:
            entity_id_map[row["profile_id"]] = row["id"]

    return entity_id_map


def build_relation_rows(parsed_entities, entity_id_map):
    name_rows = []
    address_rows = []
    program_rows = []
    seen_names = set()
    seen_addresses = set()
    seen_programs = set()

    for entity in parsed_entities:
        entity_id = entity_id_map.get(
            entity["profile_id"]
        )

        if not entity_id:
            raise RuntimeError(
                f"Missing entity id for profile_id={entity['profile_id']}"
            )

        for name in unique_values(
            entity["names"]
        ):
            key = (
                entity_id,
                name
            )

            if key in seen_names:
                continue

            seen_names.add(
                key
            )
            name_rows.append(
                {
                    "entity_id": entity_id,
                    "name": name,
                    "normalized_name": normalize_name(
                        name
                    )
                }
            )

        for address in unique_values(
            entity["addresses"]
        ):
            key = (
                entity_id,
                address
            )

            if key in seen_addresses:
                continue

            seen_addresses.add(
                key
            )
            address_rows.append(
                {
                    "entity_id": entity_id,
                    "address": address
                }
            )

        for program in unique_values(
            entity["programs"]
        ):
            key = (
                entity_id,
                program
            )

            if key in seen_programs:
                continue

            seen_programs.add(
                key
            )
            program_rows.append(
                {
                    "entity_id": entity_id,
                    "program": program
                }
            )

    return (
        name_rows,
        address_rows,
        program_rows
    )


def sync_ofac():
    batch_id = None

    try:
        print("Downloading latest OFAC SDN Advanced XML...")
        content = download_latest_xml()
        file_hash = sha256_hex(
            content
        )

        batch_id = create_import_batch(
            file_hash
        )

        print(
            f"Import batch: {batch_id}"
        )
        print(
            f"File hash: {file_hash}"
        )

        root, entries = parse_entries(
            LOCAL_XML_PATH
        )
        xml_indexes = build_xml_indexes(
            root
        )

        total_entries = len(
            entries
        )
        success_count = 0
        failed_count = 0
        inserted_count = 0
        reactivated_count = 0
        parsed_entities = []

        print(
            f"Total entries: {total_entries}"
        )

        for index, entry in enumerate(
            entries,
            start=1
        ):
            try:
                entity = parse_entity_from_indexes(
                    entry,
                    xml_indexes
                )
                parsed_entities.append(
                    entity
                )

                success_count += 1

                if index % BATCH_SIZE == 0:
                    print(
                        f"Parsed {index}/{total_entries}"
                    )

            except Exception as exc:
                failed_count += 1
                profile_id = entry.attrib.get(
                    "ProfileID",
                    "UNKNOWN"
                )
                print(
                    f"Failed profile {profile_id}: {exc}"
                )

        if parsed_entities:
            profile_ids = unique_values(
                entity["profile_id"]
                for entity in parsed_entities
            )
            parsed_entities = merge_entities_by_profile_id(
                parsed_entities
            )
            seen_at = utc_now()

            print(
                f"Parsed successfully: {success_count}. "
                f"Unique profiles: {len(parsed_entities)}. "
                "Fetching existing entities..."
            )
            existing_entities = fetch_existing_entities(
                profile_ids
            )

            print(
                "Upserting sanctions_entities in batches..."
            )
            inserted_count, reactivated_count = upsert_entities(
                parsed_entities,
                existing_entities,
                batch_id,
                seen_at
            )

            print(
                "Fetching entity id mapping..."
            )
            entity_id_map = fetch_entity_id_map(
                profile_ids
            )

            print(
                "Building relation rows..."
            )
            name_rows, address_rows, program_rows = build_relation_rows(
                parsed_entities,
                entity_id_map
            )

            print(
                f"Prepared rows: names={len(name_rows)}, "
                f"addresses={len(address_rows)}, programs={len(program_rows)}"
            )

            batch_upsert(
                "sanctions_names",
                name_rows,
                "entity_id,name",
                "Names"
            )
            batch_upsert(
                "sanctions_addresses",
                address_rows,
                "entity_id,address",
                "Addresses"
            )
            batch_upsert(
                "sanctions_programs",
                program_rows,
                "entity_id,program",
                "Programs"
            )

        inactive_count = 0

        if failed_count == 0:
            inactive_count = mark_missing_entities_inactive(
                batch_id
            )
        else:
            print(
                "Skipping inactive marking because this import had failed entries."
            )

        status = "completed" if failed_count == 0 else "completed_with_errors"

        update_import_batch(
            batch_id,
            {
                "completed_at": utc_now(),
                "status": status,
                "total_entries": total_entries,
                "success_count": success_count,
                "failed_count": failed_count,
                "inserted_count": inserted_count,
                "reactivated_count": reactivated_count,
                "inactive_count": inactive_count,
                "metadata": {
                    "local_xml_path": str(
                        LOCAL_XML_PATH
                    )
                }
            }
        )

        print("Sync completed.")
        print(
            f"Success: {success_count}, Failed: {failed_count}, "
            f"Inserted: {inserted_count}, Reactivated: {reactivated_count}, "
            f"Marked inactive: {inactive_count}"
        )

        return {
            "batch_id": batch_id,
            "status": status,
            "total_entries": total_entries,
            "success_count": success_count,
            "failed_count": failed_count,
            "inserted_count": inserted_count,
            "reactivated_count": reactivated_count,
            "inactive_count": inactive_count,
            "file_hash": file_hash
        }

    except Exception as exc:
        if batch_id:
            update_import_batch(
                batch_id,
                {
                    "completed_at": utc_now(),
                    "status": "failed",
                    "error_message": str(
                        exc
                    )
                }
            )

        raise


if __name__ == "__main__":
    sync_ofac()
