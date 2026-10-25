#!/usr/bin/env bash
# End-to-end experiment driver for the Slowloris containment testbed.
# Produces the real dataset, trains the model, runs the closed-loop defense
# experiment, and emits every figure/table the paper references.
#
# Usage:  bash experiments/run_all.sh
# Requires: Docker + Docker Compose v2. Everything runs locally; no external hosts.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data results

DC="docker compose"
ATTACK="python slowloris_lab.py --target victim --sockets 200 --interval 12"
BENIGN_FAST="locust -f locustfile.py --headless -u 60 -r 10 -H http://victim:80"
BENIGN_SLOW="python slow_benign.py --target victim --clients 15"

echo "==> [1/6] Build images"
$DC build

echo "==> [2/6] Collect dataset (benign + slow-benign + attack, auto-labelled)"
MODE=collect $DC up -d victim attacker benign detector
sleep 8
# generate benign load (fast + honest-slow) for 60s, attack overlaps 20-80s
$DC exec -d benign bash -c "$BENIGN_FAST -t 90s"
$DC exec -d benign bash -c "$BENIGN_SLOW --duration 90"
sleep 20
$DC exec -d attacker bash -c "$ATTACK --duration 60"
sleep 80
echo "    dataset rows:"; wc -l data/dataset.csv || true
$DC stop attacker benign detector

echo "==> [3/6] Train models (XGBoost + RF + LR, SHAP)"
$DC run --rm --no-deps detector python train.py --data data/dataset.csv

echo "==> [4/6] Closed-loop defense experiment"
MODE=defend COOLDOWN=30 $DC up -d victim attacker benign detector
sleep 6
# availability probe + benign load for the whole window; attack fires at t=40s
python experiments/availability_probe.py 200 "0:baseline,40:attack,100:mitigated,160:recovered" &
PROBE=$!
$DC exec -d benign bash -c "$BENIGN_FAST -t 190s"
sleep 40
echo "    launching attack..."
$DC exec -d attacker bash -c "$ATTACK --duration 60"
wait $PROBE

echo "==> [5/6] Collect logs"
$DC logs detector > results/detector.log 2>&1 || true
cp -f results/actions.csv results/actions.csv 2>/dev/null || true

echo "==> [6/6] Generate figures & tables"
$DC run --rm --no-deps detector python plots.py || python experiments/plots.py

echo "==> DONE. See results/ for metrics.json, *.png, *.csv"
$DC stop || true
