PYTHON ?= ./venv/bin/python

.PHONY: test test-labels test-model verify-dataset verify-baseline

test: test-labels test-model

test-labels:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/label/test_label_logic.py

test-model:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/model/tests_baseline.py --config configs/baseline.yaml --output-dir output/tests/baseline

verify-dataset:
	DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 $(PYTHON) scripts/gold/verify_research_dataset.py --dataset-dir output/research

verify-baseline:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/model/check_handoff_package.py --package-dir output/baseline/report
