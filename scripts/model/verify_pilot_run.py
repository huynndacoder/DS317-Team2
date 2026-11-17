"""
verify_pilot_run.py — Independent disk-only verifier for a corrected pilot run (fixes A2/A3/A6).

CLI:
  ./venv/bin/python scripts/model/verify_pilot_run.py \
      --run-dir output/experiments/pilot_corrected_20261115_112427 \
      --gold-dir output/gold/research_v2 \
      --output-dir output/audits/<repair-audit-id>/verification

Checks (all read disk only, no trainer import, no retrain, no holdout eval):
  1. Membership two-way EXCEPT/ANTI JOIN:
     membership.parquet vs independent expected sets recomputed from split.parquet
     (cohort + readiness month_index(label_window_end)+lag<=T).
     Overlap allowed (train_tune∩train_refit, validation∩train_refit).
     Holdout metadata-only check / SKIPPED-with-reason.
     Pre-2012 not in train_refit via real split metadata.
     Duplicate (loan_id, role) rejected before set operations.
     devtest/holdout not in fitting roles.
  2. Prediction integrity per file (4 files mandatory):
     - file exists, unique loan_id, finite scores [0,1], labels/cohort valid
     - ID set equality two-way with membership of the evaluation role
     - target equality with Gold target; cohort equality with split metadata
     - n/n_pos vs independent source (not len(df) vs itself)
     - no holdout IDs
  3. Metrics recompute vs pooled.csv AND per_quarter.csv:
     AP/AUC/Brier/log-loss/capture@5%/precision@5%/lift@5% from saved parquet.
     Mapping: model_name <-> pooled.csv model, stage <-> stage column
               average_precision <-> average_precision_global, etc.
     Required: metric present + reference row present; mismatch -> FAIL (not skip).
  4. Sample inference (real): 512 loan_id/file, read Gold features, saved
     preprocessor.transform + model.predict_proba, compare to saved score.
     Output sampled/matched/mismatched/max_abs_diff/mean_abs_diff.
  5. LR scaler n_samples_seen_: A=1,863,476 B=2,688,363.

Exit code: 0 iff no failed checks and no required_missing checks; skips only for
explicitly allowed scope (holdout set equality).
"""
import argparse
import hashlib
import json
import math
import pickle
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

LOG = None


def setup_logging(log_path: Path):
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        force=True,
    )


def log(msg):
    import logging
    logging.getLogger("verify_pilot_run").info(msg)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# DuckDB helpers (set operations in SQL, no full Gold fetch into pandas)
# ---------------------------------------------------------------------------
def load_role_sets(membership_path: Path, con) -> dict[str, set]:
    df = con.execute(f"SELECT loan_id, role FROM read_parquet('{membership_path.as_posix()}')").fetchdf()
    role_sets: dict[str, set] = {}
    for role, g in df.groupby("role"):
        ids = set(g["loan_id"].astype(str).tolist())
        if len(ids) != len(g):
            raise ValueError(f"trùng loan_id trong role '{role}'")
        role_sets[role] = ids
    return role_sets


