#!/usr/bin/env bash
# Rebuild the 12-month label table end to end.
#
#   1. profile the parquet store   (read-only survey, step 1)
#   2. known-answer logic tests    (step 6.1)
#   3. build the label table       (step 2)
#   4. verify the exported table   (step 6.3)
#   5. export real-data evidence   (step 6.2)
#   6. write the report            (step 7)
#
# Usage:
#   bash scripts/label/run_labels.sh              # full history (110 cohorts)
#   bash scripts/label/run_labels.sh --force      # rebuild existing partitions
#   QS="2020Q1 2021Q1" bash scripts/label/run_labels.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

PY=./venv/bin/python
: "${DQ_MEMORY_LIMIT:=5GB}"
: "${DQ_THREADS:=10}"
export DQ_MEMORY_LIMIT DQ_THREADS

FORCE=""
[[ "${1:-}" == "--force" ]] && FORCE="--force"
QS="${QS:-}"
QARGS=()
[[ -n "$QS" ]] && read -r -a QARGS <<< "--quarters $QS"

echo "=== resources ==="
echo "memory_limit=$DQ_MEMORY_LIMIT threads=$DQ_THREADS"
free -g | head -2
df -h . | tail -1

echo
echo "=== 1/6 profile ==="
mkdir -p output/label_tables
$PY scripts/label/profile_data.py ${QARGS[@]+"${QARGS[@]}"} | tee output/label_tables/profile.log

echo
echo "=== 2/6 logic tests ==="
$PY scripts/label/test_label_logic.py | tee output/label_tables/test_label_logic.log

echo
echo "=== 3/6 build labels ==="
$PY scripts/label/build_labels.py $FORCE ${QARGS[@]+"${QARGS[@]}"} | tee output/label_build.log

echo
echo "=== 4/6 verify ==="
$PY scripts/label/verify_labels.py ${QARGS[@]+"${QARGS[@]}"} | tee output/label_tables/verification.log

echo
echo "=== 5/6 evidence (real-data label examples) ==="
# label_examples.py names its selector --cohorts; translate the shared QARGS
COHARGS=()
[[ -n "$QS" ]] && read -r -a COHARGS <<< "--cohorts $QS"
$PY scripts/label/label_examples.py ${COHARGS[@]+"${COHARGS[@]}"} \
    | tee output/label_tables/label_evidence.log

echo
echo "=== 6/6 report ==="
$PY scripts/label/write_report.py | tee output/label_tables/report.log

echo
echo "=== artefacts ==="
ls -la output/label_tables/
echo "label partitions: $(ls output/labels | wc -l)"
du -sh output/labels