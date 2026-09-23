#!/usr/bin/env python3
"""Run from any cwd. Dry-run never imports or initializes the Supabase client."""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from dotenv import load_dotenv

from ukmto.client import UKMTOClient
from ukmto.config import ConfigurationError, Settings
from ukmto.logging_utils import configure_logging, error_fields, log
from ukmto.repository import SupabaseIncidentRepository
from ukmto.service import UKMTOService


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect UKMTO Recent Incidents")
    parser.add_argument("--dry-run", action="store_true", help="Parse and output JSON; never access Supabase")
    parser.add_argument("--max-incidents", type=int)
    parser.add_argument("--verbose", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 1
    # Process environment wins, then module .env, then workspace .env.
    load_dotenv(MODULE_ROOT / ".env", override=False)
    load_dotenv(MODULE_ROOT.parent / ".env", override=False)
    configure_logging(args.verbose)
    try:
        settings = Settings.from_env(args.max_incidents)
        repository = None
        if not args.dry_run:
            url = os.getenv("SUPABASE_URL")
            key = (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
                   or os.getenv("SUPABASE_SECRET_KEY"))
            if not url or not key:
                raise ConfigurationError("SUPABASE_URL and a Supabase service/secret key are required")
            from supabase import create_client
            repository = SupabaseIncidentRepository(create_client(url, key))
    except Exception as exc:
        log("ukmto_configuration_error", level=logging.ERROR, **error_fields(exc))
        return 1

    def output_incident(incident):
        # stdout is machine-readable JSON Lines; operational logs go to stderr.
        json.dump({"event": "ukmto_dry_run_incident", "incident": incident.payload()}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")

    client = UKMTOClient(settings)
    try:
        result = UKMTOService(client, repository).run(
            dry_run=args.dry_run, max_incidents=settings.max_incidents,
            on_parsed=output_incident if args.dry_run else None,
        )
        return result.exit_code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
