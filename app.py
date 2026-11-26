import csv
import io
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
from flask import Flask, jsonify, render_template_string, send_file

app = Flask(__name__)

DB_PATH = Path(os.environ.get("METRICS_DB", "/tmp/metrics.sqlite3"))
RETENTION_DAYS = max(1, int(os.environ.get("METRICS_RETENTION_DAYS", "1")))
SAMPLE_LOCK = threading.Lock()
PROCESS = psutil.Process()
CPU_COUNT = psutil.cpu_count(logical=True) or 1

# Prime psutil's non-blocking CPU counters.
psutil.cpu_percent(interval=None)
PROCESS.cpu_percent(interval=None)


def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect_db() as db:
        # Incremental auto-vacuum returns freed pages to the filesystem as
        # old samples are removed. A one-time VACUUM migrates existing DBs.
        if db.execute("PRAGMA auto_vacuum").fetchone()[0] != 2:
            db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            db.execute("VACUUM")
        db.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                system_cpu REAL NOT NULL,
                app_cpu REAL NOT NULL,
                system_ram REAL NOT NULL,
                app_ram_mb REAL NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_samples_id ON samples(id)")


def collect_sample():
    with SAMPLE_LOCK:
        system_cpu = psutil.cpu_percent(interval=None)
        app_cpu = PROCESS.cpu_percent(interval=None) / CPU_COUNT
        system_ram = psutil.virtual_memory().percent
        app_ram_mb = PROCESS.memory_info().rss / (1024 * 1024)
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat(timespec="seconds")
        cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")

        with connect_db() as db:
            db.execute(
                """
                INSERT INTO samples
                    (timestamp, system_cpu, app_cpu, system_ram, app_ram_mb)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp, system_cpu, app_cpu, system_ram, app_ram_mb),
            )
            db.execute("DELETE FROM samples WHERE timestamp < ?", (cutoff,))
            db.execute("""
                DELETE FROM samples
                WHERE id NOT IN (
                    SELECT id FROM samples ORDER BY id DESC LIMIT 1500
                )
            """)
            db.execute("PRAGMA incremental_vacuum")


def get_recent_samples(limit=60):
    with connect_db() as db:
        rows = db.execute("""
            SELECT timestamp, system_cpu, app_cpu, system_ram, app_ram_mb
            FROM (
                SELECT * FROM samples ORDER BY id DESC LIMIT ?
            )
            ORDER BY id ASC
        """, (limit,)).fetchall()
    return [dict(row) for row in rows]


@app.after_request
def add_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/metrics")
def metrics():
    collect_sample()
    return jsonify(get_recent_samples())


@app.get("/api/metrics.csv")
def metrics_csv():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["timestamp", "system_cpu", "app_cpu", "system_ram", "app_ram_mb"])
    for sample in get_recent_samples(limit=1500):
        writer.writerow([
            sample["timestamp"], sample["system_cpu"], sample["app_cpu"],
            sample["system_ram"], sample["app_ram_mb"],
        ])

    content = io.BytesIO(output.getvalue().encode("utf-8"))
    content.seek(0)
    filename = f"metrics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return send_file(content, mimetype="text/csv", as_attachment=True, download_name=filename)


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Resource Monitor</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #10141c; color: #e8edf5; }
    main { max-width: 1050px; margin: 36px auto; padding: 0 20px; }
    h1 { margin-bottom: 6px; }
    .muted { color: #9aa8bb; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
             gap: 14px; margin: 24px 0; }
    .card, .panel { background: #1a2230; border: 1px solid #2a3547;
                    border-radius: 12px; padding: 18px; }
    .value { display: block; font-size: 1.8rem; font-weight: 700; margin-top: 8px; }
    .panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
              gap: 14px; }
    canvas { width: 100%; }
    #status { min-height: 1.5em; }
    a { color: #8fc2ff; }
  </style>
</head>
<body>
<main>
  <h1>Local Resource Monitor</h1>
  <div class="muted">Live system and app metrics · sampled every 2 seconds</div>
  <p><a href="/api/metrics.csv">Download metrics as CSV</a></p>

  <section class="cards">
    <div class="card">System CPU<span class="value" id="systemCpu">—</span></div>
    <div class="card">App CPU (normalized)<span class="value" id="appCpu">—</span></div>
    <div class="card">System RAM used<span class="value" id="systemRam">—</span></div>
    <div class="card">App memory (RSS)<span class="value" id="appRam">—</span></div>
  </section>

  <div id="status" class="muted" role="status">Waiting for first sample…</div>

  <section class="panels">
    <div class="panel"><h2>CPU (%)</h2><canvas id="cpuChart"></canvas></div>
    <div class="panel"><h2>Memory</h2><canvas id="ramChart"></canvas></div>
  </section>
</main>

<script>
  const labels = [];
  const cpuChart = new Chart(document.getElementById("cpuChart"), {
    type: "line",
    data: { labels, datasets: [
      { label: "System CPU", data: [], borderColor: "#62a8ff", tension: 0.25 },
      { label: "App CPU", data: [], borderColor: "#ffb454", tension: 0.25 }
    ]},
    options: { animation: false, scales: { y: { beginAtZero: true, suggestedMax: 100 } } }
  });

  const ramChart = new Chart(document.getElementById("ramChart"), {
    type: "line",
    data: { labels, datasets: [
      { label: "System RAM (%)", data: [], borderColor: "#68d391",
        yAxisID: "percent", tension: 0.25 },
      { label: "App RSS (MB)", data: [], borderColor: "#e879f9",
        yAxisID: "megabytes", tension: 0.25 }
    ]},
    options: { animation: false, scales: {
      percent: { type: "linear", position: "left", beginAtZero: true, max: 100 },
      megabytes: { type: "linear", position: "right", beginAtZero: true,
                   grid: { drawOnChartArea: false } }
    }}
  });

  function timeLabel(value) {
    return new Date(value).toLocaleTimeString();
  }

  async function refresh() {
    try {
      const response = await fetch("/api/metrics", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const samples = await response.json();
      if (!samples.length) return;

      const latest = samples[samples.length - 1];
      document.getElementById("systemCpu").textContent = `${latest.system_cpu.toFixed(1)}%`;
      document.getElementById("appCpu").textContent = `${latest.app_cpu.toFixed(1)}%`;
      document.getElementById("systemRam").textContent = `${latest.system_ram.toFixed(1)}%`;
      document.getElementById("appRam").textContent = `${latest.app_ram_mb.toFixed(1)} MB`;
      document.getElementById("status").textContent = `Last sample: ${timeLabel(latest.timestamp)}`;

      const times = samples.map(s => timeLabel(s.timestamp));
      cpuChart.data.labels = times;
      cpuChart.data.datasets[0].data = samples.map(s => s.system_cpu);
      cpuChart.data.datasets[1].data = samples.map(s => s.app_cpu);
      cpuChart.update();

      ramChart.data.labels = times;
      ramChart.data.datasets[0].data = samples.map(s => s.system_ram);
      ramChart.data.datasets[1].data = samples.map(s => s.app_ram_mb);
      ramChart.update();
    } catch (error) {
      document.getElementById("status").textContent = `Could not load metrics: ${error.message}`;
    }
  }

  refresh();
  setInterval(refresh, 2000);
</script>
</body>
</html>
"""


# Initialize the database for both the development server and production WSGI.
init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
