"""
Detector entry point. MODE env selects behaviour:

  idle    : do nothing (default; lab is up but detector passive)
  collect : sniff and write auto-labelled feature rows to data/dataset.csv
            (attacker IP -> label 1, everything else -> label 0)
  defend  : load the trained model and run the full closed loop
            (monitor -> classify -> isolate -> cooldown/restore),
            logging a timeline for the availability/latency figures.
"""
import csv
import os
import threading
import time

from features import FEATURE_NAMES
from monitor import Monitor

MODE = os.environ.get("MODE", "idle")
ATTACKER_IP = os.environ.get("ATTACKER_IP", "172.28.0.20")
ATTACKER_CONTAINER = os.environ.get("ATTACKER_CONTAINER", "sl_attacker")
VICTIM_CONTAINER = os.environ.get("VICTIM_CONTAINER", "sl_victim")
DATASET = "data/dataset.csv"
TIMELINE = "results/timeline.csv"


def run_collect():
    os.makedirs("data", exist_ok=True)
    new = not os.path.exists(DATASET)
    f = open(DATASET, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(FEATURE_NAMES + ["src_ip", "label"])

    def on_snapshot(rows, ts):
        for r in rows:
            label = 1 if r["src_ip"] == ATTACKER_IP else 0
            w.writerow([r[k] for k in FEATURE_NAMES] + [r["src_ip"], label])
        f.flush()
        if rows:
            print(f"[collect] +{len(rows)} rows", flush=True)

    Monitor(period=2.0).run(on_snapshot)


def run_defend():
    import docker
    from detect import AdaptiveDetector
    from mitigator import Mitigator

    os.makedirs("results", exist_ok=True)
    det = AdaptiveDetector()
    try:
        dc = docker.from_env()
    except Exception:
        dc = None
    mit = Mitigator(docker_client=dc, attacker_container=ATTACKER_CONTAINER,
                    victim_container=VICTIM_CONTAINER,
                    cooldown=float(os.environ.get("COOLDOWN", "30")))

    tl = open(TIMELINE, "w", newline="")
    tw = csv.writer(tl)
    tw.writerow(["ts", "saturation", "max_proba", "n_flows",
                 "n_offenders", "gate_open"])

    state = {"suppress_until": 0.0}

    def on_snapshot(rows, ts):
        offenders, dbg = det.classify(rows)
        # Grace period after a reclaim: a container restart briefly stalls
        # in-flight legitimate requests, which can look slow. Do not trigger
        # new mitigations while the service is still recovering, to avoid
        # falsely isolating benign clients.
        acted = 0
        if ts >= state["suppress_until"]:
            for ip in offenders:
                mit.offend(ip)
                acted += 1
            if acted:
                state["suppress_until"] = ts + 45.0
        mit.tick()
        tw.writerow([f"{ts:.3f}", dbg.get("saturation"), dbg.get("max_proba"),
                     dbg.get("n"), len(offenders), dbg.get("gate_open")])
        tl.flush()

    Monitor(period=2.0).run(on_snapshot)


if __name__ == "__main__":
    print(f"[run] MODE={MODE}", flush=True)
    if MODE == "collect":
        run_collect()
    elif MODE == "defend":
        run_defend()
    else:
        while True:
            time.sleep(3600)
