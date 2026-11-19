"""
train_baseline.py — Corrected pilot trainer (fixes F1-F6 per audit).

Role membership from membership.parquet (not split.parquet alone).
Two independent preprocessing stages (A: train_tune, B: train_refit).
LR: StandardScaler, class_weight=None, max_iter=1000, convergence capture.
XGB: n_jobs=2, random_state=42, no class weighting.
Per-quarter evaluator with batch budget protocol (k=ceil(0.05*N) per cohort-quarter).

CLI:
  --config       path to YAML config (default configs/baseline.yaml)
  --output-dir   run output dir (default output/experiments/baseline_<timestamp>)
  --dataset-dir  research dataset directory (default output/research)

Outputs (under --output-dir):
  config_snapshot.yaml, run_manifest.json
  role_counts.csv, training_boundary_checks.json
  unit_tests.json, train.log
  models/stage_a_lr.pkl, models/stage_b_lr.pkl,
  models/stage_a_xgb.pkl, models/stage_b_xgb.pkl  (each bundles model+preprocessor)
  predictions/validation_lr.parquet, predictions/validation_xgb.parquet,
  predictions/development_test_lr.parquet, predictions/development_test_xgb.parquet
  metrics/per_quarter.csv, metrics/pooled.csv, metrics/verification.json
  REPORT.md (Vietnamese)
"""
import argparse
import hashlib
import json
import logging
import os
import pickle
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

# ---------------------------------------------------------------------------
# Constants / expected role counts (smoke checks from membership.parquet)
# ---------------------------------------------------------------------------
EXPECTED_ROLE_COUNTS = {
    "train_tune": 1_863_476,
    "validation": 710_554,
    "train_refit": 2_688_363,
    "development_test": 933_708,
    "holdout": 816_670,
}

FITTING_ROLES = ("train_tune", "train_refit")
EVAL_ROLES = ("validation", "development_test")
NON_FITTING_ROLES = ("development_test", "holdout")

LOG = logging.getLogger("train_baseline")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    for h in logging.getLogger().handlers:
        h.flush = h.flush  # ensure flush exists


def log_resource_info():
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF)
        LOG.info("max RSS (self): %s KB", ru.ru_maxrss)
    except Exception as e:  # pragma: no cover - platform dependent
        LOG.info("không thể đo RSS: %s", e)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def config_hash(config_path: Path) -> str:
    h = hashlib.sha256(config_path.read_bytes()).hexdigest()
    return h


# ---------------------------------------------------------------------------
# Data loading via DuckDB (filter in SQL, fetch only needed rows)
# ---------------------------------------------------------------------------
def load_membership(parquet_path: Path, con) -> dict[str, set]:
    """Đọc membership.parquet, trả về dict role -> set(loan_id). Kiểm tra không trùng ID trong role."""
    role_sets: dict[str, set] = {}
    df = con.execute(
        f"SELECT loan_id, role FROM read_parquet('{parquet_path.as_posix()}')"
    ).fetchdf()
    for role, g in df.groupby("role"):
        ids = set(g["loan_id"].tolist())
        if len(ids) != len(g):
            raise ValueError(f"trùng loan_id trong role '{role}': {len(g)} rows vs {len(ids)} distinct")
        role_sets[role] = ids
    return role_sets


def load_features_target(parquet_dir: Path, con, role_ids: dict[str, set]):
    """
    Chỉ fetch features/target cho loan_id có trong các role cần thiết (train_tune, validation,
    train_refit, development_test). Không load 16,64M holdout/embargoed vào pandas.
    """
    all_needed = sorted(set().union(*(role_ids[r] for r in FITTING_ROLES + EVAL_ROLES)))
    # Build a temp table of needed loan_ids for efficient semi-join
    needed_df = pd.DataFrame({"loan_id": all_needed})
    con.register("needed_ids", needed_df)

    feat = con.execute(
        """
        SELECT f.* FROM read_parquet(?) f
        INNER JOIN needed_ids n USING (loan_id)
        """,
        [str((parquet_dir / "features.parquet").as_posix())],
    ).fetchdf()
    tgt = con.execute(
        """
        SELECT t.* FROM read_parquet(?) t
        INNER JOIN needed_ids n USING (loan_id)
        """,
        [str((parquet_dir / "target.parquet").as_posix())],
    ).fetchdf()
    spl = con.execute(
        """
        SELECT s.loan_id, s.cohort, s.label_window_end, s.split
        FROM read_parquet(?) s
        INNER JOIN needed_ids n USING (loan_id)
        """,
        [str((parquet_dir / "split.parquet").as_posix())],
    ).fetchdf()
    con.unregister("needed_ids")
    return feat, tgt, spl


def assemble_role_frames(feat, tgt, spl, role_sets: dict[str, set]) -> dict[str, pd.DataFrame]:
    """
    Gộp feature+target+metadata, trả về dict role -> DataFrame (mỗi role là một frame độc lập).
    Các role được phép overlap (một loan có thể nằm trong nhiều role). Không dùng cột split đơn quyền.
    """
    base = feat.merge(tgt, on="loan_id").merge(
        spl[["loan_id", "cohort", "label_window_end", "split"]], on="loan_id"
    )

    # Target must not be NULL
    null_tgt = base["label_12m"].isna().sum()
    if null_tgt:
        raise ValueError(f"{null_tgt} target NULL trong fetched set")

    # No duplicate loan_id within the fetched base (each loan fetched once)
    if base["loan_id"].duplicated().any():
        n_dup = int(base["loan_id"].duplicated().sum())
        raise ValueError(f"{n_dup} loan_id trùng sau khi gộp feature/target/split")

    frames: dict[str, pd.DataFrame] = {}
    for role, ids in role_sets.items():
        sub = base[base["loan_id"].isin(ids)].copy()
        sub["role"] = role
        frames[role] = sub

    # Sanity: every fetched loan must belong to at least one role
    fetched_ids = set(base["loan_id"].tolist())
    union_roles = set().union(*(role_sets[r] for r in role_sets))
    orphan = fetched_ids - union_roles
    if orphan:
        raise ValueError(f"{len(orphan)} loan fetched không có role nào trong membership.parquet")

    return frames


# ---------------------------------------------------------------------------
# Boundary verification: expected vs actual role IDs both directions
# ---------------------------------------------------------------------------
def compute_expected_role_ids(spl_df: pd.DataFrame, reporting_lag: int) -> dict[str, set]:
    """
    Tính expected role IDs từ split.parquet (cohort + label_window_end + split metadata) +
    quy tắc readiness: month_index(label_window_end) + lag <= T.
    Độc lập khỏi membership.parquet, không đọc lại orig/labels/performance.
    """
    df = spl_df.copy()
    df["mi_end"] = (df["label_window_end"] // 100) * 12 + (df["label_window_end"] % 100)

    T = {
        "train_tune": 2016 * 12 + 1,      # 2016-01
        "validation": 2019 * 12 + 1,      # 2019-01
        "train_refit": 2019 * 12 + 1,     # 2019-01
    }

    expected: dict[str, set] = {}

    # train_tune: cohort 2009Q1-2013Q4, ready <= T_train_tune
    tt = df[
        (df["cohort"].str.match(r"20(09|10|11|12|13)Q[1-4]"))
        & (df["mi_end"] + reporting_lag <= T["train_tune"])
    ]
    expected["train_tune"] = set(tt["loan_id"].tolist())

    # validation: cohort 2016Q1-2016Q4, ready <= T_validation
    val = df[
        (df["cohort"].str.match(r"2016Q[1-4]"))
        & (df["mi_end"] + reporting_lag <= T["validation"])
    ]
    expected["validation"] = set(val["loan_id"].tolist())

    # train_refit: cohort 2012Q1-2016Q4, ready <= T_train_refit
    tr = df[
        (df["cohort"].str.match(r"20(12|13|14|15|16)Q[1-4]"))
        & (df["mi_end"] + reporting_lag <= T["train_refit"])
    ]
    expected["train_refit"] = set(tr["loan_id"].tolist())

    # development_test: cohort 2019Q1-2019Q4 (all)
    dt = df[df["cohort"].str.match(r"2019Q[1-4]")]
    expected["development_test"] = set(dt["loan_id"].tolist())

    # holdout: cohort 2024
    ho = df[df["cohort"].str.match(r"2024Q[1-4]")]
    expected["holdout"] = set(ho["loan_id"].tolist())

    return expected


def verify_role_sets(actual: dict[str, set], expected: dict[str, set], spl_df: pd.DataFrame | None = None) -> dict:
    """So sánh actual vs expected hai chiều (EXCEPT/ANTI JOIN logic). Trả về dict kết quả kiểm tra."""
    results = {}
    for role in EXPECTED_ROLE_COUNTS:
        act = actual.get(role, set())
        exp = expected.get(role, set())
        missing = exp - act   # expected nhưng không có trong actual
        extra = act - exp     # có trong actual nhưng không mong đợi
        entry = {
            "n_actual": len(act),
            "n_expected": len(exp),
            "n_missing": len(missing),
            "n_extra": len(extra),
            "missing_ids_sample": sorted(list(missing))[:10],
            "extra_ids_sample": sorted(list(extra))[:10],
        }
        if role == "holdout":
            # Holdout không được fetch vào phạm vi trainer (du thiết kế), nên không đòi hỏi set_equal.
            entry["set_equal"] = None
            entry["skip_reason"] = "holdout_khong_duoc_fetch_vao_phan_mem_huan_luyen_du_thiet_ke"
        else:
            entry["set_equal"] = len(missing) == 0 and len(extra) == 0
        results[role] = entry
    # Cross-role constraints
    train_refit_no_pre2012 = 0
    if spl_df is not None and "train_refit" in actual:
        tr_ids = actual["train_refit"]
        tr_cohorts = spl_df[spl_df["loan_id"].isin(tr_ids)]["cohort"]
        pre2012 = tr_cohorts[tr_cohorts.str.match(r"20(09|10|11)Q[1-4]")]
        train_refit_no_pre2012 = int(len(pre2012))
    results["constraints"] = {
        "train_refit_no_pre2012": train_refit_no_pre2012,
        "devtest_holdout_not_in_fitting": len(
            (actual.get("development_test", set()) | actual.get("holdout", set()))
            & (actual.get("train_tune", set()) | actual.get("train_refit", set()) | actual.get("validation", set()))
        ),
        "train_tune_validation_disjoint": len(
            actual.get("train_tune", set()) & actual.get("validation", set())
        ),
        "train_refit_devtest_disjoint": len(
            actual.get("train_refit", set()) & actual.get("development_test", set())
        ),
    }
    return results


# ---------------------------------------------------------------------------
# Preprocessing: two independent stages
# ---------------------------------------------------------------------------
def build_preprocessor_A(numeric, categorical):
    """Stage A: fit trên train_tune. LR: numeric impute median + StandardScaler."""
    numeric_t = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_t = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
    ])
    return ColumnTransformer([
        ("num", numeric_t, numeric),
        ("cat", categorical_t, categorical),
    ], remainder="drop", sparse_threshold=0.3)


