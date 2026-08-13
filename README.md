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

Run tests:

```bash
python -m pytest tests
```

## Environment

Copy `.env.example` and provide the required Supabase and Chinaports values locally. Do not commit real secrets.
