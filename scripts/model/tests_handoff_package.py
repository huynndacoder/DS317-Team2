"""Bounded synthetic production-path package tests; children always mocked (no recursion)."""
import contextlib
import io
import json
import math
import pickle
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

import generate_handoff_package as gp
import check_handoff_package as cp
import verify_baseline as vp


def fixture(root):
    run, gold, before = [root/x for x in ("run", "gold", "before")]
    for p in (run/"predictions", run/"models", run/"metrics", run/"logs", gold, before):
        p.mkdir(parents=True, exist_ok=True)
    membership, targets = [], []
    for role, n, pos in (("train_tune", 10, 1), ("train_refit", 20, 4)):
        for i in range(n):
            loan = f"{role}_{i}"
            membership.append(dict(loan_id=loan, role=role))
            targets.append(dict(loan_id=loan, label_12m=int(i<pos)))
    pd.DataFrame(membership).to_parquet(gold/"membership.parquet", index=False)
    pd.DataFrame(targets).to_parquet(gold/"target.parquet", index=False)
    pd.DataFrame(dict(loan_id=[r["loan_id"] for r in membership], cohort=["2013Q1"]*len(membership),
                      label_window_end=[201401]*len(membership))).to_parquet(gold/"split.parquet", index=False)
    pooled, quarters, recomputed = [], [], {}
    for stage, year, letter in (("stage_A_validation", 2016, "a"), ("stage_B_development_test", 2019, "b")):
        evaluation = gp.STAGES[stage][1]
        for suffix, model_name in (("lr", "logistic_regression"), ("xgb", "xgboost")):
            df = pd.DataFrame(dict(loan_id=[f"{evaluation}_{i}" for i in range(512)],
                label_12m=[0, 1, 1, 0]*128, cohort=[f"{year}Q{q}" for q in range(1,5) for _ in range(128)],
                score=[.1, .9, .7, .2]*128))
            name = evaluation+"_"+suffix
            df.to_parquet(run/"predictions"/(name+".parquet"), index=False)
            m = vp.ranking_metrics(df.label_12m, df.score, df.loan_id)
            pq = vp.per_quarter_capture(df.label_12m, df.score, df.cohort, df.loan_id)
            qr = vp._quarter_detail_rows(df.label_12m, df.score, df.cohort, df.loan_id)
            recomputed[name] = {**m, **pq, "model": model_name, "stage": letter.upper(), "per_quarter": qr}
            r = dict(model=model_name, stage=stage, n=512, n_pos=256, prevalence=.5,
                     total_selected=pq["total_selected"], total_tp=pq["total_tp"],
                     capacity_pooled_capture=pq["capacity_pooled_capture"], macro_mean_capture=pq["macro_mean_capture"],
                     macro_mean_lift=2., macro_mean_auc=1., k=m["k"], selected_fraction=m["selected_fraction"], tp_selected=m["tp_selected"])
            for key in ("precision_at_k", "capture_at_k", "lift_at_k", "roc_auc", "average_precision", "brier", "log_loss"):
                r[key+"_global"] = m[key]
            r.update(brier_constant_rate=0., log_loss_constant_rate=0., prevalence_used=0.)
            pooled.append(r)
            quarters += [dict(model=model_name, stage=stage, **q) for q in qr]
            obj = SimpleNamespace(solver="lbfgs", max_iter=1000, n_iter_=np.array([12 if letter=="a" else 13]), coef_=np.array([[.2]]), intercept_=np.array([0.]))
            with (run/"models"/f"stage_{letter}_{suffix}.pkl").open("wb") as f:
                pickle.dump({"model":obj}, f)
    gp.write_csv(run/"metrics/pooled.csv", pooled)
    gp.write_csv(run/"metrics/per_quarter.csv", quarters)
    (run/"logs/train.log").write_text("Historical capture unavailable; LR stage A n_iter=12; LR stage B n_iter=13\n")
    for i in range(7):
        (run/f"metadata_{i}.json").write_text('{}\n')
    assert len(gp.inventory(run)) == 18
    gp.write_json(before/"input_hashes_before.json", gp.inventory(run))
    gp.write_json(before/"source_hashes_before.json", {"fixture":"pre-edit"})
    gp.write_json(before/"dependency_versions.json", {"fixture":True})
    (before/"git_status_before.txt").write_text("synthetic fixture\n")

    def runner(argv, **kwargs):
        out = Path(argv[argv.index("--output-dir")+1])
        if "tests_baseline.py" in argv[1]:
            gp.write_json(out/"convergence_evaluator_tests.json", dict(groups={"fixture":dict(tests=[dict(name="synthetic fixture", **{"pass":True})], passed=1, failed=0)},
                          overall_passed=True, total_tests_passed=1, total_tests_failed=0))
        else:
            ids = sorted(cp.expected_required_ids())
            records = [dict(name=n, **{"pass":True}, required=True, detail="synthetic child fixture") for n in ids]
            gp.write_json(out/"verification.json", dict(checks=records, overall=True, required_ids=ids, required_missing=[], registry=vp.registry_summary(records, ids)))
            gp.write_json(out/"recomputed_metrics.json", recomputed)
            gp.write_json(out/"artifact_inventory_sha256.json", gp.inventory(run))
            samples = {}
            for n in recomputed:
                sampled = pd.read_parquet(run/"predictions"/(n+".parquet")).sample(n=512,random_state=42)
                samples[n] = dict(sampled=512, matched=512, mismatched=0, max_abs_diff=0., mean_abs_diff=0.,
                    loan_ids=sampled.loan_id.astype(str).tolist(), predicted_probabilities=sampled.score.tolist(), saved_scores=sampled.score.tolist(),
                    atol=1e-8, rtol=0., seed=42, **{"pass":True})
            gp.write_json(out/"sample_inference.json", samples)
        return subprocess.CompletedProcess(argv, 0, "fixture child completed\n", "")
    return run, gold, before, runner


