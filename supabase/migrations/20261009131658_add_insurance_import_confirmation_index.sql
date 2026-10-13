-- Covers the confirmed declaration foreign key for joins and referential checks.
create index insurance_declaration_imports_confirmed_declaration_id_idx
on public.insurance_declaration_imports (confirmed_declaration_id)
where confirmed_declaration_id is not null;
