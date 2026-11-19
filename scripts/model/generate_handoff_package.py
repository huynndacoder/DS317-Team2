#!/usr/bin/env python3
"""Read-only pilot inputs -> fresh, fail-closed H1-H5 audit package. Never fits models."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGES = {"stage_A_validation": ("train_tune", "validation"),
          "stage_B_development_test": ("train_refit", "development_test")}
SOURCES = ["scripts/model/" + x for x in (
    "train_baseline.py", "verify_baseline.py", "tests_baseline.py",
    "generate_handoff_package.py", "check_handoff_package.py", "tests_handoff_package.py")]
SOURCES += ["configs/baseline.yaml"]
INVENTORY = "provenance/artifact_inventory_handoff_sha256.json"
EXCLUSIONS = [INVENTORY, "completeness_gate.json", "COMPLETE.json"]


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def portable_path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False, default=str) + "\n")


def load_json(path):
    return json.loads(Path(path).read_text())


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def inventory(directory):
    return {str(p.relative_to(directory)): {"sha256": sha256_file(p), "size": p.stat().st_size}
            for p in sorted(Path(directory).rglob("*")) if p.is_file()}


def constant_evidence(n_fit, n_pos_fit, labels):
    import numpy as np
    y = np.asarray(labels)
    if y.ndim != 1 or not y.size or not np.isin(y, [0, 1]).all():
        raise ValueError("evaluation labels must be nonempty, finite binary vector")
    if n_fit <= 0 or not 0 <= n_pos_fit <= n_fit:
        raise ValueError("invalid fit counts")
    p = n_pos_fit / n_fit
    q = float(y.mean())
    # Brier uses raw probability; log loss uses sklearn float64 epsilon clipping.
    eps = np.finfo(np.float64).eps
    clipped = min(max(p, eps), 1 - eps)
    return dict(n_fit=int(n_fit), n_pos_fit=int(n_pos_fit), p_fit=p,
                n_eval=int(y.size), n_pos_eval=int(y.sum()), q_eval=q,
                brier_constant_rate=q * (1-p)**2 + (1-q)*p*p,
                log_loss_constant_rate=-q*math.log(clipped)-(1-q)*math.log1p(-clipped))


def baseline_evidence(run_dir, gold_dir):
    import duckdb
    import pandas as pd
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    evidence = []
    try:
        for stage, (fit, evaluation) in STAGES.items():
            n, pos = con.execute("""SELECT count(*), sum(cast(t.label_12m as BIGINT))
                FROM read_parquet(?) m JOIN read_parquet(?) t USING(loan_id)
                WHERE m.role=?""", [str(gold_dir / "membership.parquet"),
                                     str(gold_dir / "target.parquet"), fit]).fetchone()
            paths = [run_dir / "predictions" / f"{evaluation}_{m}.parquet" for m in ("lr", "xgb")]
            mismatch = con.execute("""SELECT count(*) FROM (
                (SELECT loan_id,label_12m FROM read_parquet(?) EXCEPT ALL
                 SELECT loan_id,label_12m FROM read_parquet(?)) UNION ALL
                (SELECT loan_id,label_12m FROM read_parquet(?) EXCEPT ALL
                 SELECT loan_id,label_12m FROM read_parquet(?)))""",
                list(map(str, [paths[0], paths[1], paths[1], paths[0]]))).fetchone()[0]
            if mismatch:
                raise ValueError(f"{evaluation}: LR/XGB ID/label populations differ")
            y = pd.read_parquet(paths[0], columns=["label_12m"])["label_12m"].to_numpy()
            evidence.append(dict(stage=stage, fit_role=fit, evaluation_role=evaluation,
                                 **constant_evidence(n, pos, y)))
    finally:
        con.close()
    return evidence


def fresh_output(path):
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"refuse nonempty output: {path}")
    path.mkdir(parents=True, exist_ok=True)


def validate_child_evidence(name, data):
    if name == "tests":
        records = [r for g in data["groups"].values() for r in g["tests"]]
        passed = sum(r["pass"] is True for r in records)
        if not records or not data["overall_passed"] or passed != len(records):
            raise ValueError("tests records failed/empty")
        if data["total_tests_passed"] != passed or data["total_tests_failed"] != 0:
            raise ValueError("test counts inconsistent")
    else:
        from verify_baseline import registry_summary
        records = data["checks"]
        summary = registry_summary(records, data["required_ids"])
        if (not records or not data["required_ids"] or not data["overall"] or
                data["required_missing"] or not all(c["pass"] is True for c in records) or
                any(summary.values()) or summary != data["registry"]):
            raise ValueError("verification records/registry failed")


def run_children(out, run, gold, execution_id, runner=subprocess.run):
    """Tests first. Fresh per-child directories + hashed outputs bind evidence to this execution."""
    commands = []
    for name, relative, argv in [
        ("tests", "test_results/convergence_evaluator_tests.json",
         [sys.executable, str(ROOT / "scripts/model/tests_baseline.py"),
          "--config", str(ROOT / "configs/baseline.yaml"), "--output-dir", str(out / "test_results")]),
        ("verify", "verification/verification.json",
         [sys.executable, str(ROOT / "scripts/model/verify_baseline.py"),
          "--run-dir", str(run), "--gold-dir", str(gold), "--output-dir", str(out / "verification")]),
    ]:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=False)
        (out / "logs").mkdir(exist_ok=True)
        start = now_utc()
        print(f"{name}: started {start}", flush=True)
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        result = runner(argv, cwd=ROOT, capture_output=True, text=True, env=env)
        record = dict(name=name, argv=argv, execution_id=execution_id, start=start,
                      end=now_utc(), returncode=result.returncode,
                      stdout=f"logs/{name}_stdout.txt", stderr=f"logs/{name}_stderr.txt", evidence=relative)
        for field in ("stdout", "stderr"):
            (out / record[field]).write_text(getattr(result, field) or "")
        commands.append(record)
        write_json(out / "provenance/commands.json", commands)
        print(f"{name}: exit={result.returncode}, {start} -> {record['end']}", flush=True)
        if result.returncode != 0:
            raise ValueError(f"{name} child exit {result.returncode}")
        data = load_json(target)
        validate_child_evidence(name, data)
        record["evidence_sha256"] = sha256_file(target)
        write_json(out / "provenance/commands.json", commands)
    return commands


def convergence_review(run):
    import numpy as np
    rows = []
    logs = {str(p.relative_to(run)): sha256_file(p) for p in (run / "logs").rglob("*") if p.is_file()}
    for stage in ("a", "b"):
        path = run / "models" / f"stage_{stage}_lr.pkl"
        with path.open("rb") as f:
            model = pickle.load(f)["model"]
        rows.append(dict(stage=stage.upper(), solver=model.solver, max_iter=int(model.max_iter),
                         n_iter=int(np.asarray(model.n_iter_).max()),
                         finite_coefficients=bool(np.isfinite(model.coef_).all() and np.isfinite(model.intercept_).all()),
                         status="unknown", historical_warning_capture=None,
                         limitation="Historical logs do not establish reliable complete warning capture; no refit performed.",
                         model_sha256=sha256_file(path)))
    return dict(models=rows, historical_log_hashes=logs,
                log_evidence={str(p.relative_to(run)): [line for line in p.read_text(errors="replace").splitlines()
                             if "LR stage" in line or "converg" in line.lower() or "warning" in line.lower()]
                              for p in (run / "logs").rglob("*") if p.is_file()})


def emit_metrics(out, run, evidence):
    by_stage = {r["stage"]: r for r in evidence}
    pooled = load_csv(run / "metrics/pooled.csv")
    deltas = []
    for row in pooled:
        e = by_stage[row["stage"]]
        for k in ("brier_constant_rate", "log_loss_constant_rate"):
            row[k] = e[k]
        row["prevalence_used"] = e["p_fit"]
        deltas.append(dict(model=row["model"], stage=row["stage"],
                           brier_model=float(row["brier_global"]), brier_constant=e["brier_constant_rate"],
                           brier_delta=float(row["brier_global"])-e["brier_constant_rate"],
                           log_loss_model=float(row["log_loss_global"]), log_loss_constant=e["log_loss_constant_rate"],
                           log_loss_delta=float(row["log_loss_global"])-e["log_loss_constant_rate"]))
    write_csv(out / "metrics/pooled.csv", pooled)
    write_csv(out / "metrics/constant_baseline_by_stage.csv", evidence)
    write_csv(out / "metrics/model_vs_constant.csv", deltas)
    write_csv(out / "metrics/per_quarter.csv", load_csv(run / "metrics/per_quarter.csv"))
    return pooled, deltas


def emit_report(out, manifest, pooled, deltas, convergence):
    lines = ["# Baseline pilot — verified results", "", f"Execution: {manifest['execution_id']}",
             "Read-only saved pilot evaluation; no retrain/rebuild/holdout evaluation.",
             "", "## Main development_test: quarterly-capacity (5% per cohort)",
             "|model|selected|TP|capture|precision|lift|", "|---|---:|---:|---:|---:|---:|"]
    for r in pooled:
        if r["stage"] != "stage_B_development_test":
            continue
        selected, tp, pos, n = [int(r[k]) for k in ("total_selected", "total_tp", "n_pos", "n")]
        lines.append(f"|{r['model']}|{selected}|{tp}|{tp/pos!r}|{tp/selected!r}|{(tp/selected)/(pos/n)!r}|")
    lines += ["", "## Separate global-ranking metrics", "|model|stage|AP|AUC|Brier|log-loss|global capture|global precision|global lift|",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in pooled:
        lines.append("|" + "|".join(str(r[k]) for k in ("model", "stage", "average_precision_global", "roc_auc_global", "brier_global", "log_loss_global", "capture_at_k_global", "precision_at_k_global", "lift_at_k_global")) + "|")
    lines += ["", "## Computed constant baseline (fit membership JOIN target; losses on saved eval labels)",
              "```json", json.dumps(manifest["baseline_evidence"], indent=2), "```",
              "", "## Model minus constant loss deltas (no significance claim)", "```json", json.dumps(deltas, indent=2), "```",
              "", "## Historical LR convergence", "```json", json.dumps(convergence, indent=2), "```",
              "n_iter below max_iter is not evidence of reaching the iteration limit.",
              "", "## Evidence-derived counts", json.dumps(manifest["counts"], sort_keys=True),
              "", "Final integrity outcome is in completeness_gate.json; this report is frozen before that gate.",
              "", "## Verify-only commands", "Generator already orchestrated synthetic tests then one full saved-artifact verifier.",
              "Do not repeat the full verifier merely to check the package.", "```bash",
              f"{sys.executable} scripts/model/check_handoff_package.py --package-dir {portable_path(out)}",
              "```", "Exact executed child argv/exit codes: provenance/commands.json.",
              "Re-generation requires a NEW empty directory; no resume/force mode."]
    (out / "REPORT.md").write_text("\n".join(lines)+"\n")


def generate(run, gold, out, before_dir, runner=subprocess.run):
    fresh_output(out)
    execution_id = str(uuid.uuid4())
    (out / "provenance").mkdir()
    before = inventory(run)
    if len(before) != 18:
        raise ValueError(f"expected original 18 artifacts, got {len(before)}")
    write_json(out / "provenance/input_hashes_before.json", before)
    if before_dir:
        for name in ("source_hashes_before.json", "git_status_before.txt", "dependency_versions.json"):
            shutil.copyfile(before_dir / name, out / "provenance" / name)
        if load_json(before_dir / "input_hashes_before.json") != before:
            raise ValueError("pre-edit inputs changed")
    commands = run_children(out, run, gold, execution_id, runner)
    evidence = baseline_evidence(run, gold)
    pooled, deltas = emit_metrics(out, run, evidence)
    convergence = convergence_review(run)
    write_json(out / "metrics/convergence_review.json", convergence)
    write_json(out / "provenance/source_hashes.json", {s: sha256_file(ROOT/s) for s in SOURCES})
    write_json(out / "provenance/dependency_versions.json", dict(python=sys.version,
        **{m: importlib.metadata.version(m) for m in ("numpy", "pandas", "scikit-learn", "xgboost", "duckdb", "pyarrow")}))
    after = inventory(run)
    write_json(out / "provenance/input_hashes_after.json", after)
    if before != after:
        raise ValueError("original artifacts changed")
    tests = load_json(out / "test_results/convergence_evaluator_tests.json")
    verification = load_json(out / "verification/verification.json")
    counts = dict(tests_passed=tests["total_tests_passed"], tests_failed=tests["total_tests_failed"],
                  verification_checks=len(verification["checks"]), required_checks=len(verification["required_ids"]))
    manifest = dict(execution_id=execution_id, generated_at=now_utc(), status="FINALIZED_FOR_GATE",
                    generator_argv=sys.argv,
                    execution_root=str(ROOT), run_dir=portable_path(run), gold_dir=portable_path(gold),
                    package_dir=portable_path(out), baseline_evidence=evidence,
                    counts=counts, inventory_exclusions=EXCLUSIONS,
                    artifacts=["REPORT.md", "CHANGES.md", "metrics/pooled.csv",
                     "metrics/per_quarter.csv", "metrics/constant_baseline_by_stage.csv", "metrics/model_vs_constant.csv",
                     "metrics/convergence_review.json", "verification/verification.json", "verification/recomputed_metrics.json",
                     "verification/sample_inference.json", "test_results/convergence_evaluator_tests.json",
                     "provenance/input_hashes_before.json", "provenance/input_hashes_after.json", "provenance/source_hashes.json",
                     "provenance/dependency_versions.json", "provenance/commands.json"])
    write_json(out / "audit_manifest.json", manifest)
    emit_report(out, manifest, pooled, deltas, convergence)
    (out / "CHANGES.md").write_text("""# H1–H5 correction mapping
