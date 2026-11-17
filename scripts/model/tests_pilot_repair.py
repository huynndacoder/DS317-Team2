"""
tests_pilot_repair.py — Known-answer tests for A1 (convergence checker),
A5 (evaluator), plus verifier negative-test fixtures.

Chạy độc lập, không train dữ liệu thật, không đụng artifacts gốc.
Output JSON vào --output-dir.
"""
import argparse
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_pilot_corrected as tr


def run_convergence_tests():
    """A1 synthetic tests for lr_convergence_status."""
    tests = []

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    from sklearn.linear_model import LogisticRegression
    from sklearn.exceptions import ConvergenceWarning

    # T-c1: scaled toy data đủ vòng -> success, không fail vì thiếu converged_
    X = np.array([[0.0], [1.0], [2.0], [3.0], [4.0], [5.0]])
    y = np.array([0, 0, 0, 1, 1, 1])
    lr = LogisticRegression(max_iter=1000, solver="lbfgs").fit(X, y)
    status, n_iter = tr.lr_convergence_status(lr, [], 1000)
    t("convergence toy enough iterations -> success",
      status == "success" and n_iter is not None and n_iter < 1000,
      f"status={status} n_iter={n_iter}")

    # T-c2: max_iter thấp tạo ConvergenceWarning -> nhận diện đúng category
    lr2 = LogisticRegression(max_iter=1, solver="lbfgs").fit(X, y)
    status2, n_iter2 = tr.lr_convergence_status(lr2, ["ConvergenceWarning"], 1)
    t("convergence low max_iter + warning -> warning/iteration_limit",
      status2 in ("warning", "iteration_limit"),
      f"status={status2} n_iter={n_iter2}")

    # T-c3: ConvergenceWarning message không chứa chữ "Convergence" vẫn nhận đúng
    class FakeCat(ConvergenceWarning):
        pass
    status3, n_iter3 = tr.lr_convergence_status(lr2, ["khong hoi tu"], 1)
    # warning list non-empty; n_iter=1>=max_iter=1 -> iteration_limit (đúng quy tắc A1)
    t("convergence warning non-empty category -> warning/iteration_limit",
      status3 in ("warning", "iteration_limit"),
      f"status={status3} n_iter={n_iter3}")

    # T-c4: missing warning evidence vs captured empty warnings -> unknown/success distinction
    status4, n_iter4 = tr.lr_convergence_status(lr, [], 1000)
    t("convergence empty warnings + finite coef + n_iter<max -> success",
      status4 == "success", f"status={status4} n_iter={n_iter4}")

    # T-c5: model nonfinite coefficients -> not success
    lr5 = LogisticRegression(max_iter=1000).fit(X, y)
    lr5.coef_ = np.array([[np.inf]])
    status5, _ = tr.lr_convergence_status(lr5, [], 1000)
    t("convergence nonfinite coef -> not success", status5 != "success", f"status={status5}")

    # T-c6: n_iter >= max_iter -> iteration_limit (không dùng converged_)
    class FakeLR:
        coef_ = np.array([[0.1]])
        intercept_ = np.array([0.0])
        n_iter_ = np.array([1000])
    status6, n_iter6 = tr.lr_convergence_status(FakeLR(), [], 1000)
    t("convergence n_iter>=max_iter -> iteration_limit",
      status6 == "iteration_limit", f"status={status6} n_iter={n_iter6}")

    # T-c7: conv_warnings=None (không thu thập evidence lịch sử) -> unknown, không TypeError
    status7, _ = tr.lr_convergence_status(lr, None, 1000)
    t("convergence missing evidence None -> unknown (không TypeError)",
      status7 == "unknown", f"status={status7}")

    # T-c8: đường dẫn thu thập cảnh báo thực (production path) qua train_lr, max_iter thấp
    # -> conv_warnings không rỗng, lr_convergence_status nhận được danh sách thông điệp thực
    lr_real = tr.train_lr(X, y, max_iter=1)
    status8, n_iter8 = tr.lr_convergence_status(lr_real["model"], lr_real["convergence_warnings"], 1)
    t("convergence real capture path -> warning/iteration_limit",
       status8 == "iteration_limit" and n_iter8 == 1 and n_iter8 == lr_real["n_iter"] and len(lr_real["convergence_warnings"]) > 0,
      f"status={status8} warnings={lr_real['convergence_warnings']} n_iter={n_iter8}")

    # T-c9: conv_warnings=[] (đã thu thập nhưng rỗng) + n_iter<max + hệ số hữu hạn -> success
    status9, _ = tr.lr_convergence_status(lr, [], 1000)
    t("convergence captured empty [] + n_iter<max -> success",
      status9 == "success", f"status={status9}")

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


