# Resource Pressure Dashboard

A lightweight Python/Flask dashboard for viewing system and application CPU and memory usage. It records samples in SQLite, removes samples older than the configured retention period, and provides a CSV download.

## Metrics and retention

- **System CPU:** CPU utilization reported by `psutil`
- **App CPU:** CPU utilization of the Python process, normalized by logical CPU count
- **System RAM:** percentage of system memory used
- **App memory:** process resident set size (RSS) in megabytes
- **SQLite retention:** by default, samples older than one day are deleted as new samples are collected. The database is capped at 1,500 samples and uses incremental vacuuming to reclaim freed pages.
- **CSV export:** download the retained history from the dashboard or `GET /api/metrics.csv`. The CSV is generated in memory and is not saved on the server.

## Run locally

```bash
python -m venv .venv
```

Activate the virtual environment (Linux/macOS: `source .venv/bin/activate`; Windows: `.venv\\Scripts\\activate`), then:

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## CSV export

Click **Download metrics as CSV** on the dashboard or request:

```text
GET /api/metrics.csv
```

The response is a downloadable CSV with `timestamp`, `system_cpu`, `app_cpu`, `system_ram`, and `app_ram_mb` columns. It exports up to 1,500 retained samples. Because the CSV is generated in memory and streamed as a response, it does not create accumulating export files on the server.

## Test with Burp Suite

1. Configure a browser or Burp's built-in browser to use Burp as a proxy.
2. Add the application URL to **Target > Scope**.
3. Browse the dashboard and inspect `/api/metrics` and `/api/metrics.csv`.
4. Use Repeater or low-rate Intruder requests only against this app or another system you are authorized to test. Stop if the host becomes unstable.

## Deploy on Render

Create a Render **Web Service**, connect this repository, and configure:

| Setting | Value |
|---|---|
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT app:app` |
| Health check path | `/` |

The SQLite database defaults to `/tmp/metrics.sqlite3`. Render's local filesystem is ephemeral; it can be cleared on restart or deployment. If the service is public, consider access controls and keep testing authorized and appropriately scoped.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Server port (Render sets this automatically) |
| `METRICS_DB` | `/tmp/metrics.sqlite3` | SQLite database location |
| `METRICS_RETENTION_DAYS` | `1` | Age limit for stored samples; values below 1 are treated as 1 |

Example to retain samples for three days:

```bash
METRICS_RETENTION_DAYS=3 python app.py
```

## Notes

- Chart.js is loaded from a CDN, so the browser needs access to `cdn.jsdelivr.net`.
- Metrics are snapshots; container/platform values may differ from host-level values.
- Cleanup occurs when a new sample is collected (the dashboard polls every two seconds), so expired rows are pruned on the next sample.
