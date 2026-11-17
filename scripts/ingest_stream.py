#!/usr/bin/env python3
"""Stream Freddie Mac vintage zips straight to parquet (no raw .txt ever lands on disk).

Why this exists
---------------
The full SFLLD history (2000 -> present) is ~400-550 GB of pipe-delimited .txt.
This machine has ~53 GB free, so the txt must never touch the filesystem. Every
source is therefore decompressed through a FIFO directly into DuckDB:

    unzip -p inner.zip member.txt  ->  named pipe  ->  read_csv  ->  COPY ... parquet

Measured on this box (DuckDB 1.5.6, 16 cores / 15 GB RAM):

  * plain .txt on disk  -> parquet   559 MB/s, peak RSS 1.3 GB
  * unzip | FIFO        -> parquet    88 MB/s, peak RSS 0.34 GB   <- used here
  * zip:// member       -> parquet   137 MB/s, peak RSS 8.6 GB    <- NOT used, see below

`zipfs` is deliberately avoided: it decompresses members in RAM and exceeded
`memory_limit` by 4x (7.7 GB for a 7.5 GB member). The FIFO path costs ~40%
throughput and ~25x less memory, which is the right trade on a 15 GB box.

DuckDB gotchas this encodes
---------------------------
1. `columns={...}` must match the file's real width *exactly*; a mismatch raises
   "Invalid Input Error: Error when sniffing file" even with `null_padding=true`
   or `ignore_errors=true`. So the width is probed from the first line first.
2. Autodetected names are `column0..` below 10 columns and `column00..` at or
   above, so they are never referenced. Probing + declaring `c0..cN` keeps the
   names deterministic.
3. The layout drifts across releases (Release 47 moved SERVICER NAME from
   origination into performance and appended MI CANCELLATION INDICATOR and
   BANKRUPTCY CRAMDOWN COSTS at positions 33-35). Older files are narrower, so
   the probe result is mapped onto a fixed canonical schema positionally and any
   absent trailing column becomes NULL.
4. `/tmp` is tmpfs on this machine. Spilling there means spilling into RAM, so
   `temp_directory` and the FIFO live on the real disk (default `.fifo_work/`).

Usage
-----
    # one nested year zip (historical_data_2005.zip -> historical_data_2005Q1.zip)
    python scripts/ingest_stream.py ingest --src ~/Downloads --years 2000-2026

    # a single flat quarter zip, or an already-extracted pair of .txt files
    python scripts/ingest_stream.py ingest --src path/historical_data_2005Q2.zip
    python scripts/ingest_stream.py ingest --src path/to/historical_data_2005Q2/

Output matches the existing layout so `export_parquet.py` consumers keep working:

    parquet/orig/quarter=2005Q2/data.parquet
    parquet/perf/quarter=2005Q2/data.parquet

Each `quarter=` partition is one origination vintage. Vintages are disjoint loan
cohorts (verified: 2020Q1 and 2020Q2 share 0 loan_ids), and each vintage's
performance rows run forward for years, so the per-quarter partitions are simply
stacked -- there is nothing to deduplicate.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
PARQUET_DIR = ROOT / "parquet"

# Real disk, never /tmp (tmpfs). The FIFO and DuckDB spill both live here.
WORK_DIR = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".fifo_work"))

MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "3GB")
THREADS = int(os.environ.get("DQ_THREADS", "6"))

COMPRESSION = "zstd"
ROW_GROUP_SIZE = 122880

# Column order is file order; names follow the July 2026 file headers, which are
# the canonical vocabulary the rest of the repo (dq_core.py) already uses.
# Positions are stable across releases; later additions are appended, so an
# older, narrower file maps cleanly onto the head of this list.
ORIG_CANON: list[tuple[str, str]] = [
    ("credit_score", "INTEGER"),
    ("first_payment_date", "INTEGER"),
    ("first_time_homebuyer_flag", "VARCHAR"),
    ("maturity_date", "INTEGER"),
    ("msa", "INTEGER"),
    ("mi_percentage", "INTEGER"),
    ("number_of_units", "INTEGER"),
    ("occupancy_status", "VARCHAR"),
    ("cltv", "INTEGER"),
    ("dti", "INTEGER"),
    ("original_upb", "INTEGER"),
    ("ltv", "INTEGER"),
    ("original_interest_rate", "DOUBLE"),
    ("channel", "VARCHAR"),
    ("prepayment_penalty_flag", "VARCHAR"),
    ("product_type", "VARCHAR"),
    ("property_state", "VARCHAR"),
    ("property_type", "VARCHAR"),
    # Postal codes are 3 characters with significant leading zeros ("006" is
    # Puerto Rico), so this one must never be cast to a number.
    ("postal_code", "VARCHAR"),
    ("loan_id", "VARCHAR"),
    ("loan_purpose", "VARCHAR"),
    ("original_loan_term", "INTEGER"),
    ("number_of_borrowers", "INTEGER"),
    ("seller_name", "VARCHAR"),
    ("super_conforming_flag", "VARCHAR"),
    ("pre_harp_loan_id", "VARCHAR"),
    ("program_indicator", "VARCHAR"),
    ("harp_indicator", "VARCHAR"),
    ("valuation_method", "VARCHAR"),
    ("interest_only_indicator", "VARCHAR"),
    ("vantage_score_4", "INTEGER"),
]

PERF_CANON: list[tuple[str, str]] = [
    ("loan_id", "VARCHAR"),
    ("monthly_reporting_period", "INTEGER"),
    ("current_upb", "DOUBLE"),
    ("current_loan_delinquency_status", "VARCHAR"),
    ("loan_age", "INTEGER"),
    ("remaining_months_to_legal_maturity", "INTEGER"),
    ("defect_settlement_date", "INTEGER"),
    ("modification_flag", "VARCHAR"),
    ("zero_balance_code", "VARCHAR"),
    ("zero_balance_effective_date", "INTEGER"),
    ("current_interest_rate", "DOUBLE"),
    ("current_deferred_upb", "DOUBLE"),
    ("due_date_of_last_paid_installment", "INTEGER"),
    ("mi_recoveries", "DOUBLE"),
    ("net_sales_proceeds", "DOUBLE"),
    ("non_mi_recoveries", "DOUBLE"),
    ("expenses", "DOUBLE"),
    ("legal_costs", "DOUBLE"),
    ("maintenance_and_preservation_costs", "DOUBLE"),
    ("taxes_and_insurance", "DOUBLE"),
    ("miscellaneous_expenses", "DOUBLE"),
    ("actual_loss_calculation", "DOUBLE"),
    ("modification_cost", "DOUBLE"),
    ("step_modification_flag", "VARCHAR"),
    ("deferred_payment_plan", "VARCHAR"),
    ("estimated_loan_to_value", "INTEGER"),
    ("zero_balance_removal_upb", "DOUBLE"),
    ("delinquent_accrued_interest", "DOUBLE"),
    ("delinquency_due_to_disaster", "VARCHAR"),
    ("borrower_assistance_status_code", "VARCHAR"),
    ("current_month_modification_cost", "DOUBLE"),
    ("interest_bearing_upb", "DOUBLE"),
    ("mi_cancellation_indicator", "VARCHAR"),
    ("servicer_name", "VARCHAR"),
    ("bankruptcy_cramdown_costs", "DOUBLE"),
]

SOURCES = {"orig": ORIG_CANON, "perf": PERF_CANON}

# Non-capturing group: a capturing group would make findall return only "19"/"20".
QUARTER_RE = re.compile(r"(?:19|20)\d{2}Q[1-4]")


# --------------------------------------------------------------------------- #
# duckdb
# --------------------------------------------------------------------------- #
def connect() -> duckdb.DuckDBPyConnection:
    """DuckDB configured to stay small and never spill into tmpfs."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads={THREADS}")
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory='{WORK_DIR}'")
    # Parquet row order is not meaningful for this dataset and preserving it
    # forces materialisation; see build_warehouse.py for the same reasoning.
    con.execute("SET preserve_insertion_order=false")
    return con


