# Detection and Automated Mitigation of Slowloris in Containerized Environments

SE-401 project. A **closed-loop, container-native** defense against the Slowloris
application-layer DoS attack: monitor live connections, classify with
XGBoost + an adaptive threshold, isolate the offender through the container
runtime, and automatically restore service after a cooldown.

> **Ethics / safety.** Everything here runs inside an isolated Docker network
> against a **victim container you host yourself**. The attack generator refuses
> any target outside the lab subnet (`172.28.0.0/16`) or localhost. Never point
> it at a system you do not own.

## Architecture

```
          ┌──────────────── Docker host (isolated bridge) ───────────────┐
 benign ──┤  fast + slow-but-honest clients                              │
attacker ─┤  lab-only Slowloris ─────────► victim (Apache, 50 workers)   │
          │                                     ▲                         │
          │   detector (shares victim netns)    │ sniff eth0              │
          │     monitor → classify(XGBoost+τ) → isolate → restore         │
          │     iptables / conntrack / docker disconnect  + cooldown      │
          └───────────────────────────────────────────────────────────────┘
```

## Layout

| Path | What it is |
|---|---|
| `docker-compose.yml` | the four-service isolated testbed |
| `victim/` | intentionally small Apache (the target) |
| `attacker/slowloris_lab.py` | lab-only Slowloris (subnet-locked) |
| `benign/` | Locust (fast) + `slow_benign.py` (honest-slow hard negatives) |
| `detector/features.py` | per-connection flow tracking + L7 feature set |
| `detector/monitor.py` | Scapy sniffer → feature snapshots |
| `detector/train.py` | XGBoost + RandomForest + LogReg, metrics, SHAP |
| `detector/detect.py` | live inference + adaptive (saturation-gated) threshold |
| `detector/mitigator.py` | isolate + cooldown/restore state machine |
| `detector/run.py` | entry point: `idle` / `collect` / `defend` |
| `experiments/run_all.sh` | one command: data → train → defense → figures |
| `experiments/make_results_tex.py` | injects real numbers into the paper |
| `paper/paper.tex` | full IEEE paper (results auto-filled from the run) |

## Run it (needs Docker + Docker Compose v2)

```bash
bash experiments/run_all.sh          # ~5 min: builds, collects, trains, defends
python3 experiments/make_results_tex.py   # pull real numbers into the paper
cd paper && pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper
```

Outputs land in `results/`:
`metrics.json`, `summary.json`, `actions.csv`, `timeline.csv`,
`availability.csv`, and the figures `fig_*.png`.

## How the paper stays honest

`paper/paper.tex` reads `paper/results_generated.tex`. Before you run anything
every number shows **TBD**; `make_results_tex.py` overwrites that file with the
real figures from `results/`. Nothing in the Results section is hand-typed, so
the paper can never report a number the experiments did not produce.

## Experiment arms (for the comparison table)

Rebuild the victim with `mod_reqtimeout` enabled to measure the static-defense
arm, and disable mitigation (`MODE=idle`) to measure the no-defense baseline.
Vary `--sockets` / `--interval` / `--jitter` on the attacker for the robustness
study.
```
```
