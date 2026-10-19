"""Command line entry for scan / detect / run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spss_agent.detect import SpssNotFoundError, detect_spss
from spss_agent.pipeline import run_plan
from spss_agent.scan import scan_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用本机 IBM SPSS 跑问卷分析并写中文报告")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect", help="检查 SPSS 安装")
    scan = sub.add_parser("scan", help="梳理项目文件夹")
    scan.add_argument("project")
    run = sub.add_parser("run", help="按已确认的分析方案执行")
    run.add_argument("project")
    run.add_argument("--plan", required=True, help="分析方案 JSON")
    run.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            print(detect_spss().summary())
            return 0
        if args.command == "scan":
            print(scan_text(Path(args.project)))
            return 0
        report = run_plan(Path(args.project), Path(args.plan), timeout=args.timeout)
        print(report)
        return 0
    except SpssNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports the failure
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
