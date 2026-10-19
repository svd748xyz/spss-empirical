"""Execute a confirmed analysis plan and write the report plus trace files."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from spss_agent.detect import detect_spss
from spss_agent.interpret import (
    anova,
    correlations,
    descriptives,
    factor_loadings,
    frequencies,
    mediation,
    pairwise,
    regression_models,
    reliability,
    t_tests,
    variance_share,
)
from spss_agent.oms import parse_oms
from spss_agent.prepare import read_table, write_spss_csv
from spss_agent.report import build_report, fmt_stat, p_phrase
from spss_agent.runner import production_job_xml, run_production, viewer_messages
from spss_agent.syntax import build_syntax, formats_for

def _heading(index: int, title: str) -> str:
    digits = "一二三四五六七八九"
    number = index + 1
    if number <= 10:
        mark = "十" if number == 10 else digits[number - 1]
    elif number < 20:
        mark = "十" + digits[number - 11]
    else:
        mark = str(number)
    return f"（{mark}）{title}"


def _labels(plan: dict) -> dict[str, str]:
    labels = {}
    for variable in plan.get("variables") or []:
        labels[variable["name"]] = variable.get("label") or variable["name"]
    for scale in plan.get("scales") or []:
        labels[scale["name"]] = scale.get("label") or scale["name"]
        for item in scale.get("items") or []:
            labels.setdefault(item, item)
    return labels


def _resolve_data(project: Path, plan: dict) -> Path:
    path = Path(plan["data_file"])
    if not path.is_absolute():
        path = project / path
    if not path.is_file():
        raise FileNotFoundError(f"分析方案中的数据文件不存在：{path}")
    return path


def _discussion(sections: list[dict], labels: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for section in sections:
        kind = section["kind"]
        if kind == "reliability" and (section.get("result") or {}).get("alpha") is not None:
            alpha = section["result"]["alpha"]
            name = labels.get(section.get("scale"), "量表")
            level = "达到常用的 .70 参考线" if alpha >= 0.70 else "低于常用的 .70 参考线"
            lines.append(f"{name}的内部一致性系数{level}，是否保留题项应结合内容效度和 CITC，而不是只看这一次 α。")
        elif kind == "correlation":
            notable = [pair for pair in section.get("pairs") or [] if pair.get("p") is not None and pair["p"] < 0.05]
            lines.append(f"在报告的相关对子中，有 {len(notable)} 对达到 .05 水平。未达到该水平的相关不解释为效应不存在。")
        elif kind == "regression":
            model = (section.get("models") or [{}])[-1]
            if model.get("p") is not None:
                flag = "整体检验达到 .05 水平" if model["p"] < 0.05 else "整体检验未达到 .05 水平"
                lines.append(f"回归模型{flag}，R² = {fmt_stat(model.get('r2'), 3, True)}。系数方向只在本次样本和控制变量设定下成立。")
        elif kind == "mediation":
            result = section.get("result") or {}
            if result.get("p") is not None:
                flag = "达到" if result["p"] < 0.05 else "未达到"
                lines.append(f"Sobel 检验{flag} .05 水平（{p_phrase(result.get('p'))}）。这不是因果中介的证明，也没有给出 Bootstrap 区间。")
        elif kind == "moderation":
            lines.append("调节结论只依据交互项和简单斜率的 SPSS 系数；若交互项不显著，不再把简单斜率解释成调节成立。")
    lines.append("讨论只复述本次输出。横断问卷不能据此主张因果，未检验的假设也不在这里补写。")
    return lines


def run_plan(project: Path, plan_path: Path, timeout: int = 600) -> Path:
    project = project.resolve()
    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if "analyses" not in plan or "data_file" not in plan:
        raise ValueError("分析方案至少要包含 data_file 和 analyses。")
    data_path = _resolve_data(project, plan)
    plan = {**plan, "data_file": str(data_path)}
    install = detect_spss(plan.get("spss_exe"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = project / "spss_output" / stamp
    oms_dir = run_dir / "oms"
    oms_dir.mkdir(parents=True)
    prepared_csv = None
    formats = None
    renames: list[dict] = []
    n_rows = None
    if data_path.suffix.lower() != ".sav":
        frame = read_table(data_path, plan.get("sheet"))
        n_rows = int(len(frame))
        prepared_csv = run_dir / "prepared_data.csv"
        frame, renames = write_spss_csv(frame, prepared_csv)
        formats = formats_for(frame)
    job = build_syntax(plan, prepared_csv, formats, oms_dir)
    syntax_path = run_dir / "analysis.sps"
    syntax_path.write_text(job.text(), encoding="utf-8")
    viewer_path = run_dir / "viewer.txt"
    spj_path = run_dir / "analysis.spj"
    spj_path.write_text(production_job_xml(syntax_path, viewer_path), encoding="utf-8")
    saved_plan = run_dir / "analysis_plan.json"
    saved_plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    notes = ["# 数据说明", "", f"- 原始数据：`{data_path}`", f"- 分析用语法：`{syntax_path}`"]
    if prepared_csv:
        notes.append(f"- 整理后的 CSV：`{prepared_csv}`")
    if renames:
        notes.append("- 下列列名已改成 SPSS 可接受的变量名：")
        notes.extend(f"  - {item['original']} → {item['spss_name']}" for item in renames)
    else:
        notes.append("- 变量名未改写。")
    (run_dir / "数据说明.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

    return_code = run_production(install, spj_path, timeout=timeout)
    messages = viewer_messages(viewer_path)
    labels = _labels(plan)
    grouped: dict[int, list[dict]] = {}
    for block in job.blocks:
        block["parsed"] = parse_oms(Path(block["oms"]))
        grouped.setdefault(block["meta"]["analysis_index"], []).append(block)

    sections = []
    for offset, analysis in enumerate(plan["analyses"]):
        index = offset + 1
        blocks = grouped.get(index, [])
        kind = analysis["type"]
        if kind == "frequencies":
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "人口学频数"),
                "rows": frequencies(blocks[0]["parsed"]) if blocks else [],
            })
        elif kind == "descriptives":
            rows = descriptives(blocks[0]["parsed"]) if blocks else []
            sections.append({"kind": kind, "heading": _heading(offset, "描述统计"), "rows": rows})
        elif kind == "reliability":
            result = reliability(blocks[0]["parsed"]) if blocks else {}
            sections.append({
                "kind": kind,
                "heading": _heading(offset, f"{labels.get(analysis.get('scale'), '量表')}的内部一致性"),
                "scale": analysis.get("scale"),
                "result": result,
            })
        elif kind == "correlation":
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "相关分析"),
                "pairs": correlations(blocks[0]["parsed"]) if blocks else [],
            })
        elif kind == "regression":
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "回归分析"),
                "dependent": analysis.get("dependent"),
                "models": regression_models(blocks[0]["parsed"]) if blocks else [],
            })
        elif kind == "ttest":
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "独立样本 t 检验"),
                "results": t_tests(blocks[0]["parsed"]) if blocks else [],
            })
        elif kind == "anova":
            parsed = blocks[0]["parsed"] if blocks else []
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "单因素方差分析"),
                "results": anova(parsed),
                "pairs": pairwise(parsed),
                "outcomes": analysis.get("outcomes") or [],
            })
        elif kind == "efa":
            parsed = blocks[0]["parsed"] if blocks else []
            result = variance_share(parsed)
            result["loadings"] = factor_loadings(parsed)
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "探索性因素分析"),
                "result": result,
            })
        elif kind == "harman":
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "共同方法偏差"),
                "result": variance_share(blocks[0]["parsed"]) if blocks else {},
            })
        elif kind == "zscreen":
            parsed = blocks[0]["parsed"] if blocks else []
            rows = descriptives(parsed)
            mapping = {item["flag"]: item["var"] for item in (blocks[0]["meta"].get("flags") or [])} if blocks else {}
            for row in rows:
                row["name"] = mapping.get(row["name"], row["name"])
            sections.append({"kind": kind, "heading": _heading(offset, "极端值筛查"), "rows": rows})
        elif kind == "mediation":
            by_step = {block["meta"].get("step"): block["parsed"] for block in blocks}
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "中介效应"),
                "x": analysis["x"],
                "m": analysis["m"],
                "y": analysis["y"],
                "result": mediation(by_step.get("a", []), by_step.get("c", []), by_step.get("b", []), analysis["x"], analysis["m"]),
            })
        elif kind == "moderation":
            by_step = {block["meta"].get("step"): block for block in blocks}
            main_block = by_step.get("main")
            high_block = by_step.get("high")
            low_block = by_step.get("low")
            if main_block:
                labels[main_block["meta"]["x_c"]] = labels.get(analysis["x"], analysis["x"]) + "（中心化）"
                labels[main_block["meta"]["w_c"]] = labels.get(analysis["w"], analysis["w"]) + "（中心化）"
                labels[main_block["meta"]["xw"]] = "交互项"
            sections.append({
                "kind": kind,
                "heading": _heading(offset, "调节效应"),
                "x": analysis["x"],
                "w": analysis["w"],
                "y": analysis["y"],
                "interaction": main_block["meta"]["xw"] if main_block else "",
                "slope_var": high_block["meta"]["slope_var"] if high_block else "",
                "main": regression_models(main_block["parsed"]) if main_block else [],
                "high": regression_models(high_block["parsed"]) if high_block else [],
                "low": regression_models(low_block["parsed"]) if low_block else [],
            })

    methods = plan.get("methods_note") or "使用者确认的研究问题见分析方案。"
    if n_rows is not None:
        methods += f"导入的数据共 {n_rows} 行。"
    report_path = run_dir / "实证分析报告.docx"
    payload = {
        "title": plan.get("title") or "问卷实证分析报告",
        "software": install.summary(),
        "license_note": messages["license_note"],
        "errors": messages["errors"],
        "methods": methods,
        "labels": labels,
        "sections": sections,
        "discussion": _discussion(sections, labels),
        "plan_path": str(saved_plan),
        "syntax_path": str(syntax_path),
        "viewer_path": str(viewer_path),
        "oms_dir": str(oms_dir),
    }
    build_report(payload, report_path)
    project_report = project / "实证分析报告.docx"
    copy_error = ""
    try:
        shutil.copyfile(report_path, project_report)
    except OSError as exc:
        copy_error = str(exc)
    manifest = {
        "spss": install.summary(),
        "return_code": return_code,
        "license_note": messages["license_note"],
        "errors": messages["errors"],
        "plan": str(saved_plan),
        "syntax": str(syntax_path),
        "viewer": str(viewer_path),
        "oms": str(oms_dir),
        "report": str(report_path),
        "project_report": str(project_report),
        "project_report_error": copy_error,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if messages["errors"]:
        raise RuntimeError("SPSS 已运行，但语法日志含错误。报告只写入了已导出的表。详见 " + str(run_dir / "run_manifest.json"))
    return report_path
