#!/usr/bin/env python3
"""Independent disk-only checker. Never writes package files or invokes children."""
import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = "provenance/artifact_inventory_handoff_sha256.json"
EXCLUSIONS = [INVENTORY, "completeness_gate.json", "COMPLETE.json"]
REQUIRED = ["REPORT_CORRECTED.md", "CHANGES.md", "audit_manifest.json",
    "metrics/pooled_corrected.csv", "metrics/per_quarter_corrected.csv",
    "metrics/constant_baseline_by_stage.csv", "metrics/model_vs_constant.csv", "metrics/convergence_review.json",
    "verification/verification.json", "verification/recomputed_metrics.json", "verification/sample_inference.json",
    "verification/artifact_inventory_sha256.json", "test_results/convergence_evaluator_tests.json",
    "provenance/input_hashes_before.json", "provenance/input_hashes_after.json",
    "provenance/source_hashes_before.json", "provenance/git_status_before.txt", "provenance/source_hashes.json",
    "provenance/dependency_versions.json", "provenance/commands.json",
    "logs/tests_stdout.txt", "logs/tests_stderr.txt", "logs/verify_stdout.txt", "logs/verify_stderr.txt"]
MODELS = ("logistic_regression", "xgboost")
STAGES = {"stage_A_validation": ("train_tune", "validation"),
          "stage_B_development_test": ("train_refit", "development_test")}


def digest(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def csv_rows(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or any(None in row for row in rows):
        raise ValueError(f"empty/malformed CSV {path}")
    return rows


def close(a, b):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a), float(b), abs_tol=1e-10, rel_tol=1e-8)


def saved_model_metric_matches(a, b):
    # Existing verifier model-metric contract (float32 trainer vs float64 verifier).
    # This tolerance is NOT used for constant baseline losses or population counts.
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b)) <= 1e-6


def verify_only_commands_valid(report, package):
    commands = report.split("## Verify-only commands", 1)[1]
    return ("train_pilot" not in commands and "build_research" not in commands and
            "check_handoff_package.py --package-dir " + str(package) in commands)


def expected_required_ids():
    ids = [f"membership {r} set_equal" for r in ("train_tune", "validation", "train_refit", "development_test")]
    ids += ["train_refit no pre-2012", "development_test not in fitting roles", "holdout not in fitting roles", "membership no duplicate (loan_id,role)"]
    for name in ("validation_lr", "validation_xgb", "development_test_lr", "development_test_xgb"):
        ids += [f"predictions {name} {suffix}" for suffix in (
            "integrity", "n/n_pos vs Gold target", "per-loan_id label == Gold target", "per-loan_id cohort == Gold split",
            "recompute metrics", "matches pooled.csv", "matches per_quarter.csv", "matches per_quarter.csv per-row",
            "matches per_quarter.csv pooled counts")]
        ids.append(f"sample inference {name}")
    ids += [f"LR scaler stage {s} n_samples_seen" for s in ("A", "B")]
    return set(ids)


