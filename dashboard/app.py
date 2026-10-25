"""
Live demo dashboard for the Slowloris containment system.

Serves a single page that polls /api/state and renders, in real time:
  - legitimate-user service availability (from the host probe's CSV),
  - the victim's worker-pool saturation (live from Apache mod_status),
  - the detector's per-snapshot state (flows, max probability, offenders),
  - the automated action log (DROP / ISOLATE / RECLAIM / RESTORE).

It reads the SAME files the system already produces, so everything shown is
real live data from the running experiment -- not a mock-up.
"""
import csv
import os

import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__)

RESULTS = os.environ.get("RESULTS_DIR", "/app/results")
STATUS_URL = os.environ.get("STATUS_URL",
                            "http://victim:80/server-status?auto")


def tail_csv(path, n=400):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    try:
        with open(path) as f:
            rows = list(csv.DictReader(f))
        return rows[-n:]
    except Exception:
        return []


def worker_saturation():
    try:
        txt = requests.get(STATUS_URL, timeout=1).text
        busy = idle = None
        for line in txt.splitlines():
            if line.startswith("BusyWorkers:"):
                busy = float(line.split(":")[1])
            elif line.startswith("IdleWorkers:"):
                idle = float(line.split(":")[1])
        if busy is not None and idle is not None and (busy + idle) > 0:
            return {"busy": busy, "idle": idle,
                    "sat": round(busy / (busy + idle), 3), "up": True}
    except Exception:
        pass
    return {"busy": None, "idle": None, "sat": None, "up": False}


@app.route("/api/state")
def state():
    timeline = tail_csv(os.path.join(RESULTS, "timeline.csv"))
    avail = tail_csv(os.path.join(RESULTS, "availability.csv"))
    actions = tail_csv(os.path.join(RESULTS, "actions.csv"))
    latest = timeline[-1] if timeline else {}
    return jsonify({
        "worker": worker_saturation(),
        "latest": latest,
        "timeline": [
            {"t": i, "sat": float(r.get("saturation") or 0),
             "offenders": int(float(r.get("n_offenders") or 0)),
             "maxp": float(r.get("max_proba") or 0),
             "flows": int(float(r.get("n_flows") or 0))}
            for i, r in enumerate(timeline)
        ],
        "availability": [
            {"t": float(r.get("elapsed") or 0),
             "ok": int(float(r.get("ok") or 0)),
             "lat": float(r.get("latency_ms") or 0),
             "phase": r.get("phase", "")}
            for r in avail
        ],
        "actions": [
            {"ts": r.get("ts"), "action": r.get("action"),
             "target": r.get("target"), "detail": r.get("detail", "")}
            for r in actions if r.get("action")
        ],
    })


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