def run_package_tests():
    records = []

    def t(name, ok, detail=""):
        records.append(dict(name=name, **{"pass":bool(ok)}, detail=str(detail)))

    def raises(function):
        try:
            function()
        except (ValueError, OSError, KeyError, TypeError):
            return True
        return False

    for name, n, pos, y in (("unequal prevalence", 10, 1, [0,1,1,0]),
                             ("equal prevalence", 4, 2, [0,1,1,0]),
                             ("single negative", 10, 1, [0,0]), ("single positive", 10, 1, [1,1]),
                             ("zero fit probability", 10, 0, [0,1]), ("one fit probability", 10, 10, [0,1])):
        e = gp.constant_evidence(n, pos, y)
        scores = np.full(len(y), pos/n, dtype=np.float64)
        t("H1 sklearn "+name, cp.close(e["brier_constant_rate"], brier_score_loss(y, scores)) and
          cp.close(e["log_loss_constant_rate"], log_loss(y, scores, labels=[0,1])))
    e = gp.constant_evidence(10, 1, [0,1,1,0])
    t("H1 known unequal .41/1.2039728", cp.close(e["brier_constant_rate"], .41) and cp.close(e["log_loss_constant_rate"], 1.203972804325936))
    for y in (None, [], [0,2], [float("nan")], [[0,1]], [float("inf")]):
        t("H1 reject invalid labels "+repr(y), raises(lambda: gp.constant_evidence(10, 1, y)))
    changed = gp.constant_evidence(10, 2, [0,1,1,0])
    t("H1 changed fit counts change probability/loss", e["p_fit"] != changed["p_fit"] and e["brier_constant_rate"] != changed["brier_constant_rate"])
    t("model float32 preservation uses existing verifier tolerance, not baseline tolerance",
      cp.saved_model_metric_matches(.012939495285946997, .012939495965838432) and
      not cp.close(.012939495285946997, .012939495965838432) and not cp.saved_model_metric_matches(.01,.02))
    sample_report = "historical log: train_baseline\n## Verify-only commands\npython scripts/model/check_handoff_package.py --package-dir /fixture\n"
    t("verify-only checks command section, not historical log source names", cp.verify_only_commands_valid(sample_report, Path('/fixture')))
    t("verify-only rejects actual training command", not cp.verify_only_commands_valid(sample_report+'python train_baseline.py\n', Path('/fixture')))

    base = dict(model="lr", stage="A", cohort="Q", n=1000, n_pos=10, k=50, tp_selected=5, prevalence=.01,
                selected_fraction=.05, precision_at_k=.1, capture_at_k=.5, lift_at_k=10., roc_auc=.7)
    for metric in ("roc_auc", "prevalence", "selected_fraction", "precision_at_k", "capture_at_k", "lift_at_k"):
        for value in (None, float("nan"), float("inf")):
            bad = dict(base, **{metric:value})
            t("quarter invalid-both rejected "+metric+repr(value), not vp.compare_quarterly([bad],[bad])[0])
    na = dict(base, n_pos=0, tp_selected=0, prevalence=0., precision_at_k=0., capture_at_k=None, lift_at_k=None, roc_auc=None)
    t("quarter explicit no-positive NA accepted", vp.compare_quarterly([na],[na])[0])
    nan_na = dict(na, roc_auc=float("nan"), capture_at_k=float("nan"), lift_at_k=float("nan"))
    t("quarter explicit population NA accepts CSV NaN representation", vp.compare_quarterly([nan_na],[nan_na])[0])
    inf_na = dict(na, roc_auc=float("inf"))
    t("quarter population NA never accepts infinity", not vp.compare_quarterly([inf_na],[inf_na])[0])
    for field in ("n", "n_pos", "k", "tp_selected"):
        invalid = dict(base, **{field:None})
        t("quarter missing-both count rejected "+field, not vp.compare_quarterly([invalid],[invalid])[0])
    duplicate = vp.registry_summary([dict(name="x", required=True, **{"pass":True})]*2, {"x", "missing"})
    t("registry duplicate production helper structured count", duplicate == dict(missing=["missing"], failed=[], duplicate={"x":2}, unexpected=[]))
    registry = vp.registry_summary([dict(name="x", required=True, **{"pass":False}), dict(name="extra", required=True, **{"pass":True})], {"x", "missing"})
    t("registry failed/missing/unexpected distinct", registry == dict(missing=["missing"], failed=["x"], duplicate={}, unexpected=["extra"]))

    with tempfile.TemporaryDirectory(prefix="package_tests_") as tmp, contextlib.redirect_stdout(io.StringIO()):
        root = Path(tmp)
        run, gold, before, good_runner = fixture(root)
        import duckdb
        con = duckdb.connect(config={"threads":2, "memory_limit":"1GB"})
        vp.create_gold_views(con, gold)
        t("verifier lazy Gold SQL views count join", con.execute("SELECT count(*) FROM membership JOIN target USING(loan_id)").fetchone()[0] == 30)
        con.close()
        out = root/"success"
        code = gp.generate(run, gold, out, before, good_runner)
        result = cp.check_package(out)
        t("H2/H4 fresh package passes first invocation", code == 0 and result["all_ok"], [c for c in result["checks"] if not c["pass"]])
        snapshot = gp.inventory(out)
        t("H2 completed output refused unchanged", raises(lambda: gp.generate(run,gold,out,before,good_runner)) and gp.inventory(out)==snapshot)
        stale = root/"stale"; stale.mkdir()
        gp.write_json(stale/"verification.json", {"overall":True})
        snap = gp.inventory(stale)
        t("H2 stale PASS refuses before child/failure", raises(lambda: gp.generate(run,gold,stale,before,lambda *a,**k: (_ for _ in ()).throw(AssertionError("must not run")))) and gp.inventory(stale)==snap)
        for child in ("tests", "verify"):
            for mode in ("exit77", "missing", "malformed", "declares_failure"):
                target = root/(child+"_"+mode)
                def bad_runner(argv, child=child, mode=mode, **kwargs):
                    is_target = ("tests_baseline.py" in argv[1]) == (child=="tests")
                    if not is_target:
                        return good_runner(argv, **kwargs)
                    if mode=="exit77":
                        # Even fresh stale-looking PASS JSON may not override nonzero exit.
                        good_runner(argv, **kwargs)
                        return subprocess.CompletedProcess(argv,77,"failure stdout","injected failure")
                    p = Path(argv[argv.index("--output-dir")+1])/("convergence_evaluator_tests.json" if child=="tests" else "verification.json")
                    if mode=="missing":
                        return subprocess.CompletedProcess(argv,0,"","")
                    if mode=="malformed":
                        p.write_text('{bad')
                    else:
                        good_runner(argv, **kwargs)
                        data = gp.load_json(p)
                        data["overall_passed" if child=="tests" else "overall"] = False
                        gp.write_json(p,data)
                    return subprocess.CompletedProcess(argv,0,"","")
                failed = raises(lambda: gp.generate(run,gold,target,before,bad_runner))
                t(f"H2 {child} {mode} fails closed", failed and not (target/"COMPLETE.json").exists())

        def mutate_test(name, rel, transform, semantic_id=None):
            p = out/rel
            original = p.read_bytes()
            try:
                transform(p)
                checked = cp.check_package(out)
                bad = [c for c in checked["checks"] if not c["pass"]]
                t(name, not checked["all_ok"] and (not semantic_id or any(c["check_id"]==semantic_id for c in bad)), bad)
            finally:
                p.write_bytes(original)
        for rel in ("REPORT.md", "audit_manifest.json", "metrics/pooled.csv"):
            mutate_test("H4 missing "+rel, rel, lambda p:p.unlink(), "required_nonempty")
            mutate_test("H4 zero-byte "+rel, rel, lambda p:p.write_text(''), "required_nonempty")
        mutate_test("H4 malformed JSON", "audit_manifest.json", lambda p:p.write_text('{'), "evidence_schema")
        mutate_test("H4 modified report hash", "REPORT.md", lambda p:p.write_text(p.read_text()+"tamper"), "inventory_hash")
        mutate_test("H4 modified metric hash", "metrics/pooled.csv", lambda p:p.write_text(p.read_text()+"bad"), "inventory_hash")
        def remove_inventory(p):
            inv=gp.load_json(p); inv["files"].pop("REPORT.md"); gp.write_json(p,inv)
        mutate_test("H4 missing inventory coverage", gp.INVENTORY, remove_inventory, "required_inventory_coverage")
        inv=gp.load_json(out/gp.INVENTORY)
        t("H4 inventory excludes self/gate/marker only", inv["exclusions"]==gp.EXCLUSIONS and not set(gp.EXCLUSIONS)&set(inv["files"]))
        # Wrong loss with correct p in BOTH CSVs is rejected semantically, independent of hashes.
        originals = {rel:(out/rel).read_bytes() for rel in ("metrics/pooled.csv", "metrics/constant_baseline_by_stage.csv")}
        try:
            for rel in originals:
                rows=gp.load_csv(out/rel)
                for row in rows:
                    p=float(row.get("p_fit",row.get("prevalence_used")))
                    row["brier_constant_rate"]=p*(1-p)
                    row["log_loss_constant_rate"]=-p*math.log(p)-(1-p)*math.log1p(-p)
                gp.write_csv(out/rel,rows)
            checked=cp.check_package(out)
            t("H1 both CSV losses old formula despite correct p fail semantic gate", any(c["check_id"]=="baseline_saved_label_sklearn" and not c["pass"] for c in checked["checks"]))
        finally:
            for rel,b in originals.items(): (out/rel).write_bytes(b)
        mutate_test("H1 one wrong CSV vs correct report/evidence", "metrics/pooled.csv",
                    lambda p:p.write_text(p.read_text().replace(str(e['brier_constant_rate']),'.09')), "pooled_baseline")
        # Real fixture membership counts, not constants, drive SQL baseline.
        first=gp.baseline_evidence(run,gold)
        targets=pd.read_parquet(gold/"target.parquet")
        targets.loc[targets.loan_id=="train_tune_1","label_12m"]=1
        targets.to_parquet(gold/"target.parquet",index=False)
        second=gp.baseline_evidence(run,gold)
        t("H1 production SQL fit counts change losses", first[0]["p_fit"] != second[0]["p_fit"] and first[0]["brier_constant_rate"] != second[0]["brier_constant_rate"])
    passed=sum(r["pass"] for r in records)
    return dict(passed=passed, failed=len(records)-passed, tests=records)
