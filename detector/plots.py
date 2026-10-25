"""
Turn the raw experiment CSVs in results/ into the figures and summary tables
the paper cites. Safe to run repeatedly. Emits PNGs + results/summary.json.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

R = "results"


def fig_availability():
    p = f"{R}/availability.csv"
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p)
    fig, ax1 = plt.subplots(figsize=(8, 4))
    # rolling success rate
    df["succ"] = df["ok"].rolling(5, min_periods=1).mean() * 100
    ax1.plot(df["elapsed"], df["succ"], color="#0a2a66", label="Success rate")
    ax1.set_xlabel("Time (s)"); ax1.set_ylabel("Success rate (%)")
    ax1.set_ylim(-5, 105)
    ax2 = ax1.twinx()
    ax2.plot(df["elapsed"], df["latency_ms"], color="#c0392b",
             alpha=0.4, label="Latency (ms)")
    ax2.set_ylabel("Latency (ms)")
    for _, name in df.groupby("phase")["elapsed"].min().items():
        pass
    # phase boundaries
    for ph, sub in df.groupby("phase"):
        ax1.axvline(sub["elapsed"].min(), ls="--", c="gray", lw=0.7)
        ax1.text(sub["elapsed"].min(), 102, ph, fontsize=7, rotation=0)
    ax1.set_title("Legitimate-user service availability over time")
    fig.tight_layout(); fig.savefig(f"{R}/fig_availability.png", dpi=150)
    plt.close(fig)
    return df


def fig_timeline():
    p = f"{R}/timeline.csv"
    if not os.path.exists(p):
        return
    df = pd.read_csv(p)
    df["t"] = df["ts"] - df["ts"].min()
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(df["t"], df["saturation"] * 100, color="#c0392b",
             label="Worker saturation (%)")
    ax1.set_ylabel("Worker saturation (%)"); ax1.set_xlabel("Time (s)")
    ax2 = ax1.twinx()
    ax2.step(df["t"], df["n_offenders"], color="#0a2a66",
             where="post", label="Offenders isolated")
    ax2.set_ylabel("Offenders isolated")
    ax1.set_title("Server saturation and detector response")
    fig.tight_layout(); fig.savefig(f"{R}/fig_timeline.png", dpi=150)
    plt.close(fig)


def fig_metrics():
    p = f"{R}/metrics.json"
    if not os.path.exists(p):
        return
    m = pd.DataFrame(json.load(open(p)))
    fig, ax = plt.subplots(figsize=(7, 4))
    m.set_index("model")[["precision", "recall", "f1"]].plot.bar(ax=ax)
    ax.set_ylim(0, 1.05); ax.set_ylabel("Score")
    ax.set_title("Detection performance by model")
    plt.xticks(rotation=0)
    fig.tight_layout(); fig.savefig(f"{R}/fig_metrics.png", dpi=150)
    plt.close(fig)


def fig_shap():
    p = f"{R}/shap_importance.csv"
    if not os.path.exists(p):
        return
    df = pd.read_csv(p).head(10)[::-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(df["feature"], df["mean_abs_shap"], color="#0a2a66")
    ax.set_xlabel("Mean |SHAP|"); ax.set_title("Top features (XGBoost)")
    fig.tight_layout(); fig.savefig(f"{R}/fig_shap.png", dpi=150)
    plt.close(fig)


def timing_summary(avail):
    """Derive time-to-detect / mitigate / recover from the action + probe logs."""
    out = {}
    ap = f"{R}/actions.csv"
    if os.path.exists(ap) and os.path.getsize(ap) > 0:
        try:
            a = pd.read_csv(ap)
        except Exception:
            a = pd.DataFrame(columns=["ts", "action", "target", "detail"])
    if "a" in dir() and "action" in getattr(a, "columns", []):
        drops = a[a["action"].isin(["DROP_IP", "ISOLATE_CONTAINER"])]
        restores = a[a["action"].isin(["RESTORE_IP", "RESTORE_CONTAINER"])]
        out["first_mitigation_ts"] = float(drops["ts"].min()) if len(drops) else None
        out["first_restore_ts"] = float(restores["ts"].min()) if len(restores) else None
        out["n_mitigations"] = int(len(drops))
    if avail is not None and len(avail):
        base = avail[avail["phase"] == "baseline"]["ok"].mean()
        atk = avail[avail["phase"] == "attack"]["ok"].mean()
        rec = avail[avail["phase"] == "recovered"]["ok"].mean()
        out["avail_baseline_pct"] = round(float(base) * 100, 1) if base == base else None
        out["avail_during_attack_pct"] = round(float(atk) * 100, 1) if atk == atk else None
        out["avail_recovered_pct"] = round(float(rec) * 100, 1) if rec == rec else None
    json.dump(out, open(f"{R}/summary.json", "w"), indent=2)
    print("[plots] summary:", json.dumps(out, indent=2))


if __name__ == "__main__":
    os.makedirs(R, exist_ok=True)
    avail = fig_availability()
    fig_timeline()
    fig_metrics()
    fig_shap()
    timing_summary(avail)
    print("[plots] figures written to results/")
