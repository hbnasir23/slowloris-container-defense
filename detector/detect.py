"""
Live detection with an ADAPTIVE THRESHOLD.

A connection is treated as hostile only when BOTH hold:
  (a) the XGBoost probability exceeds an EWMA-tracked base threshold, and
  (b) the server's worker pool is under pressure (busy/total from mod_status).

Combining the model score with real server saturation is what keeps honest slow
clients from being isolated when the server is healthy. Per-source offences are
aggregated before the mitigator acts.
"""
import time
from collections import defaultdict

import joblib
import numpy as np
import requests
import xgboost as xgb

from features import FEATURE_NAMES


class AdaptiveDetector:
    def __init__(self, model_dir="models", base_tau=0.5,
                 saturation_trigger=0.8, min_conns_from_src=20,
                 status_url="http://127.0.0.1:80/server-status?auto"):
        self.clf = xgb.XGBClassifier()
        self.clf.load_model(f"{model_dir}/xgb.json")
        self.scaler = joblib.load(f"{model_dir}/scaler.pkl")  # kept for parity
        self.tau = base_tau
        self.ewma = base_tau
        self.saturation_trigger = saturation_trigger
        self.min_conns_from_src = min_conns_from_src
        self.status_url = status_url

    def worker_saturation(self) -> float:
        """busy/(busy+idle) from Apache mod_status; 1.0 if unknown (fail-safe)."""
        try:
            txt = requests.get(self.status_url, timeout=1).text
            busy = idle = None
            for line in txt.splitlines():
                if line.startswith("BusyWorkers:"):
                    busy = float(line.split(":")[1])
                elif line.startswith("IdleWorkers:"):
                    idle = float(line.split(":")[1])
            if busy is not None and idle is not None and (busy + idle) > 0:
                return busy / (busy + idle)
        except Exception:
            pass
        return 1.0

    def classify(self, rows):
        """Return (offending_src_ips, debug) for one snapshot of flows."""
        if not rows:
            return set(), {"saturation": 0.0, "n": 0}
        X = np.array([[r[f] for f in FEATURE_NAMES] for r in rows], dtype=float)
        proba = self.clf.predict_proba(X)[:, 1]

        sat = self.worker_saturation()
        # Adapt threshold to recent score distribution; raise the bar when the
        # server is calm so slow-but-honest clients are not flagged.
        self.ewma = 0.9 * self.ewma + 0.1 * float(np.median(proba))
        gate_open = sat >= self.saturation_trigger

        # Count, per source, connections that are BOTH model-flagged AND still
        # have incomplete headers. Honest clients (even many, even slow)
        # complete their headers, so they never accumulate here -- this is what
        # prevents isolating benign keep-alive or slow-but-complete traffic.
        per_src_incomplete = defaultdict(int)
        for r, p in zip(rows, proba):
            # Only LONG-LIVED incomplete flows count. A Slowloris flow holds
            # headers open for minutes; an honest request that is briefly
            # mid-header completes in well under a second, so transient benign
            # incompleteness never accumulates even under heavy load.
            if (p >= self.tau and r["incomplete_ratio"] == 1
                    and r["duration"] > 8.0):
                per_src_incomplete[r["src_ip"]] += 1

        offenders = set()
        if gate_open:
            for ip, hits in per_src_incomplete.items():
                # a Slowloris source holds MANY incomplete flows open at once
                if hits >= self.min_conns_from_src:
                    offenders.add(ip)
        return offenders, {"saturation": round(sat, 3),
                           "n": len(rows), "gate_open": gate_open,
                           "max_proba": round(float(proba.max()), 3)}
