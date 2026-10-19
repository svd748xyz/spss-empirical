"""Read project tables and write an SPSS-safe CSV when needed."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from spss_agent.names import is_spss_name, sanitize


def read_table(path: Path, sheet: str | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet or 0)
    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    raise ValueError(f"暂不能直接预览该数据文件：{path.name}。支持 .sav（由 SPSS 读取）、.xlsx、.csv。")


def write_spss_csv(frame: pd.DataFrame, dest: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Return a frame with safe column names and a rename log."""
    used: set[str] = set()
    renames: list[dict] = []
    columns: list[str] = []
    for index, column in enumerate(frame.columns, start=1):
        original = str(column).strip()
        safe = original if is_spss_name(original) and original not in used else sanitize(original, used, index)
        if safe == original:
            used.add(safe)
        columns.append(safe)
        if safe != original:
            renames.append({"original": original, "spss_name": safe})
    prepared = frame.copy()
    prepared.columns = columns
    dest.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(dest, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
    return prepared, renames


def infer_formats(frame: pd.DataFrame) -> list[tuple[str, str]]:
    formats: list[tuple[str, str]] = []
    for column in frame.columns:
        series = frame[column]
        numeric = pd.to_numeric(series, errors="coerce")
        non_empty = series.dropna()
        if len(non_empty) and numeric.notna().sum() >= max(1, int(0.9 * series.notna().sum())):
            formats.append((str(column), "F12.4"))
        else:
            formats.append((str(column), "A128"))
    return formats