- H1: generate_handoff_package.constant_evidence/baseline_evidence/emit_metrics; tests_handoff_package baseline sklearn fixtures; metrics + manifest contain computed counts/losses.
- H2: fresh_output/run_children/validate_child_evidence; mocked production runner failure/stale/missing/malformed tests; provenance/commands.json and closed logs.
- H4: substantive bytes frozen before inventory; independent check_handoff_package.check_package; mutation/coverage/schema/semantic fixture tests; finite inventory exclusions self/gate/marker.
- H3: emit_report: main quarterly-capacity; separate global; actual deltas; verify-only checker command only.
- H5: convergence_review: saved estimators/logs, actual solver/n_iter/max_iter, unknown historical warning capture; metrics/convergence_review.json.
- Negative paths: verify_baseline.registry_summary (duplicate count), compare_quarterly (explicit population N/A), tests_baseline.run_convergence_tests (result['model'], n_iter=1). Production-path regression tests included in summary.
""")
    inv = inventory(out)
    write_json(out / INVENTORY, {"exclusions": EXCLUSIONS,
        "files": {p: r for p, r in inv.items() if p not in EXCLUSIONS}})
    from check_handoff_package import check_package
    gate = check_package(out, require_complete=False)
    write_json(out / "completeness_gate.json", gate)
    if not gate["all_ok"]:
        print(json.dumps(gate, indent=2))
        return 1
    write_json(out / "COMPLETE.json", dict(status="COMPLETE", execution_id=execution_id,
        inventory_sha256=sha256_file(out/INVENTORY), gate_sha256=sha256_file(out/"completeness_gate.json")))
    print(json.dumps(dict(package=str(out), counts=counts, baseline=evidence), indent=2), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "gold-dir", "output-dir"):
        parser.add_argument("--"+name, required=True, type=Path)
    parser.add_argument("--before-provenance", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return generate(args.run_dir.resolve(), args.gold_dir.resolve(), args.output_dir.resolve(), args.before_provenance.resolve())
    except Exception as exc:
        print(f"PACKAGE FAILURE: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
