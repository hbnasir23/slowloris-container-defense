#!/usr/bin/env python3
"""
Read the real experiment outputs in results/ and (re)write
paper/results_generated.tex so the paper's numbers, tables and the metrics
table come straight from the run. Run after experiments/run_all.sh.

No fabrication: anything missing stays "TBD".
"""
import csv
import json
import os

R = "results"
OUT = "paper/results_generated.tex"


def load_json(name, default):
    p = os.path.join(R, name)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return default


def main():
    metrics = load_json("metrics.json", [])
    summary = load_json("summary.json", {})
    by = {m["model"]: m for m in metrics} if metrics else {}

    def g(model, key, default="TBD"):
        v = by.get(model, {}).get(key)
        return v if v is not None else default

    # metrics table body
    if metrics:
        rows = []
        for m in metrics:
            rows.append(
                f"{m['model']} & {m['precision']} & {m['recall']} & "
                f"{m['f1']} & {m.get('roc_auc','--')} & {m['fpr']} \\\\")
        table = "\n".join(rows)
    else:
        table = r"\textit{Run experiments to populate this table.}"

    # top SHAP features
    f1 = f2 = "TBD"
    sp = os.path.join(R, "shap_importance.csv")
    if os.path.exists(sp):
        with open(sp) as f:
            rr = list(csv.DictReader(f))
        if len(rr) >= 1:
            f1 = rr[0]["feature"].replace("_", r"\_")
        if len(rr) >= 2:
            f2 = rr[1]["feature"].replace("_", r"\_")

    def macro(name, val):
        return f"\\newcommand{{\\{name}}}{{{val}}}\n"

    with open(OUT, "w") as out:
        out.write("% AUTO-GENERATED from results/ by make_results_tex.py\n")
        out.write(macro("RESxgbPrec", g("XGBoost", "precision")))
        out.write(macro("RESxgbRec", g("XGBoost", "recall")))
        out.write(macro("RESxgbFone", g("XGBoost", "f1")))
        out.write(macro("RESxgbAuc", g("XGBoost", "roc_auc")))
        out.write(macro("RESxgbFpr", g("XGBoost", "fpr")))
        out.write(macro("RESrfFone", g("RandomForest", "f1")))
        out.write(macro("RESlrFone", g("LogisticRegression", "f1")))
        out.write(macro("RESavailBase",
                        summary.get("avail_baseline_pct", "TBD")))
        out.write(macro("RESavailAttack",
                        summary.get("avail_during_attack_pct", "TBD")))
        out.write(macro("RESavailRecovered",
                        summary.get("avail_recovered_pct", "TBD")))
        out.write(macro("RESnMitigations",
                        summary.get("n_mitigations", "TBD")))
        out.write(macro("REStopFeatureOne", f1))
        out.write(macro("REStopFeatureTwo", f2))
        out.write("\\newcommand{\\RESmetricsTable}{%\n" + table + "\n}\n")
    print("[make_results_tex] wrote", OUT)


if __name__ == "__main__":
    main()
