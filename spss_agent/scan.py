"""List the materials in a study folder."""

from __future__ import annotations

import json
from pathlib import Path

from spss_agent.prepare import read_table

DATA_SUFFIXES = {".sav", ".xlsx", ".xls", ".csv"}
TEXT_NAMES = {"需求说明.txt", "需求说明.md"}


def scan_project(project: Path) -> dict:
    project = project.resolve()
    if not project.is_dir():
        raise NotADirectoryError(f"项目文件夹不存在：{project}")
    files = []
    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue
        if "spss_output" in path.parts or path.name.startswith("."):
            continue
        files.append(str(path.relative_to(project)))
    data = []
    for relative in files:
        path = project / relative
        if path.suffix.lower() not in DATA_SUFFIXES:
            continue
        item = {"path": relative, "bytes": path.stat().st_size}
        if path.suffix.lower() != ".sav":
            try:
                frame = read_table(path)
            except Exception as exc:  # noqa: BLE001 - surface the reader error in the inventory
                item["error"] = str(exc)
            else:
                item["rows"] = int(len(frame))
                item["columns"] = [str(column) for column in frame.columns]
        else:
            item["note"] = "变量表在调用 SPSS 读取 .sav 时获取"
        data.append(item)
    brief = None
    for name in TEXT_NAMES:
        candidate = project / name
        if candidate.is_file():
            brief = candidate.read_text(encoding="utf-8", errors="replace")
            break
    return {"project": str(project), "files": files, "data": data, "需求说明": brief}


def scan_text(project: Path) -> str:
    payload = scan_project(project)
    return json.dumps(payload, ensure_ascii=False, indent=2)
