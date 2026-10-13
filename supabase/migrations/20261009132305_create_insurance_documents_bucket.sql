-- Private bucket used by the server-side insurance document workflow.
insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit
)
values (
    'insurance-documents',
    'insurance-documents',
    false,
    20971520
)
on conflict (id) do update
set name = excluded.name,
    public = excluded.public,
    file_size_limit = excluded.file_size_limit;
