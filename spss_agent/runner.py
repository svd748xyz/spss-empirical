"""Run a syntax file through the SPSS Production Facility."""

from __future__ import annotations

import subprocess
from pathlib import Path

from spss_agent.detect import SpssInstall


def production_job_xml(syntax_path: Path, viewer_path: Path) -> str:
    syntax = syntax_path.resolve().as_posix()
    viewer = viewer_path.resolve().as_posix()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<job xmlns="http://www.ibm.com/software/analytics/spss/xml/production" '
        'syntaxFormat="interactive" syntaxErrorHandling="continue" print="false" unicode="true">\n'
        f'  <output outputPath="{viewer}" outputFormat="text-utf8" tableColumnSeparator="tab"/>\n'
        f'  <syntax syntaxPath="{syntax}"/>\n'
        "</job>\n"
    )


def spss_is_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq stats.exe", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "stats.exe" in (result.stdout or "").lower()


def run_production(install: SpssInstall, spj_path: Path, timeout: int = 600) -> int:
    if spss_is_running():
        raise RuntimeError(
            "检测到 stats.exe 已在运行。SPSS 生产作业不能与已打开的 SPSS 同时执行。请先关闭 SPSS 后重试。"
        )
    completed = subprocess.run(
        [str(install.stats_exe), str(spj_path), "-production", "silent"],
        cwd=str(install.directory),
        timeout=timeout,
        check=False,
    )
    return int(completed.returncode)


def viewer_messages(viewer_path: Path) -> dict:
    if not viewer_path.is_file():
        return {"license_note": "", "errors": ["未生成 SPSS 查看器文本输出。"]}
    text = viewer_path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line.strip() for line in text.splitlines()]
    license_note = next((line for line in lines if line), "")
    errors: list[str] = []
    raw_lines = text.splitlines()
    for index, line in enumerate(raw_lines):
        if "Error #" in line or "错误 #" in line:
            snippet = " ".join(part.strip() for part in raw_lines[index : index + 3] if part.strip())
            errors.append(snippet)
    return {"license_note": license_note, "errors": errors}