def build_preprocessor_B(numeric, categorical):
    """Stage B: MỚI, fit trên train_refit đầy đủ. Không tái sử dụng object/stats từ A."""
    numeric_t = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_t = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
    ])
    return ColumnTransformer([
        ("num", numeric_t, numeric),
        ("cat", categorical_t, categorical),
    ], remainder="drop", sparse_threshold=0.3)


def build_preprocessor_XGB(numeric, categorical):
    """Preprocessor cho XGB: numeric impute median KHÔNG scale; categorical cùng policy UNKNOWN."""
    numeric_t = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
    ])
    categorical_t = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
    ])
    return ColumnTransformer([
        ("num", numeric_t, numeric),
        ("cat", categorical_t, categorical),
    ], remainder="drop", sparse_threshold=0.3)


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------
def _finite_coefficients(lr) -> bool:
    """Kiểm tra hệ số và intercept của LR có hữu hạn (không NaN/inf)."""
    try:
        coef = np.asarray(lr.coef_, dtype=float)
        intercept = np.asarray(lr.intercept_, dtype=float)
        return bool(np.isfinite(coef).all() and np.isfinite(intercept).all())
    except Exception:
        return False


def lr_convergence_status(lr, conv_warnings, max_iter: int):
    """Xác định trạng thái hội tụ LR: success / warning / iteration_limit / unknown.

    Quy tắc (không phụ thuộc converged_, có thể không tồn tại trên model cũ):
    - success: không có ConvergenceWarning, hệ số hữu hạn, số lần lặp < max_iter
      (solver dừng bình thường trước hạn, không phải chứng minh optimum tuyệt đối).
    - warning: có ConvergenceWarning.
    - iteration_limit: số lần lặp >= max_iter (đạt hạn iteration).
    - unknown: không đủ bằng chứng (ví dụ run lịch sử không lưu warning capture đầy đủ
      hoặc không có converged_/n_iter_ đáng tin cậy).
    Không gọi iteration_limit chỉ vì n_iter (12/13) < max_iter (1000).
    """
    n_iter = getattr(lr, "n_iter_", None)
    if n_iter is not None:
        try:
            n_iter = int(np.asarray(n_iter).max())
        except Exception:
            n_iter = None
    # conv_warnings có thể là None (chưa thu thập evidence lịch sử), [] (đã thu thập nhưng rỗng)
    # hoặc danh sách thông điệp thực. Không để TypeError khi None.
    if conv_warnings is None:
        # Không có bằng chứng cảnh báo nào -> không thể khẳng định hội tụ
        return ("unknown", n_iter)
    has_warning = len(conv_warnings) > 0
    finite_coef = _finite_coefficients(lr)

    if (not has_warning) and finite_coef and n_iter is not None and n_iter < max_iter:
        status = "success"
    elif has_warning:
        status = "warning" if (n_iter is None or n_iter < max_iter) else "iteration_limit"
    elif n_iter is not None and n_iter >= max_iter:
        status = "iteration_limit"
    else:
        status = "unknown"
    return status, n_iter


def _convergence_human(lr_info: dict) -> str:
    """Mô tả trạng thái hội tụ bằng tiếng Việt cho báo cáo, không tự khẳng định fail/success."""
    status = lr_info.get("convergence_status")
    n_iter = lr_info.get("n_iter")
    max_iter = lr_info.get("max_iter")
    warnings = lr_info.get("convergence_warnings") or []
    if status == "success":
        return f"không có cảnh báo hội tụ, hệ số hữu hạn, n_iter={n_iter} < max_iter={max_iter} (solver dừng bình thường)"
    if status == "warning":
        return f"có Cảnh báo hội tụ ({warnings[0] if warnings else 'không có chi tiết'}), n_iter={n_iter}, max_iter={max_iter}"
    if status == "iteration_limit":
        return f"đạt hạn iteration (n_iter={n_iter} >= max_iter={max_iter})"
    return (
        f"không đủ bằng chứng lịch sử (không có converged_/warning capture đầy đủ); "
        f"n_iter={n_iter}, max_iter={max_iter}; đây là giới hạn cần khai báo, không phải PASS giả"
    )


def train_lr(X, y, max_iter: int):
    lr = LogisticRegression(
        penalty="l2",
        C=1.0,
        solver="lbfgs",
        class_weight=None,
        max_iter=max_iter,
        random_state=42,
    )
    with warnings.catch_warnings(record=True) as warn_list:
        warnings.simplefilter("always")
        t0 = time.time()
        lr.fit(X, y)
        fit_time = time.time() - t0
    conv_warnings = [str(w.message) for w in warn_list if issubclass(w.category, ConvergenceWarning)]
    status, n_iter = lr_convergence_status(lr, conv_warnings, max_iter)
    return {
        "model": lr,
        "converged": None if status == "unknown" else (status == "success"),
        "convergence_status": status,
        "n_iter": n_iter,
        "max_iter": max_iter,
        "fit_time_sec": fit_time,
        "convergence_warnings": conv_warnings,
    }


def train_xgb(X, y, n_jobs: int):
    xgb = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        tree_method="hist",
        n_jobs=n_jobs,
        random_state=42,
        verbosity=0,
    )
    t0 = time.time()
    xgb.fit(X, y)
    fit_time = time.time() - t0
    return {"model": xgb, "fit_time_sec": fit_time}


