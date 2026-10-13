from __future__ import annotations

from typing import Any

from risk_monitor.supabase_client import supabase


def _first(rows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    return rows[0] if rows else None


class InsuranceRepository:
    def list_companies(self, search: str | None = None) -> list[dict[str, Any]]:
        query = supabase.table("insurance_companies").select("*")
        if search:
            pattern = f"%{search.strip()}%"
            query = query.or_(f"name.ilike.{pattern},name_en.ilike.{pattern}")
        result = query.order("name").execute()
        return result.data or []

    def create_company(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = supabase.table("insurance_companies").insert(payload).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Company insert returned no row")
        return row

    def get_company(self, company_id: str) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_companies")
            .select("*")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )
        return _first(result.data)

    def list_policies(
        self,
        *,
        search: str | None = None,
        company_id: str | None = None,
        insurer: str | None = None,
        status: str | None = None,
        year: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = supabase.table("insurance_policy_summaries").select("*")
        if company_id:
            query = query.eq("company_id", company_id)
        if insurer:
            query = query.ilike("insurer", f"%{insurer.strip()}%")
        if status:
            query = query.eq("status", status)
        if year:
            query = query.lte("start_date", f"{year}-12-31").gte("end_date", f"{year}-01-01")
        if search:
            pattern = f"%{search.strip()}%"
            query = query.or_(
                "policy_name.ilike.{0},policy_number.ilike.{0},insurer.ilike.{0},"
                "company_name.ilike.{0},recent_vessel_name.ilike.{0},"
                "recent_declaration_number.ilike.{0},search_text.ilike.{0}".format(pattern)
            )
        result = (
            query.order("end_date", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    def create_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = supabase.table("insurance_policies").insert(payload).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Policy insert returned no row")
        return self.get_policy(row["id"]) or row

    def update_policy(self, policy_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_policies")
            .update(payload)
            .eq("id", policy_id)
            .execute()
        )
        if not result.data:
            return None
        return self.get_policy(policy_id)

    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_policy_summaries")
            .select("*")
            .eq("id", policy_id)
            .limit(1)
            .execute()
        )
        return _first(result.data)

    def get_dashboard_summary(self) -> dict[str, Any]:
        result = (
            supabase.table("insurance_dashboard_summary")
            .select("*")
            .limit(1)
            .execute()
        )
        return _first(result.data) or {}

    def create_declaration_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = supabase.table("insurance_declaration_imports").insert(payload).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Declaration import insert returned no row")
        return row

    def get_declaration_import(self, import_id: str) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_declaration_imports")
            .select("*")
            .eq("id", import_id)
            .limit(1)
            .execute()
        )
        return _first(result.data)

    def list_pending_declaration_imports(self, limit: int = 50) -> list[dict[str, Any]]:
        result = (supabase.table("insurance_declaration_imports")
                  .select("*").eq("status", "pending_confirmation")
                  .order("created_at", desc=True).limit(limit).execute())
        return result.data or []

    def update_declaration_import(
        self,
        import_id: str,
        parsed_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_declaration_imports")
            .update({"parsed_data": parsed_data})
            .eq("id", import_id)
            .eq("status", "pending_confirmation")
            .execute()
        )
        return _first(result.data)

    def cancel_declaration_import(self, import_id: str) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_declaration_imports")
            .update({"status": "cancelled"})
            .eq("id", import_id)
            .eq("status", "pending_confirmation")
            .execute()
        )
        return _first(result.data)

    def confirm_declaration_import(
        self,
        *,
        import_id: str,
        status: str,
        notes: str | None,
        received_at: str | None,
        shipments: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        result = (
            supabase.rpc(
                "confirm_insurance_declaration_import",
                {
                    "p_import_id": import_id,
                    "p_status": status,
                    "p_notes": notes,
                    "p_received_at": received_at,
                    "p_shipments": shipments,
                },
            )
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise RuntimeError("Declaration confirmation returned no row")
        return row

    def confirm_declaration_import_batch(
        self, *, import_id: str, notes: str | None,
        received_at: str | None, shipments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = supabase.rpc("confirm_insurance_declaration_import_batch", {
            "p_import_id": import_id, "p_notes": notes,
            "p_received_at": received_at, "p_shipments": shipments,
        }).execute()
        return result.data or []

    def confirm_underwriting_terms(self, declaration_id: str, rate: str) -> dict[str, Any]:
        result = supabase.rpc("confirm_insurance_underwriting_terms", {
            "p_declaration_id": declaration_id, "p_rate": rate,
        }).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Underwriting terms confirmation returned no row")
        return row

    def confirm_underwriting(self, declaration_id: str) -> dict[str, Any]:
        result = supabase.rpc("confirm_insurance_underwriting", {
            "p_declaration_id": declaration_id,
        }).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Underwriting confirmation returned no row")
        return row

    def confirm_underwriting_atomic(self, declaration_id: str, rate: str, verification: dict[str, Any]) -> dict[str, Any]:
        result = supabase.rpc('confirm_insurance_underwriting_atomic', {
            'p_declaration_id': declaration_id, 'p_rate': rate,
            'p_expected_workflow': verification['workflow'],
            'p_verified_sha256': verification['sha256'],
            'p_expected_insured_value': verification['insured_value'],
            'p_expected_currency': verification['currency'],
        }).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError('Atomic underwriting confirmation returned no row')
        return row

    def submit_draft(self, declaration_id: str, screening: dict[str, Any]) -> None:
        result = supabase.rpc("submit_insurance_draft", {
            "p_declaration_id": declaration_id,
            "p_screening": screening,
        }).execute()
        if result.data is not True:
            raise RuntimeError("Draft submission returned no confirmation")

    def list_declarations(
        self,
        *,
        policy_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = supabase.table("insurance_declarations").select("*")
        if policy_id:
            query = query.eq("policy_id", policy_id)
        if status:
            query = query.eq("status", status)
        if date_from:
            query = query.gte("received_at", date_from)
        if date_to:
            query = query.lte("received_at", date_to)
        requested_offset = offset
        requested_limit = limit
        if search:
            offset = 0
            limit = 500
        result = query.order("received_at", desc=True).range(offset, offset + limit - 1).execute()
        declarations = self._attach_context(self._attach_shipments(result.data or []))
        if not search:
            return declarations
        needle = search.strip().casefold()
        filtered = []
        for declaration in declarations:
            values = [
                declaration.get("declaration_number"),
                declaration.get("source_file_name"),
                declaration.get("notes"),
                declaration.get("company_name"),
                declaration.get("policy_name"),
            ]
            for shipment in declaration.get("shipments", []):
                values.extend(
                    shipment.get(field)
                    for field in (
                        "vessel_name",
                        "imo_number",
                        "cargo_name",
                        "certificate_number",
                        "loading_port",
                        "discharge_port",
                    )
                )
            if needle in " ".join(str(value) for value in values if value).casefold():
                filtered.append(declaration)
        return filtered[requested_offset:requested_offset + requested_limit]

    def get_declaration(self, declaration_id: str) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_declarations")
            .select("*")
            .eq("id", declaration_id)
            .limit(1)
            .execute()
        )
        declaration = _first(result.data)
        if not declaration:
            return None
        return self._attach_context(self._attach_shipments([declaration]))[0]

    def list_insured_vessels(self) -> list[dict[str, Any]]:
        policies: list[dict[str, Any]] = []
        declarations: list[dict[str, Any]] = []
        for target, fetch in ((policies, self.list_policies), (declarations, self.list_declarations)):
            offset = 0
            while True:
                page = fetch(limit=500, offset=offset)
                target.extend(page)
                if len(page) < 500:
                    break
                offset += 500
        active_policy_ids = {row["id"] for row in policies if row.get("status") != "cancelled"}
        vessels: dict[str, dict[str, Any]] = {}
        for declaration in declarations:
            if declaration.get("status") not in {"confirmed", "covered"} or declaration.get("policy_id") not in active_policy_ids:
                continue
            for shipment in declaration.get("shipments") or []:
                if shipment.get("coverage_status") == "ended_by_mvp_departure":
                    continue
                imo = str(shipment.get("imo_number") or "").strip()
                name = str(shipment.get("vessel_name") or "").strip()
                if not imo and not name:
                    continue
                key = f"imo:{imo}" if imo else f"name:{name.casefold()}"
                item = vessels.setdefault(key, {
                    "vessel_name": name,
                    "imo_number": imo or None,
                    "confirmed_mmsi": None,
                    "declaration_count": 0,
                    "declaration_number": declaration["declaration_number"],
                    "company_name": declaration.get("company_name"),
                    "_declaration_ids": set(),
                    "_confirmed_mmsis": set(),
                })
                item["_declaration_ids"].add(declaration["id"])
                item["declaration_count"] = len(item["_declaration_ids"])
                extra = shipment.get("extra_data") or {}
                if extra.get("mmsi_confirmed") is True and str(extra.get("mmsi_candidate") or "").isdigit() and len(str(extra["mmsi_candidate"])) == 9:
                    item["_confirmed_mmsis"].add(str(extra["mmsi_candidate"]))
        for item in vessels.values():
            item["confirmed_mmsi"] = next(iter(item["_confirmed_mmsis"])) if len(item["_confirmed_mmsis"]) == 1 else None
            del item["_confirmed_mmsis"]
            del item["_declaration_ids"]
        return sorted(vessels.values(), key=lambda row: row["vessel_name"].casefold())

    def list_prediction_shipments(self) -> list[dict[str, Any]]:
        """Server-side per-voyage projection; never include demo/completed records."""
        policies = {}
        offset = 0
        while True:
            page = self.list_policies(limit=500, offset=offset)
            policies.update({row['id']: row for row in page})
            if len(page) < 500:
                break
            offset += 500
        result = []
        for status in ('confirmed', 'covered'):
            offset = 0
            while True:
                page = self.list_declarations(status=status, limit=500, offset=offset)
                for declaration in page:
                    policy = policies.get(declaration.get('policy_id'))
                    if declaration.get('status') not in {'confirmed', 'covered'} or not policy or policy.get('status') == 'cancelled':
                        continue
                    for shipment in declaration.get('shipments') or []:
                        if shipment.get('coverage_status') == 'ended_by_mvp_departure':
                            continue
                        if ((shipment.get('extra_data') or {}).get('voyage_lifecycle') or {}).get('state') == 'ended':
                            continue
                        result.append({**shipment, 'declaration_id': declaration['id'],
                                       'declaration_number': declaration['declaration_number'],
                                       'declaration_status': declaration['status'], 'policy_id': declaration['policy_id']})
                if len(page) < 500:
                    break
                offset += 500
        return result

    def update_declaration_status(
        self, declaration_id: str, status: str
    ) -> dict[str, Any] | None:
        result = (
            supabase.table("insurance_declarations")
            .update({"status": status})
            .eq("id", declaration_id)
            .neq("status", "cancelled")
            .execute()
        )
        if not result.data:
            return None
        return self.get_declaration(declaration_id)

    def _attach_context(
        self,
        declarations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not declarations:
            return []
        policy_ids = sorted({item["policy_id"] for item in declarations})
        company_ids = sorted({item["company_id"] for item in declarations})
        policies = (
            supabase.table("insurance_policies")
            .select("id,policy_name")
            .in_("id", policy_ids)
            .execute()
        )
        companies = (
            supabase.table("insurance_companies")
            .select("id,name")
            .in_("id", company_ids)
            .execute()
        )
        policy_names = {item["id"]: item["policy_name"] for item in policies.data or []}
        company_names = {item["id"]: item["name"] for item in companies.data or []}
        for declaration in declarations:
            declaration["policy_name"] = policy_names.get(declaration["policy_id"])
            declaration["company_name"] = company_names.get(declaration["company_id"])
        return declarations

    def _attach_shipments(
        self,
        declarations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not declarations:
            return []
        declaration_ids = [item["id"] for item in declarations]
        shipment_result = (
            supabase.table("insurance_shipments")
            .select("*")
            .in_("declaration_id", declaration_ids)
            .order("created_at")
            .execute()
        )
        grouped: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in declaration_ids}
        for shipment in shipment_result.data or []:
            grouped.setdefault(shipment["declaration_id"], []).append(shipment)
        for declaration in declarations:
            declaration["shipments"] = grouped.get(declaration["id"], [])
        return declarations

    def create_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = supabase.table("insurance_documents").insert(payload).execute()
        row = _first(result.data)
        if not row:
            raise RuntimeError("Document insert returned no row")
        return row

    def list_documents(
        self,
        *,
        policy_id: str | None = None,
        declaration_id: str | None = None,
        shipment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = supabase.table("insurance_documents").select("*")
        if policy_id:
            query = query.eq("policy_id", policy_id)
        if declaration_id:
            query = query.eq("declaration_id", declaration_id)
        if shipment_id:
            query = query.eq("shipment_id", shipment_id)
        result = query.order("uploaded_at", desc=True).execute()
        return result.data or []
