-- Execute against the development database after the migration. All fixtures roll back.
begin;
set local role service_role;
do $$
declare
    c uuid := gen_random_uuid(); p uuid := gen_random_uuid(); d uuid := gen_random_uuid();
    s uuid := gen_random_uuid(); second_shipment uuid := gen_random_uuid(); screenshot uuid := gen_random_uuid(); report_doc uuid := gen_random_uuid();
    w jsonb; party jsonb; report jsonb; r record; v_status text; saved jsonb;
begin
    insert into public.insurance_companies(id,name) values(c,'ATOMIC-TEST-' || c);
    insert into public.insurance_policies(id,company_id,policy_name,policy_number,insurer,start_date,end_date)
    values(p,c,'Atomic test',p::text,'Test','2026-01-01','2026-12-31');
    insert into public.insurance_declarations(id,declaration_number,policy_id,company_id,source_type,status)
    values(d,'DEC-2099-' || (floor(random()*900000000)+100000000)::bigint,p,c,'api','pending_review');
    insert into public.insurance_shipments(id,declaration_id,insured_value,currency,extra_data)
    values(s,d,10000.55,'USD','{"insured_name":"ATOMIC TEST PARTY"}');
    insert into public.insurance_documents(id,declaration_id,shipment_id,document_type,file_name,content_type,storage_bucket,storage_path,file_sha256)
    values(screenshot,d,s,'other','test.png','image/png','test',screenshot::text,repeat('a',64)),
          (report_doc,d,null,'other','test.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document','test',report_doc::text,repeat('b',64));
    party := jsonb_build_object('name','ATOMIC TEST PARTY','preliminary',jsonb_build_object('query','ATOMIC TEST PARTY','screened_at',now()-interval '2 minutes'),
      'evidence',jsonb_build_object('document_id',screenshot,'sha256',repeat('a',64)),
      'review',jsonb_build_object('result','no_match','reviewer','Test','reviewed_at',now()-interval '1 minute'));
    report := jsonb_build_object('document_id',report_doc,'sha256',repeat('b',64),'case_fingerprint','server-verified-test',
      'generated_at',now(),'screening_snapshot',jsonb_build_object(s::text,jsonb_build_object('insured_name',party)));
    w := jsonb_build_object('parties',jsonb_build_object('insured_name',party),'report',report);
    update public.insurance_shipments set extra_data=extra_data || jsonb_build_object('sanctions_workflow',w,'sanctions_screening',jsonb_build_object('status','completed')) where id=s;
    begin
      perform * from public.confirm_insurance_underwriting_atomic(d,0.15,w,repeat('b',64),10000.55,'USD');
      raise exception 'TEST FAILED: undownloaded report accepted';
    exception when sqlstate '22023' then null; end;
    w := jsonb_set(w,'{report,downloaded_at}',to_jsonb(now()));
    update public.insurance_shipments set extra_data=jsonb_set(extra_data,'{sanctions_workflow}',w) where id=s;
    -- A rejected final step must also roll back the terms written by step one.
    saved := w;
    w := jsonb_set(w,'{parties,insured_name,review,result}','"possible_match"');
    w := jsonb_set(w,array['report','screening_snapshot',s::text],w->'parties');
    update public.insurance_shipments set extra_data=jsonb_set(extra_data,'{sanctions_workflow}',w) where id=s;
    begin
      perform * from public.confirm_insurance_underwriting_atomic(d,0.15,w,repeat('b',64),10000.55,'USD');
      raise exception 'TEST FAILED: unresolved match accepted';
    exception when sqlstate '22023' then null; end;
    if exists(select 1 from public.insurance_shipments where id=s and extra_data ? 'underwriting_terms') then
      raise exception 'TEST FAILED: terms were partially committed';
    end if;
    w := saved;
    update public.insurance_shipments set extra_data=jsonb_set(extra_data,'{sanctions_workflow}',w) where id=s;
    insert into public.insurance_shipments(id,declaration_id) values(second_shipment,d);
    begin
      perform * from public.confirm_insurance_underwriting_atomic(d,0.15,w,repeat('b',64),10000.55,'USD');
      raise exception 'TEST FAILED: multiple shipments accepted';
    exception when sqlstate '22023' then null; end;
    delete from public.insurance_shipments where id=second_shipment;
    begin
      perform * from public.confirm_insurance_underwriting_atomic(d,0.15,'{}',repeat('b',64),10000.55,'USD');
      raise exception 'TEST FAILED: stale snapshot accepted';
    exception when sqlstate '40001' then null; end;
    select * into r from public.confirm_insurance_underwriting_atomic(d,0.15,w,repeat('b',64),10000.55,'USD');
    if not r.applied or r.premium <> 15.00 then raise exception 'TEST FAILED: wrong premium'; end if;
    select status into v_status from public.insurance_declarations where id=d;
    if v_status <> 'confirmed' then raise exception 'TEST FAILED: not confirmed'; end if;
    select * into r from public.confirm_insurance_underwriting_atomic(d,0.15,w,repeat('b',64),10000.55,'USD');
    if r.applied then raise exception 'TEST FAILED: duplicate confirmation applied'; end if;
    begin
      perform * from public.confirm_insurance_underwriting_atomic(d,0.25,w,repeat('b',64),10000.55,'USD');
      raise exception 'TEST FAILED: conflicting rate accepted';
    exception when sqlstate '23505' then null; end;
    begin
      update public.insurance_shipments set extra_data=jsonb_set(extra_data,'{sanctions_workflow}','{}') where id=s;
      raise exception 'TEST FAILED: confirmed screening editable';
    exception when sqlstate '23505' then null; end;
end $$;
select 'PASS: download guard, stale snapshot, match guard, atomic rollback, premium, confirmed state, idempotency, conflicting rate, immutable screening' as result;
rollback;