# --------------------------------------------------------------------------- #
# source inspection
# --------------------------------------------------------------------------- #
def zip_members(zip_path: Path) -> list[str]:
    out = subprocess.run(
        ["unzip", "-Z1", str(zip_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [m for m in out.splitlines() if m and not m.endswith("/")]


def probe_first_line(zip_path: Path, member: str) -> str:
    """Read just the first line of a zip member (cheap: stops decompressing early)."""
    p1 = subprocess.Popen(
        ["unzip", "-p", str(zip_path), member],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert p1.stdout is not None
    line = p1.stdout.readline()
    p1.stdout.close()
    p1.terminate()
    try:
        p1.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p1.kill()
    return line.decode("utf-8", errors="replace").rstrip("\r\n")


def probe_width(text_path: Path) -> int:
    with open(text_path, "r", encoding="utf-8", errors="replace") as fh:
        return len(fh.readline().rstrip("\r\n").split("|"))


def probe_width_in_zip(zip_path: Path, member: str) -> int:
    line = probe_first_line(zip_path, member)
    if not line:
        raise RuntimeError(f"empty member: {member} in {zip_path}")
    return len(line.split("|"))


# --------------------------------------------------------------------------- #
# the actual streaming copy
# --------------------------------------------------------------------------- #
def select_sql(width: int, canon: list[tuple[str, str]], quarter: str) -> str:
    """Map probed columns positionally onto the canonical schema.

    Trailing canonical columns the file does not have become typed NULLs, which
    is how a 2001 vintage (no VANTAGESCORE, 32-column performance files) lands in
    the same table as a 2026 vintage.

    `quarter` is stored physically (not only in the path) so the output is
    schema-identical to what export_parquet.py already produced.
    """
    parts: list[str] = []
    for i, (name, typ) in enumerate(canon):
        if i < width:
            parts.append(
                f"c{i} AS {name}" if typ == "VARCHAR" else f"TRY_CAST(c{i} AS {typ}) AS {name}"
            )
        else:
            parts.append(f"NULL::{typ} AS {name}")
    parts.append(f"'{quarter}' AS quarter")
    return ",\n         ".join(parts)


def stream_member_to_parquet(
    con: duckdb.DuckDBPyConnection,
    zip_path: Path,
    member: str,
    canon: list[tuple[str, str]],
    out_path: Path,
    quarter: str,
) -> tuple[int, float]:
    """unzip -p <member> | FIFO -> read_csv -> parquet.  Returns (rows, seconds)."""
    width = probe_width_in_zip(zip_path, member)
    if width < len(canon):
        print(
            f"      {member}: {width} columns on disk, canonical {len(canon)} "
            f"-> {len(canon) - width} trailing column(s) become NULL",
            flush=True,
        )

    fifo = WORK_DIR / f"stream_{os.getpid()}.pipe"
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".parquet.tmp")
    columns = "{" + ", ".join(f"'c{i}': 'VARCHAR'" for i in range(width)) + "}"
    sql = (
        f"COPY (SELECT {select_sql(width, canon, quarter)}\n"
        f"       FROM read_csv('{fifo}', delim='|', header=false, columns={columns}))\n"
        f"  TO '{tmp_out}' (FORMAT parquet, COMPRESSION {COMPRESSION}, "
        f"ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
    )

    errors: list[str] = []

    def feed() -> None:
        try:
            # Opening the FIFO for write blocks until the reader attaches, which
            # is why this runs off the main thread.
            with open(fifo, "wb", buffering=0) as sink:
                proc = subprocess.Popen(
                    ["unzip", "-p", str(zip_path), member],
                    stdout=sink,
                    stderr=subprocess.PIPE,
                )
                _, err = proc.communicate()
                if proc.returncode != 0:
                    errors.append((err or b"").decode("utf-8", "replace")[:400])
        except Exception as exc:  # noqa: BLE001 - surfaced below
            errors.append(repr(exc))

    started = time.time()
    thread = threading.Thread(target=feed, daemon=True)
    thread.start()
    try:
        con.execute(sql)
    finally:
        thread.join(timeout=120)
        fifo.unlink(missing_ok=True)

    if errors:
        tmp_out.unlink(missing_ok=True)
        raise RuntimeError(f"unzip failed for {member}: {errors[0]}")

    rows = con.execute(f"SELECT count(*) FROM read_parquet('{tmp_out}')").fetchone()[0]
    os.replace(tmp_out, out_path)
    return rows, time.time() - started


def ingest_quarter(
    con: duckdb.DuckDBPyConnection,
    quarter: str,
    orig_src: tuple[Path, str] | Path,
    perf_src: tuple[Path, str] | Path,
    out_root: Path,
    force: bool,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for kind, src, canon in (
        ("orig", orig_src, ORIG_CANON),
        ("perf", perf_src, PERF_CANON),
    ):
        out_path = out_root / kind / f"quarter={quarter}" / "data.parquet"
        if out_path.exists() and not force:
            n = con.execute(f"SELECT count(*) FROM read_parquet('{out_path}')").fetchone()[0]
            print(f"    {kind:4s} exists, {n:,} rows -- skipped", flush=True)
            counts[kind] = n
            continue
        if isinstance(src, tuple):
            rows, secs = stream_member_to_parquet(
                con, src[0], src[1], canon, out_path, quarter
            )
        else:
            rows, secs = stream_file_to_parquet(con, src, canon, out_path, quarter)
        size_mb = out_path.stat().st_size / 1e6
        print(
            f"    {kind:4s} {rows:>12,} rows -> {size_mb:7.1f} MB in {secs:5.1f}s",
            flush=True,
        )
        counts[kind] = rows
    return counts


def stream_file_to_parquet(
    con: duckdb.DuckDBPyConnection,
    txt_path: Path,
    canon: list[tuple[str, str]],
    out_path: Path,
    quarter: str,
) -> tuple[int, float]:
    """Same load, but for .txt already sitting on disk (e.g. the existing data/)."""
    width = probe_width(txt_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out_path.with_suffix(".parquet.tmp")
    columns = "{" + ", ".join(f"'c{i}': 'VARCHAR'" for i in range(width)) + "}"
    started = time.time()
    con.execute(
        f"COPY (SELECT {select_sql(width, canon, quarter)}\n"
        f"       FROM read_csv('{txt_path}', delim='|', header=false, columns={columns}))\n"
        f"  TO '{tmp_out}' (FORMAT parquet, COMPRESSION {COMPRESSION}, "
        f"ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
    )
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{tmp_out}')").fetchone()[0]
    os.replace(tmp_out, out_path)
    return rows, time.time() - started


# --------------------------------------------------------------------------- #
# zip handling: year zip -> inner quarter zips -> members
# --------------------------------------------------------------------------- #
def unwrap_quarter_zip(outer_zip: Path, inner_member: str) -> Path:
    """Pull one inner quarter zip out of a year zip (tens of MB, cheap)."""
    target = WORK_DIR / "inner" / Path(inner_member).name
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".zip.tmp")
    with open(tmp, "wb") as fh:
        proc = subprocess.run(
            ["unzip", "-p", str(outer_zip), inner_member],
            stdout=fh,
            stderr=subprocess.PIPE,
        )
    if proc.returncode != 0 or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"could not extract {inner_member} from {outer_zip}: "
            f"{(proc.stderr or b'').decode('utf-8', 'replace')[:300]}"
        )
    os.replace(tmp, target)
    return target


def members_for(quarter: str, inner_zip: Path) -> dict[str, str]:
    """Find the orig/perf members inside a quarter zip, whatever they are called.

    Modern releases use orig_YYYYQn.txt / perf_YYYYQn.txt. Older years shipped
    sample_orig_YYYY.txt / sample_svcg_YYYY.txt, so match on the prefix rather
    than the exact name.
    """
    found: dict[str, str] = {}
    for member in zip_members(inner_zip):
        name = Path(member).name.lower()
        if not name.endswith(".txt"):
            continue
        if name.startswith("orig") or "_orig" in name or "sample_orig" in name:
            found["orig"] = member
        elif (
            name.startswith("perf")
            or "svcg" in name
            or "_perf" in name
            or "sample_perf" in name
        ):
            found["perf"] = member
    missing = {"orig", "perf"} - found.keys()
    if missing:
        raise RuntimeError(
            f"{inner_zip.name}: could not find member(s) {sorted(missing)}; "
            f"members are {zip_members(inner_zip)}"
        )
    return found


def discover_sources(src: Path) -> tuple[dict[str, list[tuple[str, tuple[Path, str]]]], list[Path]]:
    """Return (zip-streamable quarters, extracted .txt quarter directories)."""
    zips: dict[str, list[tuple[str, tuple[Path, str]]]] = {}
    dirs: list[Path] = []

    if src.is_dir():
        candidates = sorted(p for p in src.rglob("*.zip"))
        # A quarter directory is identified by its own name and the matching file,
        # so a recursive scan works for a flat folder, the repo's
        # data/historical_data_2020/historical_data_2020Q1/ layout, and any depth
        # in between -- without hardcoding how many levels to descend.
        for p in src.rglob("historical_data_*Q*"):
            if not p.is_dir():
                continue
            # Directory is historical_data_2020Q1/ but the files inside are
            # orig_2020Q1.txt / perf_2020Q1.txt -- the quarter, without the prefix.
            qs = QUARTER_RE.findall(p.name)
            if qs and (p / f"orig_{qs[0]}.txt").exists():
                dirs.append(p)
    elif src.suffix.lower() == ".zip":
        candidates = [src]
    else:
        raise SystemExit(f"--src {src} is neither a .zip nor a directory")

    for zpath in candidates:
        members = zip_members(zpath)
        inner_zips = [m for m in members if m.lower().endswith(".zip")]
        if inner_zips:
            for inner in inner_zips:
                qs = [q for q in QUARTER_RE.findall(inner)]
                if not qs:
                    continue
                zips.setdefault(qs[0], []).append(("zip-of-zip", (zpath, inner)))
        else:
            qs = [q for q in QUARTER_RE.findall(zpath.name)]
            if not qs:
                for m in members:
                    qs = QUARTER_RE.findall(Path(m).name)
                    if qs:
                        break
            if qs:
                zips.setdefault(qs[0], []).append(("flat", (zpath, "")))
    return zips, dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["ingest", "list"])
    ap.add_argument("--src", required=True, help="year/quarter .zip, or a directory of them")
    ap.add_argument("--out", default=str(PARQUET_DIR), help="parquet root (default: ./parquet)")
    ap.add_argument("--years", default="", help="filter, e.g. 2000-2010,2015")
    ap.add_argument("--quarters", default="", help="comma separated explicit list, e.g. 2005Q1,2005Q2")
    ap.add_argument("--force", action="store_true", help="reload quarters that already exist")
    ap.add_argument("--keep-inner", action="store_true", help="keep unwrapped inner zips")
    args = ap.parse_args()

    src = Path(os.path.expanduser(args.src))
    out_root = Path(args.out).expanduser()
    zips, dirs = discover_sources(src)

    wanted: set[str] | None = None
    if args.quarters:
        wanted = {q.strip().upper() for q in args.quarters.split(",") if q.strip()}
    elif args.years:
        years: set[int] = set()
        for chunk in args.years.split(","):
            chunk = chunk.strip()
            if "-" in chunk:
                lo, hi = chunk.split("-", 1)
                years.update(range(int(lo), int(hi) + 1))
            elif chunk:
                years.add(int(chunk))
        wanted = {
            q for q in list(zips) + [d.name[-6:] for d in dirs] if int(q[:4]) in years
        }

    plan = sorted(q for q in zips if wanted is None or q in wanted)
    dir_plan = [d for d in dirs if wanted is None or d.name[-6:] in wanted]

    print(f"source   : {src}")
    print(f"output   : {out_root}")
    print(f"work dir : {WORK_DIR}   (real disk; /tmp is tmpfs here)")
    print(f"quarters : {len(plan)} zipped + {len(dir_plan)} extracted")
    if not plan and not dir_plan:
        print("nothing to do")
        return 1
    if args.command == "list":
        for q in plan:
            tag, (zp, inner) = zips[q][0]
            label = f"{zp.name}::{inner}" if tag == "zip-of-zip" else zp.name
            print(f"  {q}  {label}")
        for d in dir_plan:
            print(f"  {d.name}  {d} (extracted)")
        return 0

    free_gb = shutil.disk_usage(out_root if out_root.exists() else ROOT).free / 1e9
    print(f"free disk: {free_gb:.0f} GB\n")

    con = connect()
    manifest: list[tuple[str, str, int, str]] = []
    total_t0 = time.time()

    try:
        for quarter in plan:
            tag, (outer, inner_member) = zips[quarter][0]
            print(f"[{quarter}]", flush=True)
            t0 = time.time()
            if tag == "zip-of-zip":
                inner_zip = unwrap_quarter_zip(outer, inner_member)
            else:
                inner_zip = outer
            members = members_for(quarter, inner_zip)
            counts = ingest_quarter(
                con,
                quarter,
                (inner_zip, members["orig"]),
                (inner_zip, members["perf"]),
                out_root,
                args.force,
            )
            if tag == "zip-of-zip" and not args.keep_inner:
                inner_zip.unlink(missing_ok=True)
            print(f"    total {time.time() - t0:.1f}s\n", flush=True)
            manifest += [(quarter, k, v, "zip") for k, v in counts.items()]

        for qdir in dir_plan:
            quarter = qdir.name[-6:]
            print(f"[{quarter}] extracted from {qdir}", flush=True)
            counts = ingest_quarter(
                con,
                quarter,
                qdir / f"orig_{quarter}.txt",
                qdir / f"perf_{quarter}.txt",
                out_root,
                args.force,
            )
            manifest += [(quarter, k, v, "txt") for k, v in counts.items()]
    finally:
        con.close()
        if not args.keep_inner:
            shutil.rmtree(WORK_DIR / "inner", ignore_errors=True)

    elapsed = time.time() - total_t0
    rows = sum(r for _, _, r, _ in manifest)
    print(f"done: {len(plan) + len(dir_plan)} quarters, {rows:,} rows in {elapsed / 60:.1f} min")
    free_after = shutil.disk_usage(ROOT).free / 1e9
    print(f"free disk now: {free_after:.0f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())