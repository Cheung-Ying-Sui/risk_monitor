-- Accept newly generated Word reports while retaining previously archived HTML reports.
-- Both underwriting guards continue to require matching document IDs and SHA-256 hashes.
do $$
declare
    v_signature text;
    v_definition text;
    v_updated text;
begin
    foreach v_signature in array array[
        'public.confirm_insurance_underwriting(uuid,numeric)',
        'public.confirm_insurance_underwriting_terms(uuid,numeric)'
    ] loop
        select pg_get_functiondef(to_regprocedure(v_signature)) into v_definition;
        if v_definition is null then
            raise exception 'missing function %', v_signature;
        end if;
        v_updated := replace(
            v_definition,
            'd.content_type like ''text/html%''',
            'd.content_type in (''text/html; charset=utf-8'', ''application/vnd.openxmlformats-officedocument.wordprocessingml.document'')'
        );
        if v_updated = v_definition then
            raise exception 'report MIME guard not found in %', v_signature;
        end if;
        execute v_updated;
    end loop;
end;
$$;
