PYTHON ?= ./venv/bin/python

.PHONY: test test-labels test-model

test: test-labels test-model

test-labels:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/label/test_label_logic.py

test-model:
	OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 $(PYTHON) scripts/model/tests_pilot_repair.py --config configs/pilot_baseline.yaml --output-dir output/tests/pilot
