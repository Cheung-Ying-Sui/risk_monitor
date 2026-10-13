# Risk Monitor

Maritime risk monitoring workspace for vessel tracking, risk-zone matching, sanctions screening, and supporting analysis scripts.

## Directory Layout

| Path | Purpose |
| --- | --- |
| `risk_monitor/` | Main vessel monitoring application code, Streamlit dashboard, API clients, and Supabase repositories. |
| `risk_monitor/navigation/` | Baseline ETA engine and MVP destination port reference data. |
| `risk_zones/` | Risk-zone geometry processing, validation, GeoJSON generation, and anchor review data. |
| `scripts/` | Scheduled or operational jobs, including vessel position fetching and risk matching. |
| `tests/` | Test modules for the main application and risk-zone utilities. |
| `supabase/migrations/` | Supabase/Postgres migration SQL. |
| `static/` | Shared static assets used by dashboards and geography processing. |
| `docs/` | Project notes and audit documentation. |
| `legacy/` | Older dashboard prototypes and backup frontends kept for reference. |
| `制裁筛查模块/` | Sanctions screening module and OFAC sync code. |
| `获取船舶地理位置【已开发完成】/` | Earlier vessel-location collection implementation. |
| `船舶坐标管理、历史轨迹回放/` | Historical track playback scripts and generated HTML output. |
| `cnpi_spider_data/`, `IUMI_data/`, `码头拥堵模型/`, `船舶估值模块/` | Standalone data, model, and analysis modules. |

## Common Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the main Streamlit dashboard:

```bash
streamlit run risk_monitor/vessel_dashboard.py
```

Run operational jobs:

```bash
python scripts/fetch_vessel_positions_job.py
python scripts/run_risk_matching_job.py
```

Chinaports vessel search and the position collector prefer IMO when available.
The website search endpoint resolves IMO to MMSI first; `shipInfo` then returns
the vessel position. Without IMO the client queries MMSI directly. Returned
identifiers must match before persistence, and ambiguous IMO results are rejected.

Insurance declarations carry IMO identifiers. Confirming a declaration now tries
to activate AIS tracking automatically. If the IMO is already linked to a vessel
with MMSI in `core.vessels`, the existing 10-minute position collector can track
it. For IMO-only vessels, configure both `DEEPSEEK_API_KEY` and
`BRAVE_SEARCH_API_KEY` on the API server. DeepSeek then calls the backend's live
web-search tool and extracts an MMSI only when the cited search snippet includes
the declared IMO and MMSI. Chinaports checks the identity before human confirmation;
an empty, mismatched, or unverifiable suggestion never creates a tracked vessel.
Without the search key, candidate lookup reports unavailable instead of guessing.
Alternatively, configure
`DATALASTIC_API_KEY` on the API server for a licensed direct IMO lookup and AIS
position fetch. The scheduled vessel-position workflow also needs that GitHub
secret to keep refreshing insured vessels through Datalastic. Keys stay
server-side; model, search, and AIS provider requests may incur charges. To inspect or backfill
declarations confirmed before this integration:

```bash
python scripts/sync_insured_vessel_tracking.py
python scripts/sync_insured_vessel_tracking.py --apply
```

The first command is read-only. The second activates tracking and, if configured,
queries the provider. If no provider is configured and the IMO is not already
mapped to MMSI, the UI reports that status instead of inventing a live position.

Run tests:

```bash
python -m pytest tests
```

## Environment

Copy `.env.example` and provide the required Supabase and Chinaports values locally. Do not commit real secrets.

## Web deployment

The Next.js frontend and FastAPI API are deployed separately; Supabase remains
the data and authentication provider. See [docs/deployment.md](docs/deployment.md)
for the Render Blueprint, Vercel environment variables, API authentication, and
production readiness checklist.
