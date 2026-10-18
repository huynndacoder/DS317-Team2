#!/usr/bin/env python3
"""
Profile the 3 fraud datasets for the DS317 data inventory.

Reads each CSV in batches of COLUMNS (not rows) so that every statistic is
EXACT: a whole column is in memory at once, so nunique/top-3/mean/std are
computed over the full column rather than merged from per-chunk approximations.
Peak memory stays bounded because only COL_BATCH columns are resident.

Outputs dataset_profiles.json for scripts/build_inventory_xlsx.py.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUTPUT = ROOT / "dataset_profiles.json"

COL_BATCH = 60  # columns held in memory per pass
HIGH_MISSING_PCT = 70.0  # flag threshold, in PERCENT


def profile_csv(path: Path, col_batch: int = COL_BATCH) -> dict:
    """Return exact per-column statistics for a CSV."""
    all_cols = pd.read_csv(path, nrows=0).columns.tolist()
    n_rows = None
    columns = {}

    for start in range(0, len(all_cols), col_batch):
        batch = all_cols[start : start + col_batch]
        df = pd.read_csv(path, usecols=batch, low_memory=False)
        df = df[batch]  # preserve original column order
        if n_rows is None:
            n_rows = len(df)

        for col in batch:
            s = df[col]
            n_missing = int(s.isna().sum())
            non_null = s.dropna()
            n_unique = int(non_null.nunique())

            info = {
                "dtype": str(s.dtype),
                "n_missing": n_missing,
                "pct_missing": round(n_missing / len(s) * 100, 2) if len(s) else 0.0,
                "n_unique": n_unique,
            }

            if pd.api.types.is_numeric_dtype(s) and len(non_null):
                info["min"] = float(non_null.min())
                info["max"] = float(non_null.max())
                info["mean"] = float(non_null.mean())
                # pandas std() is numerically stable; the previous
                # sum-of-squares approach lost all precision on large ints.
                std = non_null.std()
                info["std"] = float(std) if pd.notna(std) else None

            if len(non_null):
                top = non_null.value_counts().head(3)
                info["top3"] = [[str(v), int(c)] for v, c in top.items()]

            flags = []
            if n_unique <= 1:
                flags.append("constant")
            if info["pct_missing"] > HIGH_MISSING_PCT:
                flags.append("high_missing")
            # A key candidate is a DISCRETE column that is exactly unique on
            # every row. Continuous floats are near-unique by nature, so a
            # ratio test would flag every PCA component as an identifier.
            if (
                n_rows
                and n_unique == n_rows
                and n_missing == 0
                and not pd.api.types.is_float_dtype(s)
            ):
                flags.append("suspected_id")
            info["flags"] = flags

            columns[col] = info

        del df

    return {"n_rows": n_rows, "n_cols": len(all_cols), "columns": columns}


def label_stats(profile: dict, label_col: str) -> dict:
    """Positive-class count and rate, read off the label column's own top-3."""
    info = profile["columns"][label_col]
    counts = {v: c for v, c in info.get("top3", [])}
    n_pos = counts.get("1", 0)
    return {
        "label_col": label_col,
        "n_positive": n_pos,
        "n_negative": profile["n_rows"] - n_pos,
    }


def main():
    profiles = {}

    print("=== IEEE-CIS train_transaction ===")
    txn = profile_csv(DATA_DIR / "train_transaction.csv")
    print("=== IEEE-CIS train_identity ===")
    ident = profile_csv(DATA_DIR / "train_identity.csv")

    # Identity joins onto transaction by TransactionID; only 24% of
    # transactions have an identity record, so identity-column missing
    # counts are relative to identity rows, not transaction rows.
    ieee_cols = dict(txn["columns"])
    for col, info in ident["columns"].items():
        if col == "TransactionID":
            continue
        info = dict(info)
        info["denominator"] = ident["n_rows"]
        info["source_table"] = "train_identity.csv"
        ieee_cols[col] = info
    for col in txn["columns"]:
        ieee_cols[col]["denominator"] = txn["n_rows"]
        ieee_cols[col]["source_table"] = "train_transaction.csv"

    profiles["ieee_cis"] = {
        "display_name": "IEEE-CIS Fraud Detection (Vesta)",
        "n_rows": txn["n_rows"],
        "n_identity_rows": ident["n_rows"],
        "n_cols_txn": txn["n_cols"],
        "n_cols_ident": ident["n_cols"],
        "files": ["train_transaction.csv", "train_identity.csv"],
        "columns": ieee_cols,
        **label_stats(txn, "isFraud"),
    }

    print("=== CCFD-2023 ===")
    ccfd = profile_csv(DATA_DIR / "creditcard_2023.csv")
    for info in ccfd["columns"].values():
        info["denominator"] = ccfd["n_rows"]
        info["source_table"] = "creditcard_2023.csv"
    ccfd.update(
        display_name="Credit Card Fraud Detection Dataset 2023",
        files=["creditcard_2023.csv"],
        **label_stats(ccfd, "Class"),
    )
    profiles["ccfd_2023"] = ccfd

    print("=== ULB ===")
    ulb = profile_csv(DATA_DIR / "creditcard.csv")
    for info in ulb["columns"].values():
        info["denominator"] = ulb["n_rows"]
        info["source_table"] = "creditcard.csv"
    ulb.update(
        display_name="Credit Card Fraud Detection (ULB / mlg-ulb)",
        files=["creditcard.csv"],
        **label_stats(ulb, "Class"),
    )
    profiles["ulb"] = ulb

    # File sizes measured from disk, not quoted from the download page.
    for key, prof in profiles.items():
        prof["bytes_on_disk"] = sum(
            (DATA_DIR / f).stat().st_size for f in prof["files"]
        )

    OUTPUT.write_text(json.dumps(profiles, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT}")
    for key, prof in profiles.items():
        rate = prof["n_positive"] / prof["n_rows"] * 100
        print(
            f"  {prof['display_name']}: {prof['n_rows']:,} rows, "
            f"{len(prof['columns'])} cols, {prof['n_positive']:,} positives "
            f"({rate:.3f}%)"
        )


if __name__ == "__main__":
    main()