def compute_expected_role_ids(split_path: Path, reporting_lag: int, con) -> dict[str, set]:
    """Expected role sets from split.parquet (cohort + readiness), independent of membership.parquet."""
    df = con.execute(f"""
        SELECT loan_id, cohort, label_window_end
        FROM read_parquet('{split_path.as_posix()}')
    """).fetchdf()
    df["mi_end"] = (df["label_window_end"] // 100) * 12 + (df["label_window_end"] % 100)
    T = {
        "train_tune": 2016 * 12 + 1,
        "validation": 2019 * 12 + 1,
        "train_refit": 2019 * 12 + 1,
    }
    expected = {}
    expected["train_tune"] = set(
        df[df["cohort"].str.match(r"20(09|10|11|12|13)Q[1-4]") & (df["mi_end"] + reporting_lag <= T["train_tune"])]["loan_id"].astype(str)
    )
    expected["validation"] = set(
        df[df["cohort"].str.match(r"2016Q[1-4]") & (df["mi_end"] + reporting_lag <= T["validation"])]["loan_id"].astype(str)
    )
    expected["train_refit"] = set(
        df[df["cohort"].str.match(r"20(12|13|14|15|16)Q[1-4]") & (df["mi_end"] + reporting_lag <= T["train_refit"])]["loan_id"].astype(str)
    )
    expected["development_test"] = set(df[df["cohort"].str.match(r"2019Q[1-4]")]["loan_id"].astype(str))
    expected["holdout"] = set(df[df["cohort"].str.match(r"2024Q[1-4]")]["loan_id"].astype(str))
    return expected


def set_comparison(actual: set, expected: set) -> dict:
    missing = expected - actual
    extra = actual - expected
    return {
        "n_actual": len(actual),
        "n_expected": len(expected),
        "n_missing": len(missing),
        "n_extra": len(extra),
        "set_equal": len(missing) == 0 and len(extra) == 0,
        "missing_ids_sample": sorted(list(missing))[:10],
        "extra_ids_sample": sorted(list(extra))[:10],
    }


# ---------------------------------------------------------------------------
# Metrics (independent recompute from saved predictions)
# ---------------------------------------------------------------------------
def ranking_metrics(y_true, y_prob, loan_id=None, k_frac=0.05):
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    n = len(y_true)
    k = 0 if n == 0 else max(1, int(math.ceil(k_frac * n)))
    if n and loan_id is not None:
        order = np.lexsort((np.asarray(loan_id, dtype=object), -y_prob))
    else:
        order = np.arange(n)
    top_idx = order[:k]
    tp = int(np.take(y_true, top_idx).sum()) if k > 0 else 0
    n_pos = int(y_true.sum())
    prev = n_pos / n if n > 0 else 0.0
    precision = tp / k if k > 0 else None
    capture = (tp / n_pos) if n_pos > 0 else None
    lift = (precision / prev) if (precision is not None and prev > 0) else None
    classes = np.unique(y_true)
    try:
        auc = float(roc_auc_score(y_true, y_prob)) if classes.size > 1 else None
    except Exception:
        auc = None
    try:
        ap = float(average_precision_score(y_true, y_prob)) if classes.size > 1 else None
    except Exception:
        ap = None
    try:
        brier = float(brier_score_loss(y_true, np.clip(y_prob, 1e-12, 1 - 1e-12)))
    except Exception:
        brier = None
    try:
        ll = float(log_loss(y_true, np.clip(y_prob, 1e-12, 1 - 1e-12), labels=[0, 1]))
    except Exception:
        ll = None
    return {
        "n": int(n), "n_pos": int(n_pos), "prevalence": float(prev),
        "k": int(k), "selected_fraction": float(k / n) if n > 0 else None,
        "tp_selected": int(tp),
        "precision_at_k": float(precision) if precision is not None else None,
        "capture_at_k": float(capture) if capture is not None else None,
        "lift_at_k": float(lift) if lift is not None else None,
        "roc_auc": auc,
        "average_precision": ap,
        "brier": brier,
        "log_loss": ll,
    }


def per_quarter_capture(y_true, y_prob, cohort, loan_id, k_frac=0.05):
    df = pd.DataFrame({"y": y_true, "p": y_prob, "cohort": cohort, "loan_id": loan_id})
    total_tp = 0
    total_pos = 0
    total_selected = 0
    caps = []
    rows = []
    for q, g in df.groupby("cohort", sort=True):
        n = len(g)
        k = 0 if n == 0 else max(1, int(math.ceil(k_frac * n)))
        g_sorted = g.sort_values(["p", "loan_id"], ascending=[False, True])
        top = g_sorted.head(k)
        tp = int(top["y"].sum())
        n_pos = int(g["y"].sum())
        total_tp += tp
        total_pos += n_pos
        total_selected += k
        caps.append((tp / n_pos) if n_pos > 0 else None)
        rows.append({"cohort": q, "n": n, "n_pos": n_pos, "k": k, "tp_selected": tp})
    valid_caps = [c for c in caps if c is not None]
    return {
        "n": int(len(df)),
        "n_pos": int(total_pos),
        "total_selected": int(total_selected),
        "total_tp": int(total_tp),
        "capacity_pooled_capture": (total_tp / total_pos) if total_pos > 0 else None,
        "macro_mean_capture": float(np.mean(valid_caps)) if valid_caps else None,
        "per_quarter_rows": rows,
    }


def _quarter_detail_rows(y_true, y_prob, cohort, loan_id, k_frac=0.05):
    """Chi tiết từng quý: capture_at_k/precision_at_k/lift_at_k/roc_auc/average_precision để so sánh hàng-quý với CSV.
    Công thức khớp trainer: precision=tp/k, capture=tp/n_pos, prev=n_pos/n, lift=precision/prev."""
    from sklearn.metrics import roc_auc_score, average_precision_score
    df = pd.DataFrame({"y": y_true, "p": y_prob, "cohort": cohort, "loan_id": loan_id})
    rows = []
    for q, g in df.groupby("cohort", sort=True):
        n = len(g)
        k = 0 if n == 0 else max(1, int(math.ceil(k_frac * n)))
        g_sorted = g.sort_values(["p", "loan_id"], ascending=[False, True])
        top = g_sorted.head(k)
        tp = int(top["y"].sum())
        n_pos = int(g["y"].sum())
        prev = n_pos / n if n > 0 else 0.0
        capture = (tp / n_pos) if n_pos > 0 else None
        precision = (tp / k) if k > 0 else None
        lift = (precision / prev) if (precision is not None and prev > 0) else None
        try:
            auc = float(roc_auc_score(g["y"], g["p"])) if g["y"].nunique() > 1 else None
        except Exception:
            auc = None
        try:
            ap = float(average_precision_score(g["y"], g["p"])) if g["y"].nunique() > 1 else None
        except Exception:
            ap = None
        rows.append({"cohort": str(q), "n": n, "n_pos": n_pos, "k": k, "tp_selected": tp,
                     "prevalence": prev, "selected_fraction": (k / n) if n > 0 else None,
                     "capture_at_k": capture, "precision_at_k": precision, "lift_at_k": lift,
                     "roc_auc": auc})
    return rows


def _metric_is_bad(v) -> bool:
    """True nếu metric bị thiếu/không hợp lệ: None, NaN, inf, chuỗi rỗng."""
    if v is None:
        return True
    try:
        f = float(v)
    except (TypeError, ValueError):
        return True
    return not math.isfinite(f)


def compare_quarterly(recomputed_rows, csv_rows, tol=1e-6):
    """
    So sánh chi tiết từng hàng-quý giữa recompute (per_quarter detail) và CSV per_quarter.csv.
    Contract C1:
    - Key = (model, stage, cohort), unique và non-null trước khi tạo dict/index.
    - Exact key set và row count; duplicate/missing/extra row đều FAIL.
    - Exact integer fields: n, n_pos, k, tp_selected (không dùng tolerance float).
    - Float fields: prevalence, selected_fraction, precision_at_k, capture_at_k, lift_at_k, roc_auc.
    - k == ceil(0.05*n), selected_fraction == k/n.
    - Trả về (ok, mismatches).
    """
    mismatches = []

    # Validate keys non-null
    for r in recomputed_rows:
        for key in ("model", "stage", "cohort"):
            if r.get(key) is None or str(r.get(key)).strip() == "":
                mismatches.append(f"recomputed row missing key {key}: {r}")
    for r in csv_rows:
        for key in ("model", "stage", "cohort"):
            if r.get(key) is None or str(r.get(key)).strip() == "":
                mismatches.append(f"csv row missing key {key}: {r}")
    if mismatches:
        return False, mismatches

    recomputed_keys = [(str(r["model"]), str(r["stage"]), str(r["cohort"])) for r in recomputed_rows]
    csv_keys = [(str(r["model"]), str(r["stage"]), str(r["cohort"])) for r in csv_rows]

    # Duplicate detection (không để set collapse âm thầm)
    recomputed_dups = [k for k in recomputed_keys if recomputed_keys.count(k) > 1]
    csv_dups = [k for k in csv_keys if csv_keys.count(k) > 1]
    if recomputed_dups:
        mismatches.append(f"recomputed duplicate quarterly keys: {sorted(set(recomputed_dups))[:10]}")
    if csv_dups:
        mismatches.append(f"csv duplicate quarterly keys: {sorted(set(csv_dups))[:10]}")
    if mismatches:
        return False, mismatches

    # Exact key set and row count
    recomputed_set = set(recomputed_keys)
    csv_set = set(csv_keys)
    if recomputed_set != csv_set:
        missing = csv_set - recomputed_set
        extra = recomputed_set - csv_set
        mismatches.append(f"key set mismatch: missing={sorted(missing)[:10]} extra={sorted(extra)[:10]}")
        return False, mismatches
    if len(recomputed_rows) != len(csv_rows):
        mismatches.append(f"row count mismatch: recomputed={len(recomputed_rows)} csv={len(csv_rows)}")
        return False, mismatches

    recomputed_by_key = {k: r for k, r in zip(recomputed_keys, recomputed_rows)}
    csv_by_key = {k: r for k, r in zip(csv_keys, csv_rows)}

    int_fields = ["n", "n_pos", "k", "tp_selected"]
    float_fields = ["prevalence", "selected_fraction", "precision_at_k", "capture_at_k", "lift_at_k", "roc_auc"]

    for key in recomputed_keys:
        r = recomputed_by_key[key]
        c = csv_by_key[key]
        cohort = key[2]

        invalid_counts = False
        for label, row in (("recomputed", r), ("csv", c)):
            try:
                values = [float(row[f]) for f in int_fields]
                if not all(math.isfinite(v) and v.is_integer() for v in values):
                    raise ValueError("counts must be finite integers")
                n, pos, k, tp = map(int, values)
                if not (n > 0 and 0 <= pos <= n and 0 < k <= n and 0 <= tp <= min(k, pos)):
                    raise ValueError("counts outside population bounds")
                derived = {"prevalence": pos/n, "selected_fraction": k/n, "precision_at_k": tp/k}
                if pos:
                    derived.update(capture_at_k=tp/pos, lift_at_k=(tp/k)/(pos/n))
                for metric, expected_value in derived.items():
                    if _metric_is_bad(row.get(metric)) or abs(float(row[metric])-expected_value) > tol:
                        mismatches.append(f"{cohort} {label} {metric}: invalid for population")
                if not _metric_is_bad(row.get("roc_auc")) and not 0 <= float(row["roc_auc"]) <= 1:
                    mismatches.append(f"{cohort} {label} roc_auc: outside [0,1]")
            except (TypeError, ValueError, OverflowError) as exc:
                mismatches.append(f"{cohort} {label} invalid population counts: {exc}")
                invalid_counts = True
        if invalid_counts:
            continue

        # Exact integer fields (không tolerance)
        for f in int_fields:
            va = r.get(f)
            vb = c.get(f)
            try:
                va_i = int(va) if va is not None else None
                vb_i = int(vb) if vb is not None else None
            except (TypeError, ValueError):
                mismatches.append(f"{cohort} {f}: non-integer {va!r} vs {vb!r}")
                continue
            if va_i != vb_i:
                mismatches.append(f"{cohort} {f}: {va_i} vs {vb_i}")

        # k == ceil(0.05*n) và selected_fraction == k/n
        n_val = r.get("n")
        k_val = r.get("k")
        sf_val = r.get("selected_fraction")
        if n_val is not None and k_val is not None:
            expected_k = 0 if int(n_val) == 0 else max(1, int(math.ceil(0.05 * int(n_val))))
            if int(k_val) != expected_k:
                mismatches.append(f"{cohort} k: {k_val} != ceil(0.05*{n_val})={expected_k}")
        if n_val is not None and k_val is not None and sf_val is not None:
            try:
                if abs(float(sf_val) - (float(k_val) / float(n_val))) > tol:
                    mismatches.append(f"{cohort} selected_fraction: {sf_val} != {k_val}/{n_val}")
            except (TypeError, ValueError):
                mismatches.append(f"{cohort} selected_fraction: non-numeric {sf_val!r}")

        # Float fields
        for f in float_fields:
            va = r.get(f)
            vb = c.get(f)
            va_bad = _metric_is_bad(va)
            vb_bad = _metric_is_bad(vb)
            if va_bad and vb_bad:
                n, n_pos = int(r["n"]), int(r["n_pos"])
                # N/A is population-specific, never a blanket invalid-both match.
                allowed = (f == "roc_auc" and n > 0 and n_pos in (0, n)) or (
                    f in ("capture_at_k", "lift_at_k") and n > 0 and n_pos == 0)
                def explicit_na(value):
                    return value is None or value == "" or (isinstance(value, (float, np.floating)) and math.isnan(value))
                if allowed and f in r and f in c and explicit_na(va) and explicit_na(vb):
                    continue
                mismatches.append(f"{cohort} {f}: invalid-both without explicit population N/A")
                continue
            if va_bad or vb_bad:
                mismatches.append(f"{cohort} {f}: {va!r} vs {vb!r}")
                continue
            try:
                if abs(float(va) - float(vb)) > tol:
                    mismatches.append(f"{cohort} {f}: {va} vs {vb}")
            except (TypeError, ValueError):
                if str(va) != str(vb):
                    mismatches.append(f"{cohort} {f}: {va} vs {vb}")

    return len(mismatches) == 0, mismatches


def compare_metrics(a, b, required_keys=None, tol=1e-6):
    """
    So sánh dict a (recompute, key METRIC_ALIASES) vs b (CSV cột *_global).
    Áp dụng METRIC_ALIASES để khớp tên cột.

    Policy N/A theo metric và population (C3):
    - required_keys: tập các key BẮT BUỘC phải có giá trị finite (None/NaN/inf/missing -> FAIL).
      Trên bốn pilot evaluation file có hai lớp: AP, ROC-AUC, Brier, log-loss, capture/precision/lift
      đều required.
    - Metric không required: None-None -> match (N/A hợp lệ, ví dụ AUC single-class);
      một bên bad -> FAIL.
    - Missing key ở bất kỳ phía nào -> FAIL (không coi là undefined metric).
    - Không dùng quy tắcNone-None tổng quát để che lỗi required metric.
    """
    mismatches = []
    checked_keys = set()
    if required_keys is None:
        required_keys = set(METRIC_ALIASES.keys())
    for k, csv_col in METRIC_ALIASES.items():
        checked_keys.add(csv_col)
        va = a.get(k)
        vb = b.get(csv_col)
        is_required = k in required_keys
        va_missing = k not in a
        vb_missing = csv_col not in b
        if va_missing or vb_missing:
            mismatches.append(f"{k}: missing key ({k!r} in a={k in a}, {csv_col!r} in b={csv_col in b})")
            continue
        va_bad = _metric_is_bad(va)
        vb_bad = _metric_is_bad(vb)
        if va_bad or vb_bad:
            if is_required:
                mismatches.append(f"{k}: required metric không hợp lệ ({va!r} vs {vb!r})")
            else:
                if va_bad and vb_bad:
                    continue  # cả hai N/A hợp lệ (ví dụ AUC single-class)
                mismatches.append(f"{k}: một bên không hợp lệ ({va!r} vs {vb!r})")
            continue
        try:
            if abs(float(va) - float(vb)) > tol:
                mismatches.append(f"{k}: {va} vs {vb}")
        except (TypeError, ValueError):
            if str(va) != str(vb):
                mismatches.append(f"{k}: {va} vs {vb}")
    # Phát hiện cột CSV bắt buộc nhưng thiếu hoàn toàn (chỉ khi b là hàng CSV thực)
    if len(b) > 0:
        for csv_col in checked_keys:
            if csv_col not in b:
                mismatches.append(f"missing csv column: {csv_col}")
    return mismatches


# Metric key aliasing between recompute dict and pooled.csv columns
METRIC_ALIASES = {
    "average_precision": "average_precision_global",
    "roc_auc": "roc_auc_global",
    "brier": "brier_global",
    "log_loss": "log_loss_global",
    "precision_at_k": "precision_at_k_global",
    "capture_at_k": "capture_at_k_global",
    "lift_at_k": "lift_at_k_global",
    "capacity_pooled_capture": "capacity_pooled_capture",
    "macro_mean_capture": "macro_mean_capture",
}
# Pooled.csv stage names (from trainer main)
POOLED_STAGE = {
    "validation_lr": ("logistic_regression", "stage_A_validation"),
    "validation_xgb": ("xgboost", "stage_A_validation"),
    "development_test_lr": ("logistic_regression", "stage_B_development_test"),
    "development_test_xgb": ("xgboost", "stage_B_development_test"),
}
PRED_FILES = [
    ("validation_lr", "stage_a_lr.pkl", "A"),
    ("validation_xgb", "stage_a_xgb.pkl", "A"),
    ("development_test_lr", "stage_b_lr.pkl", "B"),
    ("development_test_xgb", "stage_b_xgb.pkl", "B"),
]


def sample_inference_real(pred_path: Path, model_path: Path, gold_dir: Path, con,
                          n_sample: int = 512, seed: int = 42, stage_label: str = ""):
    """Real inference: sample 512 loan_id, read Gold features, transform+predict_proba,
    compare to saved score."""
    preds = pd.read_parquet(pred_path)
    if len(preds) == 0:
        return {"sampled": 0, "matched": 0, "mismatched": 0, "max_abs_diff": None,
                "mean_abs_diff": None, "note": "empty predictions"}
    sample = preds.sample(n=min(n_sample, len(preds)), random_state=seed)
    ids = sample["loan_id"].astype(str).tolist()
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    preprocessor = bundle["preprocessor"]

    # Read features for sampled IDs only (no full Gold fetch)
    id_df = pd.DataFrame({"loan_id": ids})
    con.register("sample_ids", id_df)
    feat_cols = ["loan_id"] + [c for c in [
        "original_upb", "original_loan_term", "original_interest_rate", "ltv", "cltv",
        "dti", "mi_percentage", "number_of_units", "credit_score",
        "first_time_homebuyer_flag", "channel", "property_type", "property_state",
        "occupancy_status", "prepayment_penalty_flag", "super_conforming_flag",
        "harp_indicator", "number_of_borrowers",
    ]]
    feat = con.execute(f"""
        SELECT {', '.join(feat_cols)} FROM read_parquet('{(gold_dir / 'features.parquet').as_posix()}') f
        INNER JOIN sample_ids s USING (loan_id)
    """).fetchdf()
    con.unregister("sample_ids")

    if len(feat) != len(ids):
        missing = set(ids) - set(feat["loan_id"].astype(str).tolist())
        return {
            "sampled": len(ids), "matched": 0, "mismatched": len(ids),
            "max_abs_diff": None, "mean_abs_diff": None,
            "note": f"features missing for {len(missing)} sampled ids (e.g. {sorted(list(missing))[:5]})",
        }
    feat = feat.set_index("loan_id").reindex(ids).reset_index()
    X = feat[[c for c in feat_cols if c != "loan_id"]]
    Xt = preprocessor.transform(X)
    probs = model.predict_proba(Xt)[:, 1]
    saved = sample.set_index("loan_id")["score"].astype(float).reindex(ids).to_numpy()
    diffs = np.abs(probs - saved)
    mismatched = int((diffs > 1e-8).sum())
    matched = len(ids) - mismatched
    return {
        "sampled": int(len(ids)),
        "matched": int(matched),
        "mismatched": int(mismatched),
        "max_abs_diff": float(diffs.max()),
        "mean_abs_diff": float(diffs.mean()),
        "loan_ids": ids,
        "predicted_probabilities": probs.astype(float).tolist(),
        "saved_scores": saved.astype(float).tolist(),
        "note": f"real inference: preprocessor.transform + model.predict_proba on {len(ids)} sampled ids",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def registry_summary(checks, required):
    """Audit actual emitted records; keep missing/failed/duplicate/unexpected distinct."""
    from collections import Counter
    counts = Counter(c["name"] for c in checks if c.get("required"))
    return {
        "missing": sorted(set(required) - counts.keys()),
        "failed": sorted({c["name"] for c in checks if c.get("required") and not c["pass"]}),
        "duplicate": {name: count for name, count in counts.items() if count > 1},
        "unexpected": sorted(counts.keys() - set(required)),
    }


def create_gold_views(con, gold_dir):
    """Lazy SQL views; no full Gold materialization in Python."""
    for name, filename in (("membership", "membership.parquet"), ("split_metadata", "split.parquet"), ("target", "target.parquet")):
        con.read_parquet(str(gold_dir / filename)).create_view(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--reporting-lag", type=int, default=3)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    gold_dir = Path(args.gold_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(out_dir / "verify.log")

    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='2GB'")

    results = {"checks": [], "overall": True, "required_missing": []}
    REQUIRED = [
        "membership train_tune set_equal", "membership validation set_equal",
        "membership train_refit set_equal", "membership development_test set_equal",
        "train_refit no pre-2012", "development_test not in fitting roles",
        "holdout not in fitting roles",
        "predictions validation_lr integrity", "predictions validation_xgb integrity",
        "predictions development_test_lr integrity", "predictions development_test_xgb integrity",
        "predictions validation_lr n/n_pos vs Gold target", "predictions validation_xgb n/n_pos vs Gold target",
        "predictions development_test_lr n/n_pos vs Gold target", "predictions development_test_xgb n/n_pos vs Gold target",
        "predictions validation_lr per-loan_id label == Gold target", "predictions validation_xgb per-loan_id label == Gold target",
        "predictions development_test_lr per-loan_id label == Gold target", "predictions development_test_xgb per-loan_id label == Gold target",
        "predictions validation_lr per-loan_id cohort == Gold split", "predictions validation_xgb per-loan_id cohort == Gold split",
        "predictions development_test_lr per-loan_id cohort == Gold split", "predictions development_test_xgb per-loan_id cohort == Gold split",
        "predictions validation_lr matches pooled.csv", "predictions validation_xgb matches pooled.csv",
        "predictions development_test_lr matches pooled.csv", "predictions development_test_xgb matches pooled.csv",
        "predictions validation_lr matches per_quarter.csv", "predictions validation_xgb matches per_quarter.csv",
        "predictions development_test_lr matches per_quarter.csv", "predictions development_test_xgb matches per_quarter.csv",
        "sample inference validation_lr", "sample inference validation_xgb",
        "sample inference development_test_lr", "sample inference development_test_xgb",
        "LR scaler stage A n_samples_seen", "LR scaler stage B n_samples_seen",
    ]
    # Thêm các required check đã bị bỏ trong phiên bản trước (C2)
    REQUIRED += [
        "membership no duplicate (loan_id,role)",
        "predictions validation_lr recompute metrics",
        "predictions validation_xgb recompute metrics",
        "predictions development_test_lr recompute metrics",
        "predictions development_test_xgb recompute metrics",
        "predictions validation_lr matches per_quarter.csv per-row",
        "predictions validation_xgb matches per_quarter.csv per-row",
        "predictions development_test_lr matches per_quarter.csv per-row",
        "predictions development_test_xgb matches per_quarter.csv per-row",
        # matches per_quarter.csv pooled counts (4)
        "predictions validation_lr matches per_quarter.csv pooled counts",
        "predictions validation_xgb matches per_quarter.csv pooled counts",
        "predictions development_test_lr matches per_quarter.csv pooled counts",
        "predictions development_test_xgb matches per_quarter.csv pooled counts",
    ]
    REQUIRED_SET = set(REQUIRED)
    # executed_required_list: danh sách tên check required đã thực thi (giữ thứ tự, cho phép phát hiện duplicate)
    executed_required_list = []
    executed_required = set()

    role_sets = {}
    expected = {}
    holdout_ids = set()

    def check(name, ok, detail="", required=True):
        results["checks"].append({"name": name, "pass": bool(ok), "detail": detail, "required": required})
        results["overall"] = results["overall"] and bool(ok)
        if required:
            # Unexpected required ID (không khai báo trong contract) = lỗi
            if name not in REQUIRED_SET:
                results["checks"].append({
                    "name": f"UNEXPECTED_REQUIRED_ID: {name}",
                    "pass": False,
                    "detail": f"check required nhưng không khai báo trong REQUIRED contract",
                    "required": True,
                })
                results["overall"] = False
            executed_required_list.append(name)
            executed_required.add(name)
            if not ok:
                results["required_missing"].append(name)
        log(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # ---- Check 1: membership ----
    membership_path = gold_dir / "membership.parquet"
    split_path = gold_dir / "split.parquet"
    if not membership_path.exists() or not split_path.exists():
        check("membership files exist", False, f"missing {membership_path} or {split_path}")
    else:
        # SQL set/count operations: do not materialize whole Gold ID populations.
        create_gold_views(con, gold_dir)

        # duplicate (loan_id, role) check
        duplicates = con.execute("SELECT count(*) FROM (SELECT loan_id,role FROM membership GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0]
        check("membership no duplicate (loan_id,role)", duplicates == 0,
              f"duplicates={duplicates}")

        role_rules = {
            "train_tune": (r"20(09|10|11|12|13)Q[1-4]", 2016*12+1),
            "validation": (r"2016Q[1-4]", 2019*12+1),
            "train_refit": (r"20(12|13|14|15|16)Q[1-4]", 2019*12+1),
            "development_test": (r"2019Q[1-4]", None),
        }

        for role in ["train_tune", "validation", "train_refit", "development_test"]:
            pattern, cutoff = role_rules[role]
            readiness = "" if cutoff is None else f"AND ((label_window_end // 100)*12 + label_window_end % 100 + {args.reporting_lag}) <= {cutoff}"
            expected_sql = f"SELECT loan_id FROM split_metadata WHERE regexp_full_match(cohort, '{pattern}') {readiness}"
            actual_sql = f"SELECT loan_id FROM membership WHERE role='{role}'"
            n_actual = con.execute(f"SELECT count(*) FROM ({actual_sql})").fetchone()[0]
            n_expected = con.execute(f"SELECT count(*) FROM ({expected_sql})").fetchone()[0]
            missing = con.execute(f"SELECT count(*) FROM ({expected_sql} EXCEPT {actual_sql})").fetchone()[0]
            extra = con.execute(f"SELECT count(*) FROM ({actual_sql} EXCEPT {expected_sql})").fetchone()[0]
            check(f"membership {role} set_equal", missing == extra == 0 and n_actual == n_expected,
                  f"actual={n_actual:,} expected={n_expected:,} missing={missing} extra={extra}")

        ho_actual = con.execute("SELECT count(*) FROM membership WHERE role='holdout'").fetchone()[0]
        ho_expected = con.execute("SELECT count(*) FROM split_metadata WHERE regexp_full_match(cohort,'2024Q[1-4]')").fetchone()[0]
        check("membership holdout count (skipped set_equal)", ho_actual == ho_expected,
              f"actual={ho_actual:,} expected={ho_expected:,} (metadata only; no holdout features/labels/scores)",
              required=False)

        # pre-2012 not in train_refit (real split metadata)
        tr_count = con.execute("SELECT count(*) FROM membership WHERE role='train_refit'").fetchone()[0]
        if tr_count:
            pre2012 = con.execute("""SELECT count(*) FROM split_metadata s JOIN membership m USING(loan_id)
                WHERE m.role='train_refit' AND s.cohort ~ '20(09|10|11)Q[1-4]'""").fetchone()[0]
            check("train_refit no pre-2012", pre2012 == 0, f"pre-2012 count in train_refit={pre2012}")
        else:
            check("train_refit no pre-2012", False, "train_refit empty")

        # cross-role leak
        for role in ("development_test", "holdout"):
            leak = con.execute("""SELECT count(*) FROM membership e JOIN membership f USING(loan_id)
                WHERE e.role=? AND f.role IN ('train_tune','train_refit','validation')""", [role]).fetchone()[0]
            check(f"{role} not in fitting roles", leak == 0, f"leak={leak}")

    # ---- Check 2: prediction integrity + metrics recompute ----
    pooled_path = run_dir / "metrics" / "pooled.csv"
    perq_path = run_dir / "metrics" / "per_quarter.csv"
    pooled_ref = {}
    perq_ref = {}
    if pooled_path.exists():
        pooled_df = pd.read_csv(pooled_path)
        for _, row in pooled_df.iterrows():
            pooled_ref[(row["model"], row["stage"])] = row.to_dict()
    if perq_path.exists():
        perq_df = pd.read_csv(perq_path)
        for _, row in perq_df.iterrows():
            perq_ref.setdefault((row["model"], row["stage"]), []).append(row.to_dict())

    recomputed = {}
    for name, pkl_name, stage_label in PRED_FILES:
        p_path = run_dir / "predictions" / f"{name}.parquet"
        m_path = run_dir / "models" / pkl_name
        model_name, pooled_stage = POOLED_STAGE[name]

        if not p_path.exists():
            check(f"predictions {name} exists", False, f"missing {p_path}")
            continue
        df = pd.read_parquet(p_path)
        # Integrity: unique id, scores [0,1], labels/cohort valid
        ids = df["loan_id"].astype(str).to_numpy()
        unique_ok = len(np.unique(ids)) == len(ids)
        scores = df["score"].to_numpy(dtype=float)
        scores_ok = bool(np.all(np.isfinite(scores)) and np.all(scores >= 0.0) and np.all(scores <= 1.0))
        labels = df["label_12m"].to_numpy()
        labels_ok = bool(set(np.unique(labels).tolist()).issubset({0, 1}))
        cohort = df["cohort"].astype(str).to_numpy()
        cohort_ok = bool(~pd.isna(cohort).any())

        # Role membership set equality two-way vs evaluation role
        eval_role = "validation" if stage_label == "A" else "development_test"
        con.register("prediction_ids", pd.DataFrame({"loan_id": ids}))
        missing_ids = con.execute("SELECT count(*) FROM (SELECT loan_id FROM membership WHERE role=? EXCEPT SELECT loan_id FROM prediction_ids)", [eval_role]).fetchone()[0]
        extra_ids = con.execute("SELECT count(*) FROM (SELECT loan_id FROM prediction_ids EXCEPT SELECT loan_id FROM membership WHERE role=?)", [eval_role]).fetchone()[0]
        set_equal = missing_ids == extra_ids == 0

        # no holdout IDs
        holdout_leak = con.execute("SELECT count(*) FROM prediction_ids JOIN membership USING(loan_id) WHERE role='holdout'").fetchone()[0]
        con.unregister("prediction_ids")

        check(f"predictions {name} integrity",
              unique_ok and scores_ok and labels_ok and cohort_ok and set_equal and holdout_leak == 0,
              f"n={len(df)} unique={unique_ok} scores[0,1]={scores_ok} labels={labels_ok} cohort={cohort_ok} "
              f"set_equal={set_equal} missing={missing_ids} extra={extra_ids} holdout_leak={holdout_leak}")

        # n/n_pos vs independent Gold target (not len(df) vs itself)
        if membership_path.exists():
            tgt = con.execute(f"""
                SELECT COUNT(*) n, SUM(CAST(label_12m AS BIGINT)) n_pos
                FROM read_parquet('{(gold_dir / 'target.parquet').as_posix()}') t
                INNER JOIN membership e USING (loan_id) WHERE e.role=?
            """, [eval_role]).fetchone()
            n_exp, n_pos_exp = int(tgt[0]), int(tgt[1])
            check(f"predictions {name} n/n_pos vs Gold target", len(df) == n_exp and int(labels.sum()) == n_pos_exp,
                  f"pred n={len(df)} n_pos={int(labels.sum())} Gold n={n_exp} n_pos={n_pos_exp}", required=True)

            # Per-loan_id label & cohort equality vs Gold target/split (R3)
            pred_lbl = pd.DataFrame({"loan_id": ids, "label_12m": labels, "cohort": cohort})
            con.register("pred_lbl", pred_lbl)
            # Labels: target.parquet has (loan_id, label_12m). Cohort: split.parquet has (loan_id, cohort, ...)
            gold_lbl = con.execute(f"""
                SELECT p.loan_id,
                       CAST(p.label_12m AS BIGINT) AS pred_label,
                       CAST(t.label_12m AS BIGINT) AS gold_label
                FROM pred_lbl p
                INNER JOIN read_parquet('{(gold_dir / 'target.parquet').as_posix()}') t USING (loan_id)
                WHERE p.label_12m <> CAST(t.label_12m AS BIGINT)
            """).fetchdf()
            con.unregister("pred_lbl")
            mismatch_n = len(gold_lbl)
            # Cohort check vs split.parquet
            con.register("pred_lbl", pd.DataFrame({"loan_id": ids, "cohort": cohort}))
            gold_coh = con.execute(f"""
                SELECT p.loan_id, p.cohort AS pred_cohort, s.cohort AS gold_cohort
                FROM pred_lbl p
                INNER JOIN read_parquet('{(split_path.as_posix() if 'split_path' in locals() else gold_dir / 'split.parquet')}') s USING (loan_id)
                WHERE p.cohort <> s.cohort
            """).fetchdf()
            con.unregister("pred_lbl")
            cohort_mismatch_n = len(gold_coh)
            check(f"predictions {name} per-loan_id label == Gold target", mismatch_n == 0,
                  f"label mismatch rows={mismatch_n}" + (f" sample={gold_lbl.head(3).to_dict('records')}" if mismatch_n else ""), required=True)
            check(f"predictions {name} per-loan_id cohort == Gold split", cohort_mismatch_n == 0,
                  f"cohort mismatch rows={cohort_mismatch_n}" + (f" sample={gold_coh.head(3).to_dict('records')}" if cohort_mismatch_n else ""), required=True)
        else:
            n_exp, n_pos_exp = None, None

        # Recompute metrics
        m = ranking_metrics(labels, scores, loan_id=ids)
        pq = per_quarter_capture(labels, scores, cohort, ids)
        # per-quarter detail rows for row-level comparison (R4)
        pq_detail = _quarter_detail_rows(labels, scores, cohort, ids, k_frac=0.05)
        recomputed[name] = {**m, **pq, "model": model_name, "stage": stage_label,
                            "n_gold": n_exp, "n_pos_gold": n_pos_exp,
                            "per_quarter": pq_detail if isinstance(pq_detail, list) else []}
        check(f"predictions {name} recompute metrics",
              m["n"] == len(df) and m["n_pos"] == int(labels.sum()),
              f"AP={m['average_precision']:.6f} AUC={m['roc_auc']:.6f} Brier={m['brier']:.6f} logloss={m['log_loss']:.6f} capture@5={m['capture_at_k']:.6f}")

        # Compare to pooled.csv reference (A2 fix: mapping + no skip)
        ref = pooled_ref.get((model_name, pooled_stage))
        if ref is None:
            check(f"predictions {name} matches pooled.csv", False,
                  f"no pooled.csv reference row for (model={model_name}, stage={pooled_stage})", required=True)
        else:
            REQUIRED_METRICS = {
                "average_precision", "roc_auc", "brier", "log_loss",
                "precision_at_k", "capture_at_k", "lift_at_k",
            }
            mm = compare_metrics(recomputed[name], ref, required_keys=REQUIRED_METRICS)
            check(f"predictions {name} matches pooled.csv", len(mm) == 0,
                  "; ".join(mm) if mm else "match", required=True)

        # Compare per-quarter rows using production compare_quarterly helper (C1)
        pq_refs = perq_ref.get((model_name, pooled_stage), [])
        per_q_recomputed = recomputed[name].get("per_quarter", [])

        # Build rows with model/stage keys for exact key-set contract
        recomputed_q_rows = []
        for r in per_q_recomputed:
            row = dict(r)
            row["model"] = model_name
            row["stage"] = stage_label
            recomputed_q_rows.append(row)
        csv_q_rows = []
        for r in pq_refs:
            row = dict(r)
            row["model"] = model_name
            row["stage"] = stage_label
            csv_q_rows.append(row)

        pq_ok, pq_mm = compare_quarterly(recomputed_q_rows, csv_q_rows)
        check(f"predictions {name} matches per_quarter.csv per-row", pq_ok,
              "; ".join(pq_mm) if pq_mm else "match", required=True)

        # Aggregate pooled counts cross-check: recompute from quarterly rows (not trust CSV total)
        total_selected_csv = sum(int(r.get("k", 0) or 0) for r in csv_q_rows)
        total_tp_csv = sum(int(r.get("tp_selected", 0) or 0) for r in csv_q_rows)
        total_n_csv = sum(int(r.get("n", 0) or 0) for r in csv_q_rows)
        total_pos_csv = sum(int(r.get("n_pos", 0) or 0) for r in csv_q_rows)
        agg_mm = []
        for field, csv_val, recomputed_val in [
            ("n", total_n_csv, m["n"]),
            ("n_pos", total_pos_csv, m["n_pos"]),
            ("total_selected", total_selected_csv, pq.get("total_selected", None)),
            ("total_tp", total_tp_csv, pq.get("total_tp", None)),
        ]:
            if recomputed_val is None:
                agg_mm.append(f"{field}: recomputed None vs csv {csv_val}")
            elif int(recomputed_val) != int(csv_val):
                agg_mm.append(f"{field}: {recomputed_val} vs csv {csv_val}")
        check(f"predictions {name} matches per_quarter.csv pooled counts", len(agg_mm) == 0,
              "; ".join(agg_mm) if agg_mm else "match", required=True)

        if not pq_refs:
            check(f"predictions {name} matches per_quarter.csv", False,
                  f"no per_quarter.csv reference for (model={model_name}, stage={pooled_stage})", required=True)
        else:
            check(f"predictions {name} matches per_quarter.csv", pq_ok,
                  "; ".join(pq_mm) if pq_mm else "match")

    # ---- Check 3: sample inference (real) ----
    inference = {}
    for name, pkl_name, stage_label in PRED_FILES:
        p_path = run_dir / "predictions" / f"{name}.parquet"
        m_path = run_dir / "models" / pkl_name
        if not p_path.exists() or not m_path.exists():
            check(f"sample inference {name}", False, f"missing {p_path} or {m_path}", required=True)
            continue
        inf = sample_inference_real(p_path, m_path, gold_dir, con, stage_label=stage_label)
        inf.update({"atol": 1e-8, "rtol": 0.0, "seed": 42})
        ok = inf["sampled"] == 512 and inf["mismatched"] == 0 and inf["max_abs_diff"] is not None and inf["max_abs_diff"] <= inf["atol"]
        inf["pass"] = ok
        inference[name] = inf
        check(f"sample inference {name}", ok,
              f"sampled={inf['sampled']} matched={inf['matched']} mismatched={inf['mismatched']} "
              f"max_abs_diff={inf['max_abs_diff']} mean_abs_diff={inf['mean_abs_diff']} note={inf['note']}",
              required=True)

    # ---- Check 4: LR scaler n_samples_seen ----
    for stage, pkl_name, expected_n in [("A", "stage_a_lr.pkl", 1_863_476), ("B", "stage_b_lr.pkl", 2_688_363)]:
        pkl_path = run_dir / "models" / pkl_name
        if not pkl_path.exists():
            check(f"LR scaler stage {stage} pkl exists", False, f"missing {pkl_path}", required=True)
            continue
        with open(pkl_path, "rb") as f:
            bundle = pickle.load(f)
        pre = bundle["preprocessor"]
        try:
            scaler = pre.named_transformers_["num"].named_steps["scale"]
            n_seen = int(getattr(scaler, "n_samples_seen_", -1))
            check(f"LR scaler stage {stage} n_samples_seen", n_seen == expected_n,
                  f"n_samples_seen={n_seen} expected={expected_n:,}", required=True)
        except (AttributeError, KeyError) as e:
            check(f"LR scaler stage {stage} n_samples_seen", False, f"cannot read scaler: {e}", required=True)

    # ---- C2: required registry - missing/failed/duplicate/unexpected ----
    # required_missing được tính lại từ toàn bộ checks, không guglielp từ check() trước đó
    results["required_missing"] = []
    # duplicate execution names (không để set collapse âm thầm)
    from collections import Counter as _Counter
    registry = registry_summary(results["checks"], REQUIRED_SET)
    results["registry"] = registry
    results["required_ids"] = sorted(REQUIRED_SET)
    for name, count in registry["duplicate"].items():
        results["checks"].append({
            "name": f"DUPLICATE_REQUIRED_CHECK: {name}",
            "pass": False,
            "detail": f"check required được thực thi {count} lần",
            "required": True,
        })
        results["overall"] = False
        results["required_missing"].append(f"DUPLICATE_REQUIRED_CHECK: {name}")

    # missing_required = expected - executed
    missing_required = REQUIRED_SET - executed_required
    for name in sorted(missing_required):
        results["checks"].append({
            "name": f"MISSING_REQUIRED_CHECK: {name}",
            "pass": False,
            "detail": "không thực hiện check này trong lần chạy",
            "required": True,
        })
        results["overall"] = False
        results["required_missing"].append(f"MISSING_REQUIRED_CHECK: {name}")

    # failed_required = executed required but not ok
    for c in results["checks"]:
        nm = c["name"]
        if c.get("required") and not c["pass"] and not nm.startswith(("MISSING_REQUIRED_CHECK:", "DUPLICATE_REQUIRED_CHECK:", "UNEXPECTED_REQUIRED_ID:")):
            results["required_missing"].append(nm)

    # ---- Write outputs ----
    (out_dir / "sample_inference.json").write_text(json.dumps(inference, indent=2), encoding="utf-8")
    (out_dir / "verification.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "recomputed_metrics.json").write_text(json.dumps(recomputed, indent=2, default=str), encoding="utf-8")
    inv = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            inv[str(p.relative_to(run_dir))] = {"sha256": sha256_file(p), "size": p.stat().st_size}
    (out_dir / "artifact_inventory_sha256.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")

    overall_ok = results["overall"] and len(results["required_missing"]) == 0
    log(f"VERIFICATION overall={'PASS' if overall_ok else 'FAIL'} required_missing={len(results['required_missing'])}")
    print(json.dumps(results, indent=2, default=str))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