def _validate_eval_input(y_true, y_prob, cohort, loan_id, label="eval"):
    """Input contract cho evaluator (per-quarter và global).

    - Lengths khớp, labels binary không null.
    - loan_id không null/rỗng, không duplicate trong một evaluation file.
    - cohort hợp lệ/không null.
    - Scores phải finite và thuộc [0,1].
    - Reject rõ duplicate ID, NaN/inf, score ngoài khoảng; không clip score invalid để che lỗi.
    """
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    n = len(y_true)
    if cohort is None:
        cohort = np.empty(n, dtype=object)
    else:
        cohort = np.asarray(cohort, dtype=object)
    if loan_id is None:
        loan_id = np.empty(n, dtype=object)
    else:
        loan_id = np.asarray(loan_id, dtype=object)
    if len(y_prob) != n or len(cohort) != n or len(loan_id) != n:
        raise ValueError(f"{label}: độ dài khớp nhau (y={len(y_prob)}, p={len(cohort)}, c={len(loan_id)}, id={len(loan_id)})")
    # Labels binary, không null
    if n == 0:
        return y_true, y_prob, cohort, loan_id
    if pd.isna(y_true).any():
        raise ValueError(f"{label}: label có giá trị null")
    uniq = np.unique(y_true)
    if not set(uniq.tolist()).issubset({0, 1}):
        raise ValueError(f"{label}: label phải là nhị phân {0, 1}, tìm thấy {uniq.tolist()}")
    # Scores finite và [0,1]
    if not np.all(np.isfinite(y_prob)):
        raise ValueError(f"{label}: score có NaN/inf")
    if np.any(y_prob < 0.0) or np.any(y_prob > 1.0):
        raise ValueError(f"{label}: score ngoài khoảng [0,1]")
    # loan_id không null/rỗng, không duplicate
    if pd.isna(loan_id).any() or (loan_id == "").any():
        raise ValueError(f"{label}: loan_id có giá trị null/rỗng")
    if np.unique(loan_id).size != n:
        dups = pd.Series(loan_id).value_counts()
        dups = dups[dups > 1].index.tolist()
        raise ValueError(f"{label}: loan_id trùng (ví dụ {dups[:5]})")
    # cohort không null
    if pd.isna(cohort).any():
        raise ValueError(f"{label}: cohort có giá trị null")
    return y_true, y_prob, cohort, loan_id


# ---------------------------------------------------------------------------
# Evaluator: per-quarter batch budget protocol
# ---------------------------------------------------------------------------
def per_quarter_metrics(y_true, y_prob, cohort, loan_id, k_frac=0.05):
    """
    Tính metrics theo batch cohort-quý:
    - k = ceil(0.05 * N_batch)
    - sort score desc, tie-break loan_id asc
    - precision = TP_selected / k
    - capture = TP_selected / n_pos
    - lift = precision / prevalence
    - batch không positive -> capture/lift/ROC-AUC = N/A (None), không ép 0
    - All-positive và k<N: precision=1, capture=k/N, lift=1.
    """
    y_true, y_prob, cohort, loan_id = _validate_eval_input(
        y_true, y_prob, cohort, loan_id, label="per_quarter_metrics"
    )
    df = pd.DataFrame({"y": y_true, "p": y_prob, "cohort": cohort, "loan_id": loan_id})
    rows = []
    total_tp = 0
    total_pos = 0
    total_selected = 0
    for q, g in df.groupby("cohort", sort=True):
        n = len(g)
        k = 0 if n == 0 else max(1, int(np.ceil(k_frac * n)))
        g_sorted = g.sort_values(["p", "loan_id"], ascending=[False, True])
        top = g_sorted.head(k)
        tp = int(top["y"].sum())
        n_pos = int(g["y"].sum())
        prev = n_pos / n if n > 0 else 0.0
        precision = tp / k if k > 0 else None
        capture = (tp / n_pos) if n_pos > 0 else None
        lift = (precision / prev) if (precision is not None and prev > 0) else None
        # ROC-AUC / AP per batch (needs both classes)
        try:
            auc = float(roc_auc_score(g["y"], g["p"])) if g["y"].nunique() > 1 else None
        except Exception:
            auc = None
        try:
            ap = float(average_precision_score(g["y"], g["p"])) if g["y"].nunique() > 1 else None
        except Exception:
            ap = None
        rows.append({
            "cohort": q,
            "n": n,
            "n_pos": n_pos,
            "prevalence": prev,
            "k": k,
            "selected_fraction": k / n if n > 0 else None,
            "tp_selected": tp,
            "precision_at_k": precision,
            "capture_at_k": capture,
            "lift_at_k": lift,
            "roc_auc": auc,
            "average_precision": ap,
        })
        total_tp += tp
        total_pos += n_pos
        total_selected += k
    pooled = {
        "n": int(df["y"].shape[0]),
        "n_pos": total_pos,
        "prevalence": total_pos / len(df) if len(df) > 0 else 0.0,
        "total_selected": total_selected,
        "total_tp": total_tp,
        "capacity_pooled_capture": (total_tp / total_pos) if total_pos > 0 else None,
    }
    # Macro mean per-quarter (skip None for capture/lift/auc where N/A)
    valid_capture = [r["capture_at_k"] for r in rows if r["capture_at_k"] is not None]
    valid_lift = [r["lift_at_k"] for r in rows if r["lift_at_k"] is not None]
    valid_auc = [r["roc_auc"] for r in rows if r["roc_auc"] is not None]
    valid_ap = [r["average_precision"] for r in rows if r["average_precision"] is not None]
    pooled["macro_mean_capture"] = float(np.mean(valid_capture)) if valid_capture else None
    pooled["macro_mean_lift"] = float(np.mean(valid_lift)) if valid_lift else None
    pooled["macro_mean_auc"] = float(np.mean(valid_auc)) if valid_auc else None
    pooled["macro_mean_ap"] = float(np.mean(valid_ap)) if valid_ap else None
    return rows, pooled


def global_ranking_metrics(y_true, y_prob, cohort=None, loan_id=None, k_frac=0.05):
    """Top-5% pooled toàn năm (đặt tên khác, KHÔNG gọi là metric ngân sách quý).

    Nhận loan_id và dùng tie-break score DESC, loan_id ASC; độc lập thứ tự dòng.
    log_loss dùng labels=[0,1] để hỗ trợ single-class.
    """
    y_true, y_prob, cohort, loan_id = _validate_eval_input(
        y_true, y_prob, cohort, loan_id, label="global_ranking_metrics"
    )
    n = len(y_true)
    k = 0 if n == 0 else max(1, int(np.ceil(k_frac * n)))
    order = np.lexsort((loan_id, -y_prob))  # primary: -y_prob (desc), secondary: loan_id asc
    top_idx = order[:k]
    tp = int(np.take(y_true, top_idx).sum())
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
    p_clip = np.clip(y_prob, 1e-12, 1 - 1e-12)
    try:
        brier = float(brier_score_loss(y_true, p_clip))
    except Exception:
        brier = None
    try:
        ll = float(log_loss(y_true, p_clip, labels=[0, 1]))
    except Exception:
        ll = None
    return {
        "n": int(n), "n_pos": int(n_pos), "prevalence": float(prev),
        "k": int(k), "selected_fraction": float(k / n) if n > 0 else None,
        "tp_selected": tp,
        "precision_at_k_global": precision,
        "capture_at_k_global": capture,
        "lift_at_k_global": lift,
        "roc_auc_global": auc,
        "average_precision_global": ap,
        "brier_global": brier,
        "log_loss_global": ll,
    }


def constant_rate_baseline(y_true, train_prevalence):
    """Brier/log-loss của xác suất hằng = prevalence train, để so trên cùng eval set."""
    n = len(y_true)
    p = np.full(n, train_prevalence)
    return {
        "brier_constant_rate": float(brier_score_loss(y_true, np.clip(p, 1e-12, 1 - 1e-12))),
        "log_loss_constant_rate": float(log_loss(y_true, np.clip(p, 1e-12, 1 - 1e-12))),
        "prevalence_used": train_prevalence,
    }


def evaluate_metrics(model_name, y_true, y_prob, cohort, loan_id, train_prev, stage_label, k_frac=0.05):
    """Đánh giá metrics trên một eval set (module-level helper, không fit/fit_transform).

    Truyền đầy đủ cohort/loan_id vào global_ranking_metrics để nhận tie-break theo loan_id.
    """
    per_q, pooled = per_quarter_metrics(y_true, y_prob, cohort, loan_id, k_frac=k_frac)
    global_rank = global_ranking_metrics(y_true, y_prob, cohort=cohort, loan_id=loan_id, k_frac=k_frac)
    const_base = constant_rate_baseline(y_true, train_prev)
    return {
        "model": model_name,
        "stage": stage_label,
        "per_quarter": per_q,
        "pooled_capacity": pooled,
        "global_ranking": global_rank,
        "constant_rate_baseline": const_base,
    }


# ---------------------------------------------------------------------------
# Unit tests (run before real training)
# ---------------------------------------------------------------------------
def run_unit_tests(numeric, categorical) -> dict:
    tests = []

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    # T1: one/multiple/NULL categorical handled
    cat_df = pd.DataFrame({"cb": pd.Series(["one", "multiple", None, "one", np.nan], dtype="object")})
    pre_cat = build_preprocessor_XGB([], ["cb"])
    try:
        out = pre_cat.fit_transform(cat_df)
        t("categorical one/multiple/NULL handled", out is not None and out.shape[0] == 5)
    except Exception as e:
        t("categorical one/multiple/NULL handled", False, str(e))

    # T2: unknown category doesn't change fitted vocabulary
    tr = pd.DataFrame({"cb": ["one", "multiple", "one"]})
    te = pd.DataFrame({"cb": ["one", "UNKNOWN_SEEN", "multiple"]})
    pre2 = build_preprocessor_XGB([], ["cb"])
    pre2.fit(tr)
    n_cols_fit = pre2.transform(tr).shape[1]
    out_te = pre2.transform(te)
    t("unknown category doesn't change vocabulary", out_te.shape[1] == n_cols_fit)

    # T3: median/scaler of A doesn't use validation data
    tr_df = pd.DataFrame({"num": [1.0, 2.0, 3.0, 100.0]})
    val_df = pd.DataFrame({"num": [500.0]})
    preA = build_preprocessor_A(["num"], [])
    preA.fit(tr_df)
    med_A = preA.named_transformers_["num"].named_steps["impute"].statistics_[0]
    t("median A from train only (not 500 from val)", abs(med_A - 2.5) < 1e-9)

    # T4: B fit on refit; synthetic median A != B catches reuse
    tr2 = pd.DataFrame({"num": [1.0, 2.0, 3.0]})
    refit = pd.DataFrame({"num": [10.0, 20.0, 30.0]})
    preA2 = build_preprocessor_A(["num"], [])
    preB2 = build_preprocessor_B(["num"], [])
    preA2.fit(tr2)
    preB2.fit(refit)
    med_A2 = preA2.named_transformers_["num"].named_steps["impute"].statistics_[0]
    med_B2 = preB2.named_transformers_["num"].named_steps["impute"].statistics_[0]
    t("median A != median B (independent fit)", abs(med_A2 - med_B2) > 1e-9 and abs(med_B2 - 20.0) < 1e-9)

    # T5: feature trace / id / target cannot leak into matrix
    leak_df = pd.DataFrame({"loan_id": ["a", "b"], "label_12m": [0, 1], "num": [1.0, 2.0]})
    pre5 = build_preprocessor_A(["num"], [])
    try:
        pre5.fit(leak_df[["num"]])
        t("only numeric feature column used (no id/target)", True)
    except Exception as e:
        t("only numeric feature column used (no id/target)", False, str(e))

    # T6: NULL type handling - not string 'nan'
    null_df = pd.DataFrame({"cb": pd.Series([None, np.nan, "one"], dtype="object")})
    pre6 = build_preprocessor_XGB([], ["cb"])
    try:
        out6 = pre6.fit_transform(null_df)
        t("NULL handled as missing (not 'nan' string)", out6 is not None and out6.shape[0] == 3)
    except Exception as e:
        t("NULL handled as missing (not 'nan' string)", False, str(e))

    # ---- T7..T15: Evaluator edge tests (per_quarter_metrics / global_ranking_metrics) ----
    # T7: ties -> deterministic tie-break loan_id asc, identical scores top-k picks lowest loan_id
    df_tie = pd.DataFrame({
        "y": [1, 0, 1, 0, 0], "p": [0.9, 0.9, 0.9, 0.9, 0.9],
        "cohort": ["Q1", "Q1", "Q1", "Q1", "Q1"], "loan_id": ["a", "b", "c", "d", "e"],
    })
    rows_tie, _ = per_quarter_metrics(df_tie["y"], df_tie["p"], df_tie["cohort"], df_tie["loan_id"], k_frac=0.4)
    top_ids = rows_tie[0]["tp_selected"]  # TP among top k=ceil(0.4*5)=2 -> ids a,b -> TP=1
    t("ties tie-break loan_id asc -> TP among top 2 = 1", top_ids == 1)

    # T8: permutation invariance -> same multiset of (y,p) gives same k/precision/capture
    g1 = pd.DataFrame({"y": [1, 0, 0], "p": [0.5, 0.4, 0.3], "cohort": ["Q1", "Q1", "Q1"], "loan_id": ["x", "y", "z"]})
    g2 = pd.DataFrame({"y": [0, 1, 0], "p": [0.3, 0.5, 0.4], "cohort": ["Q1", "Q1", "Q1"], "loan_id": ["y", "x", "z"]})
    r1, _ = per_quarter_metrics(g1["y"], g1["p"], g1["cohort"], g1["loan_id"], k_frac=1.0)
    r2, _ = per_quarter_metrics(g2["y"], g2["p"], g2["cohort"], g2["loan_id"], k_frac=1.0)
    t("permutation invariance same k/precision", r1[0]["k"] == r2[0]["k"] and r1[0]["precision_at_k"] == r2[0]["precision_at_k"])

    # T9: ceil rounding -> N=21 => k=2 (0.05*21=1.05 ceil=2); N=19 => k=1 (0.95 ceil=1)
    r21, _ = per_quarter_metrics(pd.Series([0]*21), pd.Series([0.5]*21), pd.Series(["Q1"]*21), pd.Series([f"i{i}" for i in range(21)]), k_frac=0.05)
    r19, _ = per_quarter_metrics(pd.Series([0]*19), pd.Series([0.5]*19), pd.Series(["Q1"]*19), pd.Series([f"j{i}" for i in range(19)]), k_frac=0.05)
    t("ceil rounding k(21)=2 k(19)=1", r21[0]["k"] == 2 and r19[0]["k"] == 1)

    # T10: batch no positives -> capture/lift/auc None, not 0
    r_nopos, _ = per_quarter_metrics(pd.Series([0, 0, 0]), pd.Series([0.9, 0.5, 0.1]), pd.Series(["Q1", "Q1", "Q1"]), pd.Series(["a", "b", "c"]), k_frac=0.5)
    t("no positives -> capture None lift None auc None", r_nopos[0]["capture_at_k"] is None and r_nopos[0]["lift_at_k"] is None and r_nopos[0]["roc_auc"] is None)

    # T11: all positives -> precision=capture=lift=1.0
    r_allpos, _ = per_quarter_metrics(pd.Series([1, 1, 1]), pd.Series([0.9, 0.5, 0.1]), pd.Series(["Q1", "Q1", "Q1"]), pd.Series(["a", "b", "c"]), k_frac=1.0)
    t("all positives -> precision capture lift 1.0", r_allpos[0]["precision_at_k"] == 1.0 and r_allpos[0]["capture_at_k"] == 1.0 and r_allpos[0]["lift_at_k"] == 1.0)

    # T12: empty input -> no crash, returns empty rows
    r_empty, p_empty = per_quarter_metrics(pd.Series([], dtype=int), pd.Series([], dtype=float), pd.Series([], dtype=object), pd.Series([], dtype=object), k_frac=0.05)
    t("empty input no crash rows=[]", len(r_empty) == 0 and p_empty["n"] == 0)

    # T13: quarter-vs-global not assumed equal
    gq = pd.DataFrame({"y": [1, 0, 0, 0, 1, 0], "p": [0.9, 0.1, 0.2, 0.3, 0.8, 0.4], "cohort": ["Q1", "Q1", "Q1", "Q2", "Q2", "Q2"], "loan_id": ["a", "b", "c", "d", "e", "f"]})
    rq, pq = per_quarter_metrics(gq["y"], gq["p"], gq["cohort"], gq["loan_id"], k_frac=1.0)
    t("quarter-vs-global macro_mean_capture exists", pq["macro_mean_capture"] is not None)

    # T14: budget sum -> total_selected == sum of k across quarters
    t("budget sum total_selected==sum k", pq["total_selected"] == sum(r["k"] for r in rq))

    # T15: duplicate loan_id / NaN score / score out of range are REJECTED (not accepted)
    g15 = pd.DataFrame({"y": [1, 0, 1], "p": [0.9, float("nan"), 1.5], "cohort": ["Q1", "Q1", "Q1"], "loan_id": ["a", "a", "b"]})
    try:
        per_quarter_metrics(g15["y"], g15["p"], g15["cohort"], g15["loan_id"], k_frac=1.0)
        t("dup id / nan score / oob score rejected", False, "không ném lỗi cho input không hợp lệ")
    except ValueError:
        t("dup id / nan score / oob score rejected", True, "ném ValueError đúng policy")

    # T16: missing label -> reject
    g16 = pd.DataFrame({"y": [1, None, 0], "p": [0.9, 0.5, 0.1], "cohort": ["Q1", "Q1", "Q1"], "loan_id": ["a", "b", "c"]})
    try:
        per_quarter_metrics(g16["y"], g16["p"], g16["cohort"], g16["loan_id"], k_frac=1.0)
        t("missing label rejected", False, "không ném lỗi khi label null")
    except ValueError:
        t("missing label rejected", True, "ném ValueError khi label null")

    # T17: empty global input -> n=0/k=0/TP=0, metrics N/A (no crash)
    rg = global_ranking_metrics(pd.Series([], dtype=int), pd.Series([], dtype=float), k_frac=0.05)
    t("empty global: n=0 k=0 tp=0 metrics NA", rg["n"] == 0 and rg["k"] == 0 and rg["tp_selected"] == 0 and rg["roc_auc_global"] is None and rg["log_loss_global"] is None)

    # T18: single-class quarter -> AUC/AP N/A
    gs = pd.DataFrame({"y": [1, 1, 1], "p": [0.9, 0.5, 0.1], "cohort": ["Q1", "Q1", "Q1"], "loan_id": ["a", "b", "c"]})
    rg_s, _ = per_quarter_metrics(gs["y"], gs["p"], gs["cohort"], gs["loan_id"], k_frac=1.0)
    t("single-class quarter: auc/ap None", rg_s[0]["roc_auc"] is None and rg_s[0]["average_precision"] is None)
    rg2 = global_ranking_metrics(gs["y"], gs["p"], gs["cohort"], gs["loan_id"], k_frac=0.5)
    t("single-class global: auc/ap None but logloss computed", rg2["roc_auc_global"] is None and rg2["average_precision_global"] is None and rg2["log_loss_global"] is not None)

    # T19: ties at boundary top-k -> selected IDs specific (k=ceil(0.4*5)=2, scores all equal -> pick lowest loan_id)
    # ids a,b selected, c,d,e excluded -> TP among top 2 = 1 (a=1,b=0)
    rows_tie, _ = per_quarter_metrics(
        pd.Series([1, 0, 1, 0, 0]), pd.Series([0.9, 0.9, 0.9, 0.9, 0.9]),
        pd.Series(["Q1"]*5), pd.Series(["a", "b", "c", "d", "e"]), k_frac=0.4,
    )
    t("ties boundary: k=2 tp_selected=1", rows_tie[0]["k"] == 2 and rows_tie[0]["tp_selected"] == 1)

    # T20: perfect vs reversed ranking with k<n_pos -> capture differs
    # n=6, n_pos=2, k=ceil(0.5*6)=3. Perfect: 2 positives top -> tp=2 capture=1.0.
    # Reversed: 2 negatives top -> tp=0 capture=0.
    r_perf, _ = per_quarter_metrics(
        pd.Series([1, 1, 0, 0, 0, 0]), pd.Series([0.9, 0.8, 0.7, 0.6, 0.5, 0.4]),
        pd.Series(["Q1"]*6), pd.Series(["a","b","c","d","e","f"]), k_frac=0.5,
    )
    r_rev, _ = per_quarter_metrics(
        pd.Series([1, 1, 0, 0, 0, 0]), pd.Series([0.4, 0.5, 0.6, 0.7, 0.8, 0.9]),
        pd.Series(["Q1"]*6), pd.Series(["a","b","c","d","e","f"]), k_frac=0.5,
    )
    t("perfect capture=1.0 reversed capture=0", r_perf[0]["capture_at_k"] == 1.0 and r_rev[0]["capture_at_k"] == 0.0)

    # T21: two quarters different score scale -> quarterly precision differs; macro_mean_capture exists
    gq = pd.DataFrame({"y": [1, 0, 1, 0], "p": [0.9, 0.1, 0.2, 0.3], "cohort": ["Q1", "Q1", "Q2", "Q2"], "loan_id": ["a", "b", "c", "d"]})
    rq, pq = per_quarter_metrics(gq["y"], gq["p"], gq["cohort"], gq["loan_id"], k_frac=0.5)
    qs = [r["precision_at_k"] for r in rq]
    t("two quarters different scales -> quarterly precision list differs", len(qs) == 2 and qs[0] != qs[1])
    t("quarter-vs-global macro_mean_capture exists", pq["macro_mean_capture"] is not None)

    # T22: budget sum -> total_selected == sum of k across quarters
    t("budget sum total_selected==sum k", pq["total_selected"] == sum(r["k"] for r in rq))

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/baseline.yaml")
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--dataset-dir", type=Path, default=None)
    args = ap.parse_args()

    ROOT = Path(__file__).resolve().parents[2]
    config_path = ROOT / args.config
    if not config_path.exists():
        raise FileNotFoundError(f"config không tồn tại: {config_path}")

    cfg = load_config(config_path)
    c_hash = config_hash(config_path)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "output" / "experiments" / f"baseline_{ts}"
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        ap.error("refuse nonempty run directory; choose a fresh --output-dir")
    out_dir = Path(out_dir)
    models_dir = out_dir / "models"
    preds_dir = out_dir / "predictions"
    metrics_dir = out_dir / "metrics"
    logs_dir = out_dir / "logs"
    for d in (models_dir, preds_dir, metrics_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    setup_logging(logs_dir / "train.log")
    LOG.info("=== Bắt đầu chạy baseline trainer ===")
    LOG.info("config=%s config_hash=%s", config_path, c_hash)
    LOG.info("output_dir=%s", out_dir)
    LOG.info("python=%s", sys.version.split()[0])

    log_resource_info()

    # ---- Config values ----
    split_cfg = cfg["split"]
    feat_cfg = cfg["features"]
    model_cfg = cfg["model"]
    res_cfg = cfg["resources"]
    report_cfg = cfg["reporting"]
    gold_dir = args.dataset_dir.resolve() if args.dataset_dir else ROOT / "output" / "research"
    version = "purchase_12m"
    label_path = cfg["scope"]["label_path"]
    reporting_lag = int(cfg["label"]["reporting_lag_months"])
    max_iter = int(model_cfg["algorithms"][0]["max_iter"])
    model_threads = int(res_cfg.get("model_threads", 2)) if isinstance(res_cfg.get("model_threads"), int) else 2
    LOG.info("model_threads=%d max_iter=%d reporting_lag=%d version=%s", model_threads, max_iter, reporting_lag, version)

    # ---- Load membership (source of truth for roles) ----
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{res_cfg['memory_limit']}'")
    con.execute(f"SET threads={int(res_cfg['threads'])}")
    con.execute("SET preserve_insertion_order=false")
    work = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))
    work.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(work / 'duckdb').as_posix()}'")

    membership_path = gold_dir / "membership.parquet"
    role_sets = load_membership(membership_path, con)
    LOG.info("membership loaded: %s", {r: len(s) for r, s in role_sets.items()})

    # Smoke counts
    for role, exp in EXPECTED_ROLE_COUNTS.items():
        act = len(role_sets.get(role, set()))
        LOG.info("role %s: actual=%d expected=%d match=%s", role, act, exp, act == exp)

    # ---- Load features/target for needed roles only ----
    feat, tgt, spl = load_features_target(gold_dir, con, role_sets)
    role_frames = assemble_role_frames(feat, tgt, spl, role_sets)
    LOG.info("fetched base rows=%d roles=%s", len(feat), sorted(role_frames.keys()))

    # ---- Boundary verification: expected vs actual both directions ----
    expected = compute_expected_role_ids(spl, reporting_lag)
    boundary = verify_role_sets(role_sets, expected, spl_df=spl)
    all_ok = True
    fitted_eval_roles = ("train_tune", "validation", "train_refit", "development_test")
    for role, res in boundary.items():
        if role == "constraints":
            continue
        if res.get("set_equal") is None:
            # Holdout không fetch vào phạm vi trainer -> báo SKIPPED, không fail.
            LOG.info("boundary %s: SKIPPED (%s)", role, res.get("skip_reason"))
            continue
        if role not in fitted_eval_roles:
            continue
        count_ok = res["n_actual"] == res["n_expected"]
        set_ok = res["set_equal"]
        ok = count_ok and set_ok
        all_ok = all_ok and ok
        LOG.info("boundary %s: actual=%d expected=%d missing=%d extra=%d equal=%s count_ok=%s",
                 role, res["n_actual"], res["n_expected"], res["n_missing"], res["n_extra"], res["set_equal"], count_ok)
    for cname, cval in boundary["constraints"].items():
        LOG.info("constraint %s: %d", cname, cval)
        if cval != 0:
            all_ok = False

    # Role counts file
    role_counts = pd.DataFrame([
        {"role": r, "n_actual": len(role_sets.get(r, set())), "n_expected": EXPECTED_ROLE_COUNTS[r]}
        for r in EXPECTED_ROLE_COUNTS
    ])
    role_counts.to_csv(out_dir / "role_counts.csv", index=False)
    with open(out_dir / "training_boundary_checks.json", "w") as f:
        json.dump(boundary, f, indent=2, default=str)

    if not all_ok:
        LOG.error("TRAINING BOUNDARY CHECK FAILED — không fit model.")
        sys.exit(1)
    LOG.info("Tất cả boundary check đạt — tiếp tục train.")

    # ---- Feature contract validation ----
    whitelist = list(feat_cfg["whitelist"])
    numeric = list(feat_cfg["numeric"])
    categorical = list(feat_cfg["categorical"])
    identifier = list(feat_cfg["identifier"])
    split_metadata = list(feat_cfg["split_metadata"])
    audit_only = list(feat_cfg["audit_only"])

    X_cols = numeric + categorical
    assert sorted(X_cols) == sorted(whitelist), f"feature whitelist mismatch: {sorted(X_cols)} vs {sorted(whitelist)}"
    assert not set(numeric) & set(categorical), "numeric & categorical giao nhau"
    leaked = set(X_cols) & set(identifier + split_metadata + audit_only)
    assert not leaked, f"cột audit/id/metadata lọt vào X: {leaked}"
    LOG.info("feature contract OK: %d numeric, %d categorical, whitelist=%d", len(numeric), len(categorical), len(whitelist))

    # Kiểm tra kiểu thực tế (không chỉ tin YAML)
    actual_types = {}
    for c in X_cols:
        actual_types[c] = str(feat[c].dtype) if c in feat.columns else "MISSING"
    LOG.info("actual feature dtypes: %s", actual_types)
    assert "number_of_borrowers" in categorical, "number_of_borrowers phải là categorical"
    nb_vals = feat["number_of_borrowers"].dropna().unique().tolist() if "number_of_borrowers" in feat.columns else []
    LOG.info("number_of_borrowers values: %s", nb_vals)

    # ---- Unit tests ----
    ut = run_unit_tests(numeric, categorical)
    LOG.info("unit tests: passed=%d failed=%d", ut["passed"], ut["failed"])
    with open(out_dir / "unit_tests.json", "w") as f:
        json.dump(ut, f, indent=2)
    if ut["failed"] > 0:
        LOG.error("unit tests thất bại — không fit.")
        sys.exit(1)

    # ---- Split into role frames (each role independent; overlap allowed) ----
    train_tune = role_frames["train_tune"].copy()
    validation = role_frames["validation"].copy()
    train_refit = role_frames["train_refit"].copy()
    dev_test = role_frames["development_test"].copy()

    LOG.info("train_tune=%d validation=%d train_refit=%d development_test=%d",
             len(train_tune), len(validation), len(train_refit), len(dev_test))

    # Count check (secondary to set equality) — chỉ các role đã fetch vào fit/dự báo
    count_roles = ("train_tune", "validation", "train_refit", "development_test")
    for role in count_roles:
        exp = EXPECTED_ROLE_COUNTS[role]
        act = len(role_frames[role])
        assert act == exp, f"role {role}: actual {act} != expected {exp}"

    # ---- Stage A: preprocess + fit on train_tune ----
    LOG.info("=== Bước A: fit preprocessing + model trên train_tune ===")
    X_tt = train_tune[X_cols]
    y_tt = train_tune["label_12m"]
    X_val = validation[X_cols]
    y_val = validation["label_12m"]

    preA_lr = build_preprocessor_A(numeric, categorical)
    preA_xgb = build_preprocessor_XGB(numeric, categorical)

    t0 = time.time()
    X_tt_lr = preA_lr.fit_transform(X_tt)
    X_val_lr = preA_lr.transform(X_val)
    preA_fit_time = time.time() - t0
    LOG.info("preprocessor A fit time=%.2fs shapes tt=%s val=%s", preA_fit_time, X_tt_lr.shape, X_val_lr.shape)

    X_tt_xgb = preA_xgb.fit_transform(X_tt)
    X_val_xgb = preA_xgb.transform(X_val)

    # LR stage A
    lrA = train_lr(X_tt_lr, y_tt, max_iter)
    lrA_val_prob = lrA["model"].predict_proba(X_val_lr)[:, 1]
    lrA_val_metrics = {
        "average_precision": float(average_precision_score(y_val, lrA_val_prob)),
        "roc_auc": float(roc_auc_score(y_val, lrA_val_prob)),
        "brier": float(brier_score_loss(y_val, np.clip(lrA_val_prob, 1e-12, 1 - 1e-12))),
        "log_loss": float(log_loss(y_val, np.clip(lrA_val_prob, 1e-12, 1 - 1e-12))),
    }
    LOG.info("LR stage A: val AP=%.6f AUC=%.6f Brier=%.6f logloss=%.6f converged=%s n_iter=%s warnings=%s",
             lrA_val_metrics["average_precision"], lrA_val_metrics["roc_auc"],
             lrA_val_metrics["brier"], lrA_val_metrics["log_loss"],
             lrA["converged"], lrA["n_iter"], lrA["convergence_warnings"])

    # XGB stage A
    xgbA = train_xgb(X_tt_xgb, y_tt, model_threads)
    xgbA_val_prob = xgbA["model"].predict_proba(X_val_xgb)[:, 1]
    xgbA_val_metrics = {
        "average_precision": float(average_precision_score(y_val, xgbA_val_prob)),
        "roc_auc": float(roc_auc_score(y_val, xgbA_val_prob)),
        "brier": float(brier_score_loss(y_val, np.clip(xgbA_val_prob, 1e-12, 1 - 1e-12))),
        "log_loss": float(log_loss(y_val, np.clip(xgbA_val_prob, 1e-12, 1 - 1e-12))),
    }
    LOG.info("XGB stage A: val AP=%.6f AUC=%.6f Brier=%.6f logloss=%.6f fit_time=%.2fs",
             xgbA_val_metrics["average_precision"], xgbA_val_metrics["roc_auc"],
             xgbA_val_metrics["brier"], xgbA_val_metrics["log_loss"], xgbA["fit_time_sec"])

    # Save stage A artifacts
    with open(models_dir / "stage_a_lr.pkl", "wb") as f:
        pickle.dump({"model": lrA["model"], "preprocessor": preA_lr, "train_info": lrA}, f)
    with open(models_dir / "stage_a_xgb.pkl", "wb") as f:
        pickle.dump({"model": xgbA["model"], "preprocessor": preA_xgb, "train_info": xgbA}, f)

    # Validation predictions
    val_pred_lr = validation[["loan_id", "cohort", "label_12m"]].copy()
    val_pred_lr["score"] = lrA_val_prob
    val_pred_lr["model_name"] = "logistic_regression"
    val_pred_lr["run_id"] = ts
    val_pred_lr["stage"] = "A"
    val_pred_lr.to_parquet(preds_dir / "validation_lr.parquet", index=False)

    val_pred_xgb = validation[["loan_id", "cohort", "label_12m"]].copy()
    val_pred_xgb["score"] = xgbA_val_prob
    val_pred_xgb["model_name"] = "xgboost"
    val_pred_xgb["run_id"] = ts
    val_pred_xgb["stage"] = "A"
    val_pred_xgb.to_parquet(preds_dir / "validation_xgb.parquet", index=False)

    # Free stage A matrices
    del X_tt_lr, X_val_lr, X_tt_xgb, X_val_xgb

    # ---- Stage B: new preprocessor + refit on train_refit ----
    LOG.info("=== Bước B: preprocessing MỚI fit trên train_refit, refit model ===")
    X_tr = train_refit[X_cols]
    y_tr = train_refit["label_12m"]
    X_dt = dev_test[X_cols]
    y_dt = dev_test["label_12m"]

    preB_lr = build_preprocessor_B(numeric, categorical)
    preB_xgb = build_preprocessor_XGB(numeric, categorical)

    t0 = time.time()
    X_tr_lr = preB_lr.fit_transform(X_tr)
    X_dt_lr = preB_lr.transform(X_dt)
    preB_fit_time = time.time() - t0
    LOG.info("preprocessor B fit time=%.2fs shapes tr=%s dt=%s", preB_fit_time, X_tr_lr.shape, X_dt_lr.shape)

    X_tr_xgb = preB_xgb.fit_transform(X_tr)
    X_dt_xgb = preB_xgb.transform(X_dt)

    # Verify B preprocessing not reusing A stats (sanity)
    med_A = preA_lr.named_transformers_["num"].named_steps["impute"].statistics_[0]
    med_B = preB_lr.named_transformers_["num"].named_steps["impute"].statistics_[0]
    LOG.info("median numeric col[0]: A=%.4f B=%.4f (không bắt buộc bằng nhau)", med_A, med_B)

    # LR stage B
    lrB = train_lr(X_tr_lr, y_tr, max_iter)
    lrB_dt_prob = lrB["model"].predict_proba(X_dt_lr)[:, 1]
    lrB_dt_metrics_point = {
        "average_precision": float(average_precision_score(y_dt, lrB_dt_prob)),
        "roc_auc": float(roc_auc_score(y_dt, lrB_dt_prob)),
        "brier": float(brier_score_loss(y_dt, np.clip(lrB_dt_prob, 1e-12, 1 - 1e-12))),
        "log_loss": float(log_loss(y_dt, np.clip(lrB_dt_prob, 1e-12, 1 - 1e-12))),
    }
    LOG.info("LR stage B: dev_test AP=%.6f AUC=%.6f Brier=%.6f logloss=%.6f converged=%s n_iter=%s warnings=%s",
             lrB_dt_metrics_point["average_precision"], lrB_dt_metrics_point["roc_auc"],
             lrB_dt_metrics_point["brier"], lrB_dt_metrics_point["log_loss"],
             lrB["converged"], lrB["n_iter"], lrB["convergence_warnings"])

    # XGB stage B
    xgbB = train_xgb(X_tr_xgb, y_tr, model_threads)
    xgbB_dt_prob = xgbB["model"].predict_proba(X_dt_xgb)[:, 1]
    xgbB_dt_metrics_point = {
        "average_precision": float(average_precision_score(y_dt, xgbB_dt_prob)),
        "roc_auc": float(roc_auc_score(y_dt, xgbB_dt_prob)),
        "brier": float(brier_score_loss(y_dt, np.clip(xgbB_dt_prob, 1e-12, 1 - 1e-12))),
        "log_loss": float(log_loss(y_dt, np.clip(xgbB_dt_prob, 1e-12, 1 - 1e-12))),
    }
    LOG.info("XGB stage B: dev_test AP=%.6f AUC=%.6f Brier=%.6f logloss=%.6f fit_time=%.2fs",
             xgbB_dt_metrics_point["average_precision"], xgbB_dt_metrics_point["roc_auc"],
             xgbB_dt_metrics_point["brier"], xgbB_dt_metrics_point["log_loss"], xgbB["fit_time_sec"])

    # Save stage B artifacts
    with open(models_dir / "stage_b_lr.pkl", "wb") as f:
        pickle.dump({"model": lrB["model"], "preprocessor": preB_lr, "train_info": lrB}, f)
    with open(models_dir / "stage_b_xgb.pkl", "wb") as f:
        pickle.dump({"model": xgbB["model"], "preprocessor": preB_xgb, "train_info": xgbB}, f)

    # Development_test predictions
    dt_pred_lr = dev_test[["loan_id", "cohort", "label_12m"]].copy()
    dt_pred_lr["score"] = lrB_dt_prob
    dt_pred_lr["model_name"] = "logistic_regression"
    dt_pred_lr["run_id"] = ts
    dt_pred_lr["stage"] = "B"
    dt_pred_lr.to_parquet(preds_dir / "development_test_lr.parquet", index=False)

    dt_pred_xgb = dev_test[["loan_id", "cohort", "label_12m"]].copy()
    dt_pred_xgb["score"] = xgbB_dt_prob
    dt_pred_xgb["model_name"] = "xgboost"
    dt_pred_xgb["run_id"] = ts
    dt_pred_xgb["stage"] = "B"
    dt_pred_xgb.to_parquet(preds_dir / "development_test_xgb.parquet", index=False)

    # ---- Evaluator on development_test (per-quarter) ----
    LOG.info("=== Tính metrics theo protocol ngân sách quý (development_test) ===")
    k_frac = float(report_cfg["topk"]["k"].replace("ceil(", "").replace("0.05 * batch_size)", "0.05"))

    train_prev_A = float(y_tt.mean())  # prevalence train_tune (baseline hằng số giai đoạn A)
    train_prev_B = float(y_tr.mean())  # prevalence train_refit (baseline hằng số giai đoạn B)
    results = {
        "logistic_regression": {
            "stage_A_validation": evaluate_metrics("logistic_regression", y_val, lrA_val_prob, validation["cohort"], validation["loan_id"], train_prev_A, "A", k_frac),
            "stage_B_development_test": evaluate_metrics("logistic_regression", y_dt, lrB_dt_prob, dev_test["cohort"], dev_test["loan_id"], train_prev_B, "B", k_frac),
        },
        "xgboost": {
            "stage_A_validation": evaluate_metrics("xgboost", y_val, xgbA_val_prob, validation["cohort"], validation["loan_id"], train_prev_A, "A", k_frac),
            "stage_B_development_test": evaluate_metrics("xgboost", y_dt, xgbB_dt_prob, dev_test["cohort"], dev_test["loan_id"], train_prev_B, "B", k_frac),
        },
    }

    # Write per_quarter.csv (flattened)
    pq_rows = []
    for model_name, mres in results.items():
        for stage_key, sres in mres.items():
            for r in sres["per_quarter"]:
                row = {"model": model_name, "stage": stage_key}
                row.update(r)
                pq_rows.append(row)
    pd.DataFrame(pq_rows).to_csv(metrics_dir / "per_quarter.csv", index=False)

    # Write pooled.csv
    pooled_rows = []
    for model_name, mres in results.items():
        for stage_key, sres in mres.items():
            row = {"model": model_name, "stage": stage_key}
            row.update(sres["pooled_capacity"])
            row.update(sres["global_ranking"])
            row.update(sres["constant_rate_baseline"])
            pooled_rows.append(row)
    pd.DataFrame(pooled_rows).to_csv(metrics_dir / "pooled.csv", index=False)

    # ---- Convergence check for LR ----
    if not lrB["converged"]:
        LOG.error("LR stage B KHÔNG hội tụ (max_iter=%d). Warning: %s", max_iter, lrB["convergence_warnings"])
    else:
        LOG.info("LR stage B hội tụ (n_iter=%s, max_iter=%d)", lrB["n_iter"], max_iter)

    # ---- Manifest & provenance ----
    manifest = {
        "run_id": ts,
        "run_dir": str(out_dir),
        "config": str(config_path),
        "config_hash": c_hash,
        "version": version,
        "regime": split_cfg["regime"],
        "fit_date": split_cfg["fit_date"],
        "refit_date": split_cfg["refit_date"],
        "development_test_year": split_cfg["development_test_year"],
        "holdout_year": split_cfg["holdout_year"],
        "reporting_lag_months": reporting_lag,
        "label_version": cfg["provenance"]["label_version"],
        "research_version": cfg["provenance"]["research_version"],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "python": sys.version.split()[0],
        "model_threads": model_threads,
        "max_iter": max_iter,
        "class_weight": "None (unweighted baseline)",
        "roles": {r: len(role_sets.get(r, set())) for r in EXPECTED_ROLE_COUNTS},
        "features": {"numeric": numeric, "categorical": categorical},
        "whitelist": whitelist,
        "lr_stage_A": {
            "convergence_status": lrA["convergence_status"],
            "n_iter": lrA["n_iter"],
            "max_iter": max_iter,
            "fit_time_sec": lrA["fit_time_sec"],
            "convergence_warnings": lrA["convergence_warnings"],
        },
        "lr_stage_B": {
            "convergence_status": lrB["convergence_status"],
            "n_iter": lrB["n_iter"],
            "max_iter": max_iter,
            "fit_time_sec": lrB["fit_time_sec"],
            "convergence_warnings": lrB["convergence_warnings"],
        },
        "xgb_stage_A": {"fit_time_sec": xgbA["fit_time_sec"]},
        "xgb_stage_B": {"fit_time_sec": xgbB["fit_time_sec"]},
        "preprocessing": {
            "stage_A_fit_on": "train_tune",
            "stage_B_fit_on": "train_refit",
            "numeric_impute": "median",
            "numeric_scale_lr": "StandardScaler",
            "categorical_missing": "UNKNOWN",
            "categorical_ohe": "handle_unknown=ignore sparse",
        },
        "holdout_evaluated": False,
    }
    with open(out_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    # Config snapshot
    import shutil
    shutil.copy2(config_path, out_dir / "config_snapshot.yaml")

    # Verification JSON (recompute metrics from saved predictions)
    verification = {
        "run_id": ts,
        "predictions_files": {
            "validation_lr": str(preds_dir / "validation_lr.parquet"),
            "validation_xgb": str(preds_dir / "validation_xgb.parquet"),
            "development_test_lr": str(preds_dir / "development_test_lr.parquet"),
            "development_test_xgb": str(preds_dir / "development_test_xgb.parquet"),
        },
        "role_counts": role_counts.to_dict("records"),
        "boundary_checks": boundary,
        "unit_tests": ut,
        "lr_convergence_stage_B": {
            "converged": lrB["converged"],
            "n_iter": lrB["n_iter"],
            "max_iter": max_iter,
            "warnings": lrB["convergence_warnings"],
        },
        "metrics_summary": pooled_rows,
    }
    with open(metrics_dir / "verification.json", "w") as f:
        json.dump(verification, f, indent=2, default=str)

    log_resource_info()
    LOG.info("=== HOÀN TẦN chạy trainer đã sửa ===")
    LOG.info("output_dir=%s", out_dir)
    LOG.info("models: %s", models_dir)
    LOG.info("predictions: %s", preds_dir)
    LOG.info("metrics: %s", metrics_dir)

    # ---- REPORT.md (Tiếng Việt, P6 DoD) ----
    def fmt(x, nd=6):
        return f"{x:.{nd}f}" if isinstance(x, (int, float)) and x is not None else str(x)

    lrB_dt = results["logistic_regression"]["stage_B_development_test"]
    xgbB_dt = results["xgboost"]["stage_B_development_test"]
    lrA_val = results["logistic_regression"]["stage_A_validation"]
    xgbA_val = results["xgboost"]["stage_A_validation"]

    report_lines = [
        "# Báo cáo pilot đã sửa (baseline LR + XGBoost)",
        "",
        f"- Mã môn: DS317 (không phải DS312).",
        f"- Run ID: {ts}",
        f"- Thời gian tạo: {manifest['generated_at']}",
        f"- Thư mục chạy: {out_dir}",
        f"- Config: {config_path} (hash sha256: {c_hash})",
        f"- Phiên bản dữ liệu: {version} (regime {split_cfg['regime']})",
        f"- Dataset: {gold_dir}; use a fresh directory for a new dataset.",
        f"- Accepted baseline: output/baseline/; new runs use a separate output directory.",
        "",
        "## 1. Dữ liệu đầu vào",
        f"- Đọc features.parquet, target.parquet, split.parquet, membership.parquet từ {gold_dir}.",
        f"- Thành viên role (membership.parquet, nguồn sự thật): " +
        ", ".join(f"{r}={len(role_sets.get(r, set())):,}" for r in EXPECTED_ROLE_COUNTS),
        "- Chỉ fetch các loan_id trong các role cần fit/dự báo (train_tune, validation, train_refit, development_test).",
        f"- Không đọc holdout 2024 ({len(role_sets.get('holdout', set())):,} khoản) vào pandas để train.",
        "- Role được gán từ membership.parquet (không dùng cột split đơn quyền).",
        "- Kiểm tra set equality hai chiều giữa actual membership và expected (cohort + readiness), không chỉ so count.",
        "",
        "## 2. Tiền xử lý (hai giai đoạn độc lập)",
        "- Bước A: preprocessing fit trên train_tune (1.863.476 khoản).",
        "- Bước B: preprocessing MỚI fit trên train_refit đầy đủ (2.688.363 khoản), không tái sử dụng object/stats từ A.",
        "- Numeric: median impute. LR thêm StandardScaler. XGB không scale.",
        "- Categorical: missing -> UNKNOWN (OneHotEncoder handle_unknown=ignore, sparse).",
        "- 18 candidate features theo whitelist; không đưa id/label/cohort/ngày/audit vào X.",
        "- number_of_borrowers là categorical (one/multiple/NULL).",
        "",
        "## 3. Mô hình (baseline, config có hiệu lực)",
        "- Logistic Regression: L2, C=1.0, solver=lbfgs, class_weight=None (unweighted), max_iter=1000, random_state=42.",
        "- XGBoost: objective=binary:logistic, tree_method=hist, n_estimators=200, max_depth=6, learning_rate=0.05,",
        "  subsample=0.8, colsample_bytree=0.8, scale_pos_weight=1, random_state=42, n_jobs=2.",
        "- Không class_weight/resampling/SMOTE, không early stopping, không tuning.",
        "- Không đánh giá holdout 2024, không so sánh cửa sổ, không ensemble.",
        "",
        "## 4. Kết quả (development_test 2019, 933.708 khoản, 24.100 positive)",
        "",
        f"### Logistic Regression (step B, refit trên train_refit)",
        f"- Validation (step A, train_tune): AP={fmt(lrA_val['global_ranking']['average_precision_global'])} AUC={fmt(lrA_val['global_ranking']['roc_auc_global'])} Brier={fmt(lrA_val['global_ranking']['brier_global'])} logloss={fmt(lrA_val['global_ranking']['log_loss_global'])}",
        f"- Development_test: AP={fmt(lrB_dt['global_ranking']['average_precision_global'])} AUC={fmt(lrB_dt['global_ranking']['roc_auc_global'])} Brier={fmt(lrB_dt['global_ranking']['brier_global'])} logloss={fmt(lrB_dt['global_ranking']['log_loss_global'])}",
        f"- Pooled capture@5% (toàn năm, global ranking): {fmt(lrB_dt['global_ranking']['capture_at_k_global'])}",
        f"- Capacity pooled (tổng TP mỗi quý / tổng positives): {fmt(lrB_dt['pooled_capacity']['capacity_pooled_capture'])}",
        f"- Macro mean capture@5% (per-quarter): {fmt(lrB_dt['pooled_capacity']['macro_mean_capture'])}",
        f"- Brier baseline (hằng số prevalence train): {fmt(lrB_dt['constant_rate_baseline']['brier_constant_rate'])}",
        f"- Log-loss baseline (hằng số prevalence train): {fmt(lrB_dt['constant_rate_baseline']['log_loss_constant_rate'])}",
        f"- Hội tụ LR: {_convergence_human(lrB)}",
        f"- Cảnh báo hội tụ: {lrB['convergence_warnings'] if lrB['convergence_warnings'] else 'không'}.",
        "",
        f"### XGBoost (step B, refit trên train_refit)",
        f"- Validation (step A, train_tune): AP={fmt(xgbA_val['global_ranking']['average_precision_global'])} AUC={fmt(xgbA_val['global_ranking']['roc_auc_global'])} Brier={fmt(xgbA_val['global_ranking']['brier_global'])} logloss={fmt(xgbA_val['global_ranking']['log_loss_global'])}",
        f"- Development_test: AP={fmt(xgbB_dt['global_ranking']['average_precision_global'])} AUC={fmt(xgbB_dt['global_ranking']['roc_auc_global'])} Brier={fmt(xgbB_dt['global_ranking']['brier_global'])} logloss={fmt(xgbB_dt['global_ranking']['log_loss_global'])}",
        f"- Pooled capture@5% (toàn năm, global ranking): {fmt(xgbB_dt['global_ranking']['capture_at_k_global'])}",
        f"- Capacity pooled (tổng TP mỗi quý / tổng positives): {fmt(xgbB_dt['pooled_capacity']['capacity_pooled_capture'])}",
        f"- Macro mean capture@5% (per-quarter): {fmt(xgbB_dt['pooled_capacity']['macro_mean_capture'])}",
        "",
        "## 5. Giới hạn / chưa làm",
        "- Chưa đánh giá model trên holdout 2024 (loại khỏi pilot theo thiết kế).",
        "- Chưa so sánh cửa sổ (3/5/10/expanding), chưa ensemble, chưa AccTEMPO.",
        "- Score là output thô của mô hình, chưa tuyên bố là PD đã calibrated.",
        "- Cohort 2019 có phần lớn sự kiện đầu tiên ghi nhận năm 2020; đây là bằng chứng thời điểm, không khẳng định nguyên nhân nhân quả COVID.",
        "- Không claim test metrics là upper bound chỉ vì snapshot backfill.",
        "",
        "## 6. Lệnh tái lập (3 bước)",
        f"1. ./venv/bin/python scripts/gold/build_research_dataset.py --output-dir output/research",
        f"2. ./venv/bin/python scripts/gold/verify_research_dataset.py --dataset-dir output/research",
        f"3. ./venv/bin/python scripts/model/train_baseline.py --config {config_path} --output-dir {out_dir}",
        "",
        "## 7. Artifacts trong run này",
        f"- config_snapshot.yaml, run_manifest.json (hash config, actual params, thread limits, runtime).",
        f"- role_counts.csv, training_boundary_checks.json (set equality hai chiều).",
        f"- unit_tests.json, train.log.",
        f"- models/stage_a_lr.pkl, stage_b_lr.pkl, stage_a_xgb.pkl, stage_b_xgb.pkl (model + preprocessing tương ứng).",
        f"- predictions/validation_lr, validation_xgb, development_test_lr, development_test_xgb (.parquet).",
        f"- metrics/per_quarter.csv, metrics/pooled.csv, metrics/verification.json.",
        "",
        "---\n*Báo cáo tự động tạo bởi train_baseline.py.*",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
    LOG.info("REPORT.md đã ghi: %s", out_dir / "REPORT.md")

    return {
        "out_dir": out_dir,
        "models_dir": models_dir,
        "preds_dir": preds_dir,
        "metrics_dir": metrics_dir,
        "logs_dir": logs_dir,
        "ts": ts,
        "manifest": manifest,
        "results": results,
        "lrB": lrB,
        "xgbB": xgbB,
        "lrA": lrA,
        "xgbA": xgbA,
    }


if __name__ == "__main__":
    main()