def check_package(package, require_complete=True):
    """Each failure carries an identifier/path/reason. All evidence comes from disk."""
    package = Path(package).resolve()
    checks = []

    def check(check_id, ok, path="", reason=""):
        checks.append(dict(check_id=check_id, path=str(path), **{"pass": bool(ok)}, reason=reason))

    def phase(check_id, function):
        try:
            function()
        except Exception as exc:
            check(check_id, False, reason=f"{type(exc).__name__}: {exc}")

    def required_files():
        for rel in REQUIRED + [INVENTORY]:
            p = package / rel
            # Empty stderr is valid and still inventoried; substantive evidence may not be empty.
            check("required_nonempty", p.is_file() and (p.stat().st_size > 0 or rel.startswith("logs/")), rel)
    phase("required_files", required_files)

    def integrity():
        inv = read_json(package / INVENTORY)
        check("finite_exclusions", inv["exclusions"] == EXCLUSIONS, INVENTORY)
        files = inv["files"]
        actual = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
        check("inventory_exact_coverage", set(files) == actual - set(EXCLUSIONS), INVENTORY,
              f"missing={sorted(actual-set(EXCLUSIONS)-set(files))}; extra={sorted(set(files)-actual)}")
        check("required_inventory_coverage", set(REQUIRED) <= set(files), INVENTORY)
        for rel, entry in files.items():
            path = package / rel
            safe = path.resolve().is_relative_to(package) and not path.is_symlink()
            check("inventory_hash", safe and path.is_file() and path.stat().st_size == entry["size"] and digest(path) == entry["sha256"], rel)
    phase("integrity", integrity)

    manifest = {}
    def evidence():
        nonlocal manifest
        from collections import Counter
        manifest = read_json(package / "audit_manifest.json")
        check("manifest_identity", Path(manifest["package_dir"]).resolve() == package and bool(manifest["execution_id"]), "audit_manifest.json")
        check("manifest_exclusions", manifest["inventory_exclusions"] == EXCLUSIONS)
        check("manifest_artifacts", set(manifest["artifacts"]) <= set(REQUIRED) and all((package/p).is_file() for p in manifest["artifacts"]))
        verification = read_json(package / "verification/verification.json")
        records = verification["checks"]
        required = expected_required_ids()
        counts = Counter(r["name"] for r in records if r["required"])
        check("verification_registry", set(verification["required_ids"]) == required and set(counts) == required and all(v == 1 for v in counts.values()) and
              not any(verification["registry"].values()) and not verification["required_missing"] and
              verification["overall"] is True and all(r["pass"] is True for r in records), "verification/verification.json")
        tests = read_json(package / "test_results/convergence_evaluator_tests.json")
        test_records = [r for g in tests["groups"].values() for r in g["tests"]]
        passed = sum(r["pass"] is True for r in test_records)
        check("test_counts", bool(test_records) and passed == len(test_records) == tests["total_tests_passed"] and
              tests["total_tests_failed"] == 0 and tests["overall_passed"] is True and
              all(g["passed"] == sum(r["pass"] is True for r in g["tests"]) and g["failed"] == 0 for g in tests["groups"].values()),
              "test_results/convergence_evaluator_tests.json")
        expected_counts = dict(tests_passed=passed, tests_failed=0, verification_checks=len(records), required_checks=len(required))
        check("manifest_counts", manifest["counts"] == expected_counts)
        commands = read_json(package / "provenance/commands.json")
        check("child_order", [c["name"] for c in commands] == ["tests", "verify"])
        previous_end = None
        for command in commands:
            target = package / command["evidence"]
            argv = command["argv"]
            start, end = datetime.fromisoformat(command["start"]), datetime.fromisoformat(command["end"])
            check("child_fresh_execution", command["execution_id"] == manifest["execution_id"] and command["returncode"] == 0 and
                  command["evidence_sha256"] == digest(target) and end >= start and (previous_end is None or start >= previous_end), command["evidence"])
            previous_end = end
            script = "tests_pilot_repair.py" if command["name"] == "tests" else "verify_pilot_run.py"
            expected_argv = [argv[0], str(ROOT/"scripts/model"/script)]
            if command["name"] == "tests":
                expected_argv += ["--config", str(ROOT/"configs/pilot_baseline.yaml"), "--output-dir", str(package/"test_results")]
            else:
                expected_argv += ["--run-dir", manifest["run_dir"], "--gold-dir", manifest["gold_dir"], "--output-dir", str(package/"verification")]
            check("child_argv", argv == expected_argv and all((package/command[k]).is_file() for k in ("stdout", "stderr")))
    phase("evidence_schema", evidence)

    def provenance():
        run = Path(manifest["run_dir"])
        before = read_json(package / "provenance/input_hashes_before.json")
        after = read_json(package / "provenance/input_hashes_after.json")
        check("original_18_unchanged", len(before) == 18 and before == after == read_json(package/"verification/artifact_inventory_sha256.json"))
        for rel, record in before.items():
            path = run / rel
            check("original_input_hash", path.is_file() and digest(path) == record["sha256"] and path.stat().st_size == record["size"], rel)
        sources = read_json(package / "provenance/source_hashes.json")
        expected_sources = {"scripts/model/"+s for s in ("train_pilot_corrected.py", "verify_pilot_run.py", "tests_pilot_repair.py", "generate_handoff_package.py", "check_handoff_package.py", "tests_handoff_package.py")} | {"configs/pilot_baseline.yaml"}
        check("source_coverage", set(sources) == expected_sources)
        for rel, value in sources.items():
            check("source_hash", digest(ROOT/rel) == value, rel)
        dependencies = read_json(package / "provenance/dependency_versions.json")
        check("dependency_schema", all(dependencies.get(k) for k in ("python", "numpy", "pandas", "scikit-learn", "xgboost", "duckdb", "pyarrow")))
        check("before_sources_schema", bool(read_json(package/"provenance/source_hashes_before.json")))
    phase("provenance", provenance)

    def metrics():
        import duckdb
        import numpy as np
        import pandas as pd
        from sklearn.metrics import brier_score_loss, log_loss
        run, gold = Path(manifest["run_dir"]), Path(manifest["gold_dir"])
        pooled = csv_rows(package / "metrics/pooled_corrected.csv")
        baseline = csv_rows(package / "metrics/constant_baseline_by_stage.csv")
        deltas = csv_rows(package / "metrics/model_vs_constant.csv")
        perq = csv_rows(package / "metrics/per_quarter_corrected.csv")
        expected_keys = {(m, s) for m in MODELS for s in STAGES}
        for name, rows in (("pooled", pooled), ("model_vs_constant", deltas)):
            check("csv_keys", len(rows) == 4 and {(r["model"], r["stage"]) for r in rows} == expected_keys, name)
        check("baseline_keys", len(baseline) == 2 and {r["stage"] for r in baseline} == set(STAGES))
        check("quarter_keys", len(perq) == 16 and {(r["model"], r["stage"], r["cohort"]) for r in perq} ==
              {(m, s, str(y)+"Q"+str(q)) for m in MODELS for s, y in zip(STAGES, (2016, 2019)) for q in range(1, 5)})
        original = csv_rows(run / "metrics/pooled.csv")
        check("quarterly_preserved", perq == csv_rows(run / "metrics/per_quarter.csv"))
        recomputed = read_json(package / "verification/recomputed_metrics.json")
        con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
        try:
            for stage, (fit, evaluation) in STAGES.items():
                n_fit, n_pos = con.execute("""SELECT count(*),sum(cast(label_12m as BIGINT)) FROM
                    read_parquet(?) m JOIN read_parquet(?) t USING(loan_id) WHERE role=?""",
                    [str(gold/"membership.parquet"), str(gold/"target.parquet"), fit]).fetchone()
                y = pd.read_parquet(run/"predictions"/f"{evaluation}_lr.parquet", columns=["label_12m"])["label_12m"].to_numpy()
                if not len(y) or not np.isin(y, [0, 1]).all():
                    raise ValueError("invalid evaluation labels")
                p = n_pos/n_fit
                scores = np.full(len(y), p, dtype=np.float64)
                computed = dict(n_fit=n_fit, n_pos_fit=n_pos, p_fit=p, n_eval=len(y), n_pos_eval=int(y.sum()), q_eval=float(y.mean()),
                                brier_constant_rate=float(brier_score_loss(y, scores)), log_loss_constant_rate=float(log_loss(y, scores, labels=[0, 1])))
                e = next(r for r in baseline if r["stage"] == stage)
                me = next(r for r in manifest["baseline_evidence"] if r["stage"] == stage)
                check("baseline_roles", e["fit_role"] == me["fit_role"] == fit and e["evaluation_role"] == me["evaluation_role"] == evaluation)
                for key, value in computed.items():
                    matches = (str(e[key]) == str(value) and me[key] == value) if key in ("n_fit", "n_pos_fit", "n_eval", "n_pos_eval") else (close(e[key], value) and close(me[key], value))
                    check("baseline_saved_label_sklearn", matches, f"{stage}/{key}")
                for r in (r for r in pooled if r["stage"] == stage):
                    model = r["model"]
                    old = next(o for o in original if o["model"] == model and o["stage"] == stage)
                    check("saved_model_metrics_preserved", all(r[k] == v for k, v in old.items() if k not in ("prevalence_used", "brier_constant_rate", "log_loss_constant_rate")))
                    for k in ("brier_constant_rate", "log_loss_constant_rate"):
                        check("pooled_baseline", close(r[k], computed[k]), f"{model}/{stage}/{k}")
                    check("pooled_p_fit", close(r["prevalence_used"], p))
                    qs = [q for q in perq if q["model"] == model and q["stage"] == stage]
                    for column, q_col in (("n", "n"), ("n_pos", "n_pos"), ("total_selected", "k"), ("total_tp", "tp_selected")):
                        check("quarterly_capacity_population", int(r[column]) == sum(int(q[q_col]) for q in qs), f"{model}/{stage}/{column}")
                    check("quarterly_capacity_capture", close(r["capacity_pooled_capture"], int(r["total_tp"])/int(r["n_pos"])))
                    d = next(d for d in deltas if d["model"] == model and d["stage"] == stage)
                    for metric in ("brier", "log_loss"):
                        check("model_vs_constant", close(d[metric+"_model"], r[metric+"_global"]) and
                              close(d[metric+"_constant"], computed[metric+"_constant_rate"]) and
                              close(d[metric+"_delta"], float(r[metric+"_global"])-computed[metric+"_constant_rate"]))
                    name = evaluation + ("_lr" if model == "logistic_regression" else "_xgb")
                    rec = recomputed[name]
                    for k, col in (("n", "n"), ("n_pos", "n_pos"), ("total_selected", "total_selected"), ("total_tp", "total_tp"),
                                   ("average_precision", "average_precision_global"), ("roc_auc", "roc_auc_global"), ("brier", "brier_global"), ("log_loss", "log_loss_global")):
                        match = str(rec[k]) == r[col] if k in ("n", "n_pos", "total_selected", "total_tp") else saved_model_metric_matches(rec[k], r[col])
                        check("recomputed_metrics_consistency", match, f"{name}/{k}",
                              f"recomputed={rec[k]!r}; saved={r[col]}; counts exact, model-metric atol=1e-6 (existing verifier contract)")
        finally:
            con.close()
        sample = read_json(package / "verification/sample_inference.json")
        names = {r+"_"+m for r in ("validation", "development_test") for m in ("lr", "xgb")}
        check("sample_inference_keys", set(sample) == names)
        for name, r in sample.items():
            check("sample_inference", r["sampled"] == r["matched"] == 512 and r["mismatched"] == 0 and r["pass"] is True and
                  r["atol"] == 1e-8 and r["rtol"] == 0 and r["seed"] == 42 and 0 <= r["mean_abs_diff"] <= r["max_abs_diff"] <= r["atol"], name)
            saved = pd.read_parquet(run/"predictions"/(name+".parquet"), columns=["loan_id", "score"])
            expected_sample = saved.sample(n=512, random_state=42)
            actual_saved = expected_sample["score"].to_numpy(dtype=float)
            predicted = np.asarray(r["predicted_probabilities"], dtype=float)
            diffs = np.abs(predicted-actual_saved)
            check("sample_inference_fixed_ids_values", r["loan_ids"] == expected_sample["loan_id"].astype(str).tolist() and
                  np.isfinite(predicted).all() and np.array_equal(np.asarray(r["saved_scores"]), actual_saved) and
                  int((diffs > r["atol"]).sum()) == r["mismatched"] and close(float(diffs.max()), r["max_abs_diff"]) and
                  close(float(diffs.mean()), r["mean_abs_diff"]), name)
        convergence = read_json(package / "metrics/convergence_review.json")
        check("convergence_keys", len(convergence["models"]) == 2 and {r["stage"] for r in convergence["models"]} == {"A", "B"})
        import pickle
        for r in convergence["models"]:
            path = run/"models"/f"stage_{r['stage'].lower()}_lr.pkl"
            with path.open("rb") as f:
                model = pickle.load(f)["model"]
            check("historical_convergence", r["status"] == "unknown" and r["historical_warning_capture"] is None and bool(r["limitation"]) and
                  r["n_iter"] == int(np.max(model.n_iter_)) < r["max_iter"] == model.max_iter and r["solver"] == model.solver and
                  r["finite_coefficients"] == bool(np.isfinite(model.coef_).all() and np.isfinite(model.intercept_).all()) and r["model_sha256"] == digest(path))
        for rel, h in convergence["historical_log_hashes"].items():
            check("historical_log_hash", digest(run/rel) == h, rel)
        report = (package/"REPORT_CORRECTED.md").read_text()
        check("report_computed_baseline", json.dumps(manifest["baseline_evidence"], indent=2) in report)
        check("report_computed_deltas", json.dumps([{k: (v if k in ("model", "stage") else float(v)) for k,v in r.items()} for r in deltas], indent=2) in report)
        check("report_convergence", json.dumps(convergence, indent=2) in report)
        check("report_counts", json.dumps(manifest["counts"], sort_keys=True) in report)
        check("report_metric_scope", "Main development_test: quarterly-capacity" in report and "Separate global-ranking" in report)
        for r in pooled:
            check("report_global_values", "|" + "|".join(str(r[k]) for k in ("model", "stage", "average_precision_global", "roc_auc_global", "brier_global", "log_loss_global", "capture_at_k_global", "precision_at_k_global", "lift_at_k_global")) + "|" in report)
            if r["stage"] == "stage_B_development_test":
                selected, tp, pos, n = [int(r[k]) for k in ("total_selected", "total_tp", "n_pos", "n")]
                check("report_quarterly_values", f"|{r['model']}|{selected}|{tp}|{tp/pos!r}|{tp/selected!r}|{(tp/selected)/(pos/n)!r}|" in report)
        check("report_verify_only", verify_only_commands_valid(report, package))
    phase("metrics_semantics", metrics)

    if require_complete:
        def completion():
            marker = read_json(package/"COMPLETE.json")
            gate = read_json(package/"completeness_gate.json")
            check("completion_marker", marker["status"] == "COMPLETE" and marker["execution_id"] == manifest["execution_id"] and
                  marker["inventory_sha256"] == digest(package/INVENTORY) and marker["gate_sha256"] == digest(package/"completeness_gate.json") and
                  gate["all_ok"] is True and bool(gate["checks"]) and all(r["pass"] is True for r in gate["checks"]))
        phase("completion", completion)
    return dict(all_ok=bool(checks) and all(c["pass"] for c in checks), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    args = parser.parse_args()
    result = check_package(args.package_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
