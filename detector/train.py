"""
Train and compare classifiers on the collected lab dataset.

Input : data/dataset.csv   (features + 'label' column; 1 = Slowloris, 0 = benign)
Output: models/xgb.json, models/scaler.pkl
        results/metrics.json      (precision/recall/F1/ROC-AUC/FPR per model)
        results/shap_importance.csv
        results/confusion_xgb.csv

Usage:  python train.py [--data data/dataset.csv]
"""
import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

from features import FEATURE_NAMES

MODELS_DIR = "models"
RESULTS_DIR = "results"


def fpr(y_true, y_pred):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return fp / (fp + tn) if (fp + tn) else 0.0


def evaluate(name, model, Xtr, Xte, ytr, yte, needs_scale, scaler):
    xt = scaler.transform(Xte) if needs_scale else Xte
    proba = model.predict_proba(xt)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "model": name,
        "precision": round(precision_score(yte, pred, zero_division=0), 4),
        "recall": round(recall_score(yte, pred, zero_division=0), 4),
        "f1": round(f1_score(yte, pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(yte, proba), 4) if yte.nunique() > 1 else None,
        "fpr": round(fpr(yte, pred), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dataset.csv")
    args = ap.parse_args()
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df = pd.read_csv(args.data)
    if "label" not in df.columns:
        raise SystemExit("dataset.csv must contain a 'label' column")
    X = df[FEATURE_NAMES].fillna(0.0)
    y = df["label"].astype(int)
    print(f"[train] {len(df)} rows | positives={y.sum()} negatives={(1-y).sum()}")

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.3, random_state=42,
        stratify=y if y.nunique() > 1 else None)

    scaler = StandardScaler().fit(Xtr)
    metrics = []

    # --- Baselines ---------------------------------------------------------
    lr = LogisticRegression(max_iter=1000, class_weight="balanced")
    lr.fit(scaler.transform(Xtr), ytr)
    metrics.append(evaluate("LogisticRegression", lr, Xtr, Xte, ytr, yte, True, scaler))

    rf = RandomForestClassifier(n_estimators=200, random_state=42,
                                class_weight="balanced", n_jobs=-1)
    rf.fit(Xtr, ytr)
    metrics.append(evaluate("RandomForest", rf, Xtr, Xte, ytr, yte, False, scaler))

    # --- Main model: XGBoost ----------------------------------------------
    pos = max(1, int(y.sum())); neg = max(1, int((1 - y).sum()))
    clf = xgb.XGBClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.9,
        scale_pos_weight=neg / pos, eval_metric="logloss",
        tree_method="hist", random_state=42)
    clf.fit(Xtr, ytr)
    metrics.append(evaluate("XGBoost", clf, Xtr, Xte, ytr, yte, False, scaler))

    # Persist model + scaler for the live detector
    clf.save_model(os.path.join(MODELS_DIR, "xgb.json"))
    joblib.dump(scaler, os.path.join(MODELS_DIR, "scaler.pkl"))

    # Confusion matrix for the headline model
    xte_pred = (clf.predict_proba(Xte)[:, 1] >= 0.5).astype(int)
    cm = confusion_matrix(yte, xte_pred, labels=[0, 1])
    pd.DataFrame(cm, index=["true_benign", "true_attack"],
                 columns=["pred_benign", "pred_attack"]).to_csv(
        os.path.join(RESULTS_DIR, "confusion_xgb.csv"))

    # SHAP feature importance (interpretability for the paper)
    try:
        import shap
        expl = shap.TreeExplainer(clf)
        sv = expl.shap_values(Xte)
        imp = np.abs(sv).mean(axis=0)
        pd.DataFrame({"feature": FEATURE_NAMES, "mean_abs_shap": imp}) \
          .sort_values("mean_abs_shap", ascending=False) \
          .to_csv(os.path.join(RESULTS_DIR, "shap_importance.csv"), index=False)
        print("[train] wrote SHAP importance")
    except Exception as e:  # SHAP is optional; don't fail the run
        print(f"[train] SHAP skipped: {e}")

    with open(os.path.join(RESULTS_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print("[train] metrics:")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
