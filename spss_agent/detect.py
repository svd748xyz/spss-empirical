"""Locate a local IBM SPSS Statistics installation."""

from __future__ import annotations

import os
import winreg
from dataclasses import dataclass
from pathlib import Path


class SpssNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpssInstall:
    version: str
    directory: Path
    stats_exe: Path

    def summary(self) -> str:
        return f"IBM SPSS Statistics {self.version} @ {self.stats_exe}"


def _from_registry() -> SpssInstall | None:
    root = r"SOFTWARE\IBM\SPSS Statistics"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as key:
            count = winreg.QueryInfoKey(key)[0]
            versions = [winreg.EnumKey(key, i) for i in range(count)]
    except OSError:
        return None
    installs: list[SpssInstall] = []
    for version in versions:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{root}\{version}\Setup") as setup:
                directory = Path(winreg.QueryValueEx(setup, "Directory")[0])
        except OSError:
            continue
        exe = directory / "stats.exe"
        if exe.is_file():
            installs.append(SpssInstall(version=version, directory=directory, stats_exe=exe))
    if not installs:
        return None
    installs.sort(key=lambda item: [int(part) if part.isdigit() else 0 for part in item.version.split(".")])
    return installs[-1]


def detect_spss(explicit: str | None = None) -> SpssInstall:
    """Resolve stats.exe. Order: argument, SPSS_STATS_EXE, registry."""
    candidate = explicit or os.environ.get("SPSS_STATS_EXE")
    if candidate:
        exe = Path(candidate)
        if exe.is_dir():
            exe = exe / "stats.exe"
        if not exe.is_file():
            raise SpssNotFoundError(
                f"指定的 SPSS 程序不存在：{candidate}\n"
                "请安装已授权的 IBM SPSS Statistics，或设置环境变量 SPSS_STATS_EXE 为 stats.exe 的完整路径。"
            )
        return SpssInstall(version="custom", directory=exe.parent, stats_exe=exe)
    found = _from_registry()
    if found is None:
        raise SpssNotFoundError(
            "未在本机注册表找到 IBM SPSS Statistics（HKLM\\SOFTWARE\\IBM\\SPSS Statistics）。\n"
            "请先安装并授权 IBM SPSS Statistics for Windows，确认安装目录中存在 stats.exe，"
            "然后设置 SPSS_STATS_EXE，例如：\n"
            '  setx SPSS_STATS_EXE "F:\\SPSS\\stats.exe"'
        )
    return found