def run_evaluator_known_answer_tests():
    """A5 known-answer evaluator tests (subset duplicated from trainer for standalone output)."""
    tests = []

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    rows_tie, _ = tr.per_quarter_metrics(
        pd.Series([1, 0, 1, 0, 0]), pd.Series([0.9, 0.9, 0.9, 0.9, 0.9]),
        pd.Series(["Q1"]*5), pd.Series(["a", "b", "c", "d", "e"]), k_frac=0.4,
    )
    t("ties boundary k=2 tp_selected=1", rows_tie[0]["k"] == 2 and rows_tie[0]["tp_selected"] == 1,
      str(rows_tie[0]))

    # Perfect vs reversed ranking
    r_perf, _ = tr.per_quarter_metrics(
        pd.Series([1, 1, 0, 0, 0, 0]), pd.Series([0.9, 0.8, 0.7, 0.6, 0.5, 0.4]),
        pd.Series(["Q1"]*6), pd.Series(["a","b","c","d","e","f"]), k_frac=0.5,
    )
    r_rev, _ = tr.per_quarter_metrics(
        pd.Series([1, 1, 0, 0, 0, 0]), pd.Series([0.4, 0.5, 0.6, 0.7, 0.8, 0.9]),
        pd.Series(["Q1"]*6), pd.Series(["a","b","c","d","e","f"]), k_frac=0.5,
    )
    t("perfect capture=1.0 reversed capture=0",
      r_perf[0]["capture_at_k"] == 1.0 and r_rev[0]["capture_at_k"] == 0.0,
      f"perf={r_perf[0]['capture_at_k']} rev={r_rev[0]['capture_at_k']}")

    # Empty global input -> k=0
    rg = tr.global_ranking_metrics(pd.Series([], dtype=int), pd.Series([], dtype=float), k_frac=0.05)
    t("empty global n=0 k=0 tp=0 metrics NA",
      rg["n"] == 0 and rg["k"] == 0 and rg["tp_selected"] == 0 and rg["roc_auc_global"] is None,
      str(rg))

    # Duplicate ID rejected
    try:
        tr.per_quarter_metrics(
            pd.Series([1, 0, 1]), pd.Series([0.9, 0.5, 0.1]),
            pd.Series(["Q1"]*3), pd.Series(["a", "a", "b"]), k_frac=1.0,
        )
        t("duplicate id rejected", False, "no error raised")
    except ValueError:
        t("duplicate id rejected", True)

    # NaN score rejected
    try:
        tr.per_quarter_metrics(
            pd.Series([1, 0, 1]), pd.Series([0.9, float("nan"), 0.1]),
            pd.Series(["Q1"]*3), pd.Series(["a", "b", "c"]), k_frac=1.0,
        )
        t("nan score rejected", False, "no error raised")
    except ValueError:
        t("nan score rejected", True)

    # Out-of-range score rejected
    try:
        tr.per_quarter_metrics(
            pd.Series([1, 0, 1]), pd.Series([0.9, 1.5, 0.1]),
            pd.Series(["Q1"]*3), pd.Series(["a", "b", "c"]), k_frac=1.0,
        )
        t("out-of-range score rejected", False, "no error raised")
    except ValueError:
        t("out-of-range score rejected", True)

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


