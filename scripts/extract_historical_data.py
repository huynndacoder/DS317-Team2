#!/usr/bin/env python3
"""
Extract Fannie/Freddie-style historical loan data.

Source layout (as shipped):
    data/historical_data_<YEAR>.zip
        -> historical_data_<YEAR>Q<n>.zip
            -> orig_<YEAR>Q<n>.txt
            -> perf_<YEAR>Q<n>.txt

Target layout (mirrors the source structure, one dir per quarter):
    data/historical_data_<YEAR>/historical_data_<YEAR>Q<n>/orig_<YEAR>Q<n>.txt
                                                          /perf_<YEAR>Q<n>.txt

Disk-safety: the inner quarterly zip is streamed to a temp file, its two txt
members are extracted, and the temp zip is deleted immediately. Peak extra
disk is one inner zip (~100 MB), so total footprint stays ~= the txt size.

Resumable: a quarter whose two txt files already exist at full size is skipped.
"""

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
YEARS = range(2020, 2025)  # 2025/2026 are already extracted on disk
CHUNK = 1 << 20


def quarter_dirs(year: int):
    outer = DATA / f"historical_data_{year}.zip"
    with zipfile.ZipFile(outer) as zo:
        for name in sorted(zo.namelist()):
            if not name.endswith(".zip"):
                continue
            q = name.replace("historical_data_", "").replace(".zip", "")  # e.g. 2020Q1
            yield outer, name, q


def already_done(q: str) -> bool:
    year = q[:4]
    outdir = DATA / f"historical_data_{year}" / f"historical_data_{q}"
    expected = {
        f"orig_{q}.txt": None,
        f"perf_{q}.txt": None,
    }
    # sizes come from the inner zip listing; caller checks against those
    return outdir, expected


def extract_quarter(outer: Path, member: str, q: str) -> None:
    year = q[:4]
    outdir = DATA / f"historical_data_{year}" / f"historical_data_{q}"
    outdir.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix=f"extract_{q}_", dir="/tmp/opencode"))
    tmp_zip = tmpdir / member
    try:
        with zipfile.ZipFile(outer) as zo, zo.open(member) as src, open(tmp_zip, "wb") as dst:
            shutil.copyfileobj(src, dst, CHUNK)

        with zipfile.ZipFile(tmp_zip) as zi:
            for info in zi.infolist():
                target = outdir / info.filename
                if target.exists() and target.stat().st_size == info.file_size:
                    print(f"    skip (exists): {target.name}", flush=True)
                    continue
                print(
                    f"    extract: {info.filename} ({info.file_size / 1e6:.1f} MB)",
                    flush=True,
                )
                with zi.open(info) as s, open(target, "wb") as d:
                    shutil.copyfileobj(s, d, CHUNK)
                if target.stat().st_size != info.file_size:
                    raise IOError(
                        f"size mismatch {target}: "
                        f"{target.stat().st_size} != {info.file_size}"
                    )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> int:
    failures = []
    for year in YEARS:
        outer = DATA / f"historical_data_{year}.zip"
        if not outer.exists():
            print(f"MISSING outer: {outer}", flush=True)
            failures.append(str(outer))
            continue
        print(f"=== {outer.name} ===", flush=True)
        for o, member, q in quarter_dirs(year):
            print(f"  -- {q} --", flush=True)
            try:
                extract_quarter(o, member, q)
            except Exception as exc:  # keep going; report at the end
                print(f"    FAILED {q}: {exc}", flush=True)
                failures.append(q)

    print("\n=== extraction done ===", flush=True)
    if failures:
        print("FAILURES: " + ", ".join(failures), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
