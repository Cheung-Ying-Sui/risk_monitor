"""Backfill AIS tracking for already confirmed insurance declarations.

Default is read-only. Pass --apply to activate tracking for confirmed insurance
vessels by IMO through Chinaports.
"""

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk_monitor.insurance_repository import InsuranceRepository
from risk_monitor.insurance_tracking_service import InsuranceTrackingService


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile insured vessels with AIS tracking")
    parser.add_argument("--apply", action="store_true", help="activate tracking for confirmed declarations via IMO")
    args = parser.parse_args()
    service = InsuranceTrackingService()
    vessels = InsuranceRepository().list_insured_vessels()
    for vessel in vessels:
        imo = vessel.get("imo_number")
        try:
            if args.apply:
                service.sync_shipments([{"imo_number": imo, "vessel_name": vessel.get("vessel_name")}])
            result = service.status_for(imo)
        except Exception as exc:
            result = f"error:{type(exc).__name__}"
        print(f"IMO {imo or 'missing'} | {vessel['vessel_name']} | {result}")


if __name__ == "__main__":
    main()