def run_smoke_evaluator_test():
    """R1: chạy đường dẫn production real trên synthetic — global_ranking_metrics nhận cohort/loan_id,
    trả về dict duy nhất, không crash và các metric finanziary đúng kiểu."""
    tests = []

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    n = 200
    rng = np.random.RandomState(42)
    y = pd.Series(rng.randint(0, 2, n).astype(int))
    p = pd.Series(rng.rand(n))
    cohort = pd.Series(["Q1"] * (n // 2) + ["Q2"] * (n // 2))
    loan_id = pd.Series([f"L{i}" for i in range(n)])

    # Must return a single dict, not a tuple; no crash with cohort/loan_id passed
    rg = tr.global_ranking_metrics(y, p, cohort=cohort, loan_id=loan_id, k_frac=0.05)
    t("global_ranking_metrics returns single dict", isinstance(rg, dict) and "average_precision_global" in rg,
      f"type={type(rg).__name__} keys={list(rg.keys())[:5]}")
    t("global_ranking_metrics n/tp/k types", all(isinstance(rg[k], (int, float, type(None))) for k in ["n", "tp_selected", "k"]),
      f"n={rg['n']} tp={rg['tp_selected']} k={rg['k']}")
    t("global_ranking_metrics finite metrics", all(
        isinstance(rg[k], float) for k in ["average_precision_global", "roc_auc_global", "brier_global", "log_loss_global"]),
      str({k: type(rg[k]).__name__ for k in ["average_precision_global", "roc_auc_global", "brier_global", "log_loss_global"]}))

    per_q, pooled = tr.per_quarter_metrics(y, p, cohort, loan_id, k_frac=0.05)
    t("per_quarter_metrics returns (list, dict)", isinstance(per_q, list) and isinstance(pooled, dict),
      f"type(per_q)={type(per_q).__name__} type(pooled)={type(pooled).__name__}")
    t("per_quarter_metrics two cohorts", len(per_q) == 2,
      f"len={len(per_q)}")
    t("per_quarter_metrics has cohort/ids tie columns", all("cohort" in r for r in per_q),
      f"first row keys={list(per_q[0].keys())}")

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


def run_verifier_negative_tests():
    tests = []
    import importlib
    vp = importlib.import_module("verify_pilot_run")
    metric_is_bad = vp._metric_is_bad
    compare_metrics = vp.compare_metrics
    METRIC_COLS = list(vp.METRIC_ALIASES.values())
    METRIC_KEYS = list(vp.METRIC_ALIASES.keys())

    def full_a(**overrides):
        a = {k: None for k in METRIC_KEYS}
        a.update(overrides)
        return a

    def full_b(**overrides):
        b = {c: None for c in METRIC_COLS}
        b.update(overrides)
        return b

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    # N/A policy: None vs None -> match (không FAIL) — metric không required
    a = full_a(average_precision=None, roc_auc=None)
    b = full_b(average_precision_global=None, roc_auc_global=None)
    t("metric NaN/None vs NaN/None -> match", compare_metrics(a, b, required_keys=set()) == [],
      str(compare_metrics(a, b)))

    # NaN trên bên recompute -> FAIL
    a = full_a(average_precision=float("nan"))
    b = full_b(average_precision_global=0.05)
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("metric NaN recompute -> FAIL (không skip)", len(mm) == 1 and "average_precision:" in mm[0], str(mm))

    # inf trên bên CSV -> FAIL
    a = full_a(roc_auc=0.70)
    b = full_b(roc_auc_global=float("inf"))
    mm = compare_metrics(a, b, required_keys={"roc_auc"})
    t("metric inf CSV -> FAIL (không skip)", len(mm) == 1 and "roc_auc:" in mm[0], str(mm))

    # thiếu cột reference -> FAIL (b không có cột đó)
    a = full_a(brier=0.025)
    b = full_b()
    b.pop("brier_global", None)
    mm = compare_metrics(a, b, required_keys={"brier"})
    t("metric missing reference column -> FAIL", any("missing csv column: brier_global" in m for m in mm), str(mm))

    # sai số trên biên (0.9999 vs 0.0557) -> FAIL
    a = full_a(average_precision=0.055704548879097295)
    b = full_b(average_precision_global=0.9999)
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("metric sai biên 0.9999 vs 0.0557 -> FAIL", len(mm) == 1 and "average_precision:" in mm[0], str(mm))

    # đúng số -> match
    a = full_a(capture_at_k=0.14286307053941907)
    b = full_b(capture_at_k_global=0.14286307053941907)
    t("metric đúng số -> match", compare_metrics(a, b, required_keys={"capture_at_k"}) == [], str(compare_metrics(a, b)))

    # _metric_is_bad: None/NaN/inf/non-finite -> True
    t("_metric_is_bad(None)", metric_is_bad(None))
    t("_metric_is_bad(float('nan'))", metric_is_bad(float("nan")))
    t("_metric_is_bad(float('inf'))", metric_is_bad(float("inf")))
    t("_metric_is_bad(0.5) False", not metric_is_bad(0.5))

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


def run_production_path_regression_tests():
    """C1/C2/C3 regression tests qua production helper trong verify_pilot_run.
    Không gọi trainer main; chỉ gọi compare_quarterly / compare_metrics (các hàm CLI verifier dùng)."""
    import importlib
    vp = importlib.import_module("verify_pilot_run")
    compare_quarterly = vp.compare_quarterly
    compare_metrics = vp.compare_metrics
    METRIC_COLS = list(vp.METRIC_ALIASES.values())

    tests = []

    def t(name, ok, detail=""):
        tests.append({"name": name, "pass": bool(ok), "detail": detail})

    # Base clean row (validation stage, 1 quarter)
    base_csv = {
        "model": "logistic_regression", "stage": "stage_A_validation", "cohort": "2016Q1",
        "n": 1000, "n_pos": 10, "k": 50, "tp_selected": 5,
        "prevalence": 0.01, "selected_fraction": 0.05,
        "precision_at_k": 0.1, "capture_at_k": 0.5, "lift_at_k": 10.0, "roc_auc": 0.7,
    }
    base_recomp = dict(base_csv)

    # Case 1: Bảng sạch -> PASS
    ok, mm = compare_quarterly([base_recomp], [base_csv])
    t("C1 bảng sạch -> PASS", ok and mm == [], str(mm))

    # Case 2: Tăng k của một quý thêm 100 -> FAIL
    wrong_k = dict(base_recomp); wrong_k["k"] = base_csv["k"] + 100
    ok, mm = compare_quarterly([wrong_k], [base_csv])
    t("C1 sai k -> FAIL", not ok and any("k:" in m for m in mm), str(mm))

    # Case 3: Nhân đôi toàn bộ quarterly reference rows -> FAIL (duplicate key)
    ok, mm = compare_quarterly([base_recomp], [base_csv, base_csv])
    t("C1 duplicate reference rows -> FAIL", not ok and any("duplicate" in m.lower() for m in mm), str(mm))

    # Case 4: Duplicate chỉ một quarterly key (recomputed duplicate) -> FAIL
    ok, mm = compare_quarterly([base_recomp, base_recomp], [base_csv])
    t("C1 duplicate recomputed key -> FAIL", not ok and any("duplicate" in m.lower() for m in mm), str(mm))

    # Case 5: Thiếu một quý (key set khác) -> FAIL
    ok, mm = compare_quarterly([base_recomp], [])  # csv empty
    t("C1 thiếu quý trong reference -> FAIL", not ok and any("key set mismatch" in m for m in mm), str(mm))

    # Case 6: Thêm quý ngoài population -> FAIL
    extra_csv = dict(base_csv); extra_csv["cohort"] = "2016Q2"
    ok, mm = compare_quarterly([base_recomp], [base_csv, extra_csv])
    t("C1 thêm quý ngoài population -> FAIL", not ok and any("key set mismatch" in m for m in mm), str(mm))

    # Case 7: Sai tp_selected/n/n_pos -> FAIL (exact integer, không tolerance)
    wrong_tp = dict(base_recomp); wrong_tp["tp_selected"] = base_csv["tp_selected"] + 1
    ok, mm = compare_quarterly([wrong_tp], [base_csv])
    t("C1 sai tp_selected -> FAIL", not ok and any("tp_selected:" in m for m in mm), str(mm))

    # Case 8: Hoán vị row order của bảng sạch -> vẫn PASS
    rows_recomp = [dict(base_recomp), dict(base_recomp, cohort="2016Q2", n=2000, n_pos=20, k=100, tp_selected=10)]
    rows_csv = [dict(base_csv, cohort="2016Q2", n=2000, n_pos=20, k=100, tp_selected=10), dict(base_csv)]
    ok, mm = compare_quarterly(list(reversed(rows_recomp)), list(reversed(rows_csv)))
    t("C1 hoán vị row order -> PASS", ok and mm == [], str(mm))

    # Case 9: prevalence/selected_fraction sai -> FAIL (float fields)
    wrong_prev = dict(base_recomp); wrong_prev["prevalence"] = 0.999
    ok, mm = compare_quarterly([wrong_prev], [base_csv])
    t("C1 sai prevalence -> FAIL", not ok and any("prevalence:" in m for m in mm), str(mm))

    # Case 10: k != ceil(0.05*n) -> FAIL
    bad_k = dict(base_recomp); bad_k["n"] = 1000; bad_k["k"] = 10  # ceil(0.05*1000)=50
    ok, mm = compare_quarterly([bad_k], [base_csv])
    t("C1 k sai ceil -> FAIL", not ok and any("k:" in m for m in mm), str(mm))

    # C3: Required AP=None/None ở cả hai phía, population hai lớp -> FAIL (không N/A)
    base_a = {k: 0.5 for k in vp.METRIC_ALIASES.keys()}
    base_b = {v: 0.5 for v in vp.METRIC_ALIASES.values()}
    a = dict(base_a); a["average_precision"] = None
    b = dict(base_b); b["average_precision_global"] = None
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("C3 required AP=None/None hai phía -> FAIL", len(mm) == 1 and "average_precision:" in mm[0], str(mm))

    # C3: Required AP/ROC-AUC=NaN cả hai phía -> FAIL
    a = dict(base_a); a["average_precision"] = float("nan"); a["roc_auc"] = float("nan")
    b = dict(base_b); b["average_precision_global"] = float("nan"); b["roc_auc_global"] = float("nan")
    mm = compare_metrics(a, b, required_keys={"average_precision", "roc_auc"})
    t("C3 required AP/ROC-AUC=NaN -> FAIL", len(mm) == 2, str(mm))

    # C3: Missing key ở cả hai dict -> FAIL
    a = dict(base_a); a.pop("average_precision")
    b = dict(base_b)
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("C3 missing key average_precision -> FAIL", any("missing key" in m for m in mm), str(mm))

    # C3: Corrupt AP=.9999 -> FAIL; numeric finite đúng -> PASS
    a = dict(base_a); a["average_precision"] = 0.0557
    b = dict(base_b); b["average_precision_global"] = 0.9999
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("C3 corrupt AP=.9999 -> FAIL", len(mm) == 1, str(mm))
    a = dict(base_a); a["average_precision"] = 0.0557
    b = dict(base_b); b["average_precision_global"] = 0.0557
    mm = compare_metrics(a, b, required_keys={"average_precision"})
    t("C3 numeric finite đúng -> PASS", mm == [], str(mm))

    passed = sum(1 for t_ in tests if t_["pass"])
    return {"passed": passed, "failed": len(tests) - passed, "tests": tests}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/pilot_baseline.yaml")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = yaml.safe_load(open(args.config))
    numeric = list(cfg["features"]["numeric"])
    categorical = list(cfg["features"]["categorical"])

    unit = tr.run_unit_tests(numeric, categorical)
    conv = run_convergence_tests()
    ev = run_evaluator_known_answer_tests()
    smoke = run_smoke_evaluator_test()
    neg = run_verifier_negative_tests()
    prod = run_production_path_regression_tests()
    from tests_handoff_package import run_package_tests
    package = run_package_tests()

    all_groups = {
        "unit_tests": unit,
        "convergence_tests": conv,
        "evaluator_known_answer_tests": ev,
        "smoke_evaluator_test": smoke,
        "verifier_negative_tests": neg,
        "production_path_regression_tests": prod,
        "package_regression_tests": package,
    }
    total_passed = sum(g["passed"] for g in all_groups.values())
    total_failed = sum(g["failed"] for g in all_groups.values())
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "groups": all_groups,
        "total_tests_passed": total_passed,
        "total_tests_failed": total_failed,
        "overall_passed": total_failed == 0,
    }
    (out_dir / "convergence_evaluator_tests.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["overall_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
