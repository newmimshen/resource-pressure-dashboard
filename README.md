# Resource Pressure Dashboard

A lightweight Python/Flask dashboard for viewing system and application CPU and memory usage. It stores up to 1,500 recent samples in SQLite and renders live CPU and memory charts.

## Metrics

- **System CPU:** CPU utilization reported by `psutil`
- **App CPU:** CPU utilization of the Python process, normalized by logical CPU count
- **System RAM:** percentage of system memory used
- **App memory:** process resident set size (RSS) in megabytes
- **SQLite:** the `/api/metrics` endpoint stores and reads samples from `metrics.sqlite3` or `$METRICS_DB`

## Run locally

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
```

Linux or macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the server

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

The server binds to `0.0.0.0` in this configuration, so it is reachable on your local network if network/firewall rules permit it. For isolated testing, keep your browser and proxy traffic local and use Render for public testing only with authorization.

## Test with Burp Suite

1. Open Burp Suite and use it as a proxy.
2. Configure a browser or Burp's built-in browser to use the proxy.
3. Add the application URL to **Target > Scope**.
4. Browse the app and issue requests to:
   - `/`
   - `/api/metrics`
5. In Burp Repeater or Intruder, send authorized test requests and observe CPU/RAM history.
6. Use Intruder at low request rates initially. Stop immediately if the host becomes unstable.

Only test systems you own or are explicitly authorized to test.

## API

### `GET /`

Returns the dashboard HTML.

### `GET /api/metrics`

Collects a new sample and returns up to 60 of the newest samples:

```json
[
  {
    "timestamp": "2026-11-26T12:00:00+00:00",
    "system_cpu": 12.5,
    "app_cpu": 0.4,
    "system_ram": 48.2,
    "app_ram_mb": 34.1
  }
]

```

## Deploy on Render

### Create the service

1. Push this repository to GitHub.
2. In Render, choose **New > Web Service**.
3. Connect the repository.
4. Use these settings:

| Setting | Value |
|---|---|
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT app:app` |
| Health check path | `/` |

5. Create the service and open the generated Render URL.

For a public test service, consider adding authentication and IP allowlisting through a reverse proxy or access-control feature. SQLite data is ephemeral and should not be used as persistent storage on Render.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Local or Render server port |
| `METRICS_DB` | `/tmp/metrics.sqlite3` | SQLite database path |

Example:

```bash
METRICS_DB=/tmp/metrics.sqlite3 python app.py
```

## Notes

- Chart.js is loaded from a CDN, so the browser needs access to `cdn.jsdelivr.net`.
- CPU and memory figures are snapshots, not long-term host guarantees.
- Container/platform measurements may differ from bare-metal or virtual-machine measurements.
- The database is retained for at most 1,500 samples. The dashboard displays at most 60 in one chart update.
- A public Render service may be affected by platform quotas and resource limits.
