# Vercel and Render deployment

The web client is hosted on Vercel and the FastAPI service is hosted separately
on Render. Supabase remains the database, document storage, and authentication
provider. The `render.yaml` Blueprint creates only the API service; it does not
create or migrate a Supabase database.

## Render API service

Create a Blueprint in the Render Dashboard from the GitHub repository
`Cheung-Ying-Sui/risk_monitor`, using the repository root and its `render.yaml`.
The service runs `api.main:app`, checks `/health`, and starts on Render's
provided port. The Blueprint uses the Free plan, which may spin down after
inactivity and introduce a cold-start delay.

Set these values in the Render environment settings; never commit them:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | The project's Supabase URL |
| `SUPABASE_SECRET_KEY` | A server-only Supabase secret/service-role key |
| `API_AUTHORIZED_USER_IDS` | Comma-separated Supabase Auth user UUIDs permitted to use the API |
| `CORS_ALLOWED_ORIGINS` | Local origins and the active Vercel frontend origin |
| `CORS_ALLOWED_ORIGIN_REGEX` | `^https://risk-monitor-frontend-[a-z0-9]+-zys18476615082-7273\.vercel\.app$` for this Vercel project's generated preview hosts |

Create each account in Supabase Auth, then add its Auth user UUID to the API
allowlist. An authenticated but non-allowlisted user receives HTTP 403. The
allowlist currently grants every listed user access to the same platform data;
it is not per-company or per-record authorization.

The API validates every Bearer access token against Supabase Auth. The
server-only Supabase key is used only by Render and must never be configured as
a `NEXT_PUBLIC_*` variable. `/health` is intentionally public for Render's
health check. CORS is browser policy, not an authorization boundary.

## Vercel frontend

Set these environment variables for the Vercel Preview environment while
testing:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | The deployed Render service's HTTPS URL, without a trailing slash |
| `NEXT_PUBLIC_SUPABASE_URL` | The same Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | The project's public anon/publishable key; never use a secret/service-role key |

Redeploy the Preview after changing environment variables. The frontend uses
Supabase Auth email/password login and sends its access token to every API
request. The auth gate covers the application pages; Render independently
checks the token and allowlist on every business API route.

## Database and production checklist

- Apply only the reviewed `supabase/migrations/` files that are needed by the
  current application, using the Supabase migration workflow. Deploying the API
  does not apply migrations.
- Configure any optional external provider keys on Render only, according to
  the features being enabled (for example AIS, sanctions research, or document
  storage settings).
- Keep the Vercel Preview protected during testing. Do not move the frontend
  to a public Production domain until the API allowlist, Supabase Auth users,
  CORS, storage, and required migrations have been verified.
- For production uptime, select an always-on Render plan after reviewing its
  current price; the Blueprint intentionally does not provision a paid plan.
