#!/usr/bin/env python3
"""
Samples legitimate-user experience against the victim once per second and logs
success + latency with a phase label. This produces the headline
"service availability over time" figure. Run from the host.
"""
import csv
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8080/"
OUT = "results/availability.csv"


def phase_at(t0, marks):
    # marks: list of (elapsed_seconds, phase_name) breakpoints
    el = time.time() - t0
    ph = marks[0][1]
    for sec, name in marks:
        if el >= sec:
            ph = name
    return ph


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
    # elapsed -> phase name (passed as "sec:name,sec:name,...")
    marks = [(0, "baseline")]
    if len(sys.argv) > 2:
        marks = [(float(s.split(":")[0]), s.split(":")[1])
                 for s in sys.argv[2].split(",")]
    t0 = time.time()
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "elapsed", "phase", "ok", "latency_ms"])
        while time.time() - t0 < duration:
            start = time.time()
            ok, lat = 0, ""
            try:
                r = urllib.request.urlopen(URL, timeout=4)
                ok = 1 if r.status == 200 else 0
                lat = round((time.time() - start) * 1000, 1)
            except Exception:
                ok = 0
                lat = round((time.time() - start) * 1000, 1)
            w.writerow([round(time.time(), 3), round(time.time() - t0, 1),
                        phase_at(t0, marks), ok, lat])
            f.flush()
            time.sleep(max(0, 1.0 - (time.time() - start)))
    print("[probe] done ->", OUT)


if __name__ == "__main__":
    main()
