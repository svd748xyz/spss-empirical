"""Chinese empirical-report writer. Every statistic is passed in; nothing is imputed."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips


def fmt_p(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.001:
        return "< .001"
    text = f"{value:.3f}"
    return text[1:] if text.startswith("0") else text


def fmt_stat(value: float | None, digits: int = 3, drop_leading: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{value:.{digits}f}"
    if drop_leading:
        if text.startswith("-0"):
            text = "-" + text[2:]
        elif text.startswith("0"):
            text = text[1:]
    return text


def p_phrase(value: float | None) -> str:
    if value is None:
        return "p 未能读出"
    if value < 0.001:
        return "p < .001"
    return f"p = {fmt_p(value)}"


def fmt_df(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.2f}"


def stars(p: float | None) -> str:
    if p is None:
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def _set_run_font(run, east_asia: str, size: float, bold: bool = False) -> None:
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)


def _paragraph(doc: Document, text: str, *, center: bool = False, bold: bool = False, size: float = 12, font: str = "宋体", indent: bool = False) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if indent:
        paragraph.paragraph_format.first_line_indent = Twips(480)
    run = paragraph.add_run(text)
    _set_run_font(run, font, size, bold)


def _border(cell, edge: str, sz: str | None) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    element = borders.find(qn(f"w:{edge}"))
    if element is None:
        element = OxmlElement(f"w:{edge}")
        borders.append(element)
    if sz is None:
        element.set(qn("w:val"), "nil")
    else:
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), sz)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")


def _three_line(table, header: bool = True) -> None:
    for row_index, row in enumerate(table.rows):
        last = row_index == len(table.rows) - 1
        for cell in row.cells:
            for edge in ("left", "right"):
                _border(cell, edge, None)
            _border(cell, "top", "12" if row_index == 0 else None)
            if header and row_index == 0:
                _border(cell, "bottom", "6")
            elif last:
                _border(cell, "bottom", "12")
            else:
                _border(cell, "bottom", None)
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    _set_run_font(run, "宋体", 10.5, bold=(header and row_index == 0))


def _table(doc: Document, headers: list[str], rows: list[list[str]], footnote: str = "注：* p < .05，** p < .01，*** p < .001。") -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    for r_index, row in enumerate(rows, start=1):
        for c_index, value in enumerate(row):
            table.rows[r_index].cells[c_index].text = value
    _three_line(table)
    if footnote:
        note = doc.add_paragraph()
        note.paragraph_format.space_after = Pt(6)
        run = note.add_run(footnote)
        _set_run_font(run, "宋体", 9)


def _label(labels: dict, name: str) -> str:
    return labels.get(name, name)


def _missing(doc: Document, what: str) -> None:
    _paragraph(doc, f"本次运行没有从 SPSS 输出中读到{what}，因此这里不报告相应数字。", indent=True)


def build_report(payload: dict, dest: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Twips(1440)
    section.bottom_margin = Twips(1440)
    section.left_margin = Twips(1440)
    section.right_margin = Twips(1440)
    labels = payload.get("labels") or {}
    _paragraph(doc, payload.get("title") or "问卷实证分析报告", center=True, bold=True, size=16, font="黑体")
    _paragraph(doc, "方法与结果", center=True, size=14, font="黑体")
    software = payload.get("software") or "IBM SPSS Statistics"
    _paragraph(doc, f"分析软件为{software}。原始输出语言设为英文，以便从 OMS 表读取数值；正文根据这些数值用中文书写。", indent=True)
    if payload.get("license_note"):
        _paragraph(doc, f"SPSS 输出首行授权提示：{payload['license_note']}", indent=True)
    if payload.get("errors"):
        _paragraph(doc, "语法日志中出现错误。下文只使用已经成功导出的表格，不补写未算出的结果。", indent=True)
        for error in payload["errors"]:
            _paragraph(doc, error, size=10.5)

    _paragraph(doc, "一、方法", bold=True, size=14, font="黑体")
    _paragraph(doc, payload.get("methods") or "", indent=True)
    method_bits = ["量表得分为所属题项的平均值。"]
    kinds = {section["kind"] for section in payload.get("sections") or []}
    if "correlation" in kinds:
        method_bits.append("相关分析采用皮尔逊积差相关，缺失按成对删除。")
    if "regression" in kinds or "mediation" in kinds or "moderation" in kinds:
        method_bits.append("回归采用强迫进入法，缺失按列表删除，并报告方差膨胀系数。")
    if "mediation" in kinds:
        method_bits.append("中介检验报告路径 a、b、c′ 以及 Sobel 检验，不报告 Bootstrap 置信区间。")
    if "moderation" in kinds:
        method_bits.append("调节变量与自变量在形成交互项之前按样本均值中心化；简单斜率是把调节变量再中心化到均值上下一个标准差后重新回归得到的自变量系数。")
    _paragraph(doc, "".join(method_bits), indent=True)

    _paragraph(doc, "二、结果", bold=True, size=14, font="黑体")
    for section_data in payload.get("sections") or []:
        kind = section_data["kind"]
        if kind == "frequencies":
            _write_frequencies(doc, section_data, labels)
        elif kind == "descriptives":
            _write_descriptives(doc, section_data, labels)
        elif kind == "reliability":
            _write_reliability(doc, section_data, labels)
        elif kind == "correlation":
            _write_correlation(doc, section_data, labels)
        elif kind == "regression":
            _write_regression(doc, section_data, labels)
        elif kind == "ttest":
            _write_ttest(doc, section_data, labels)
        elif kind == "anova":
            _write_anova(doc, section_data, labels)
        elif kind == "mediation":
            _write_mediation(doc, section_data, labels)
        elif kind == "moderation":
            _write_moderation(doc, section_data, labels)
        elif kind == "efa":
            _write_efa(doc, section_data, labels)
        elif kind == "harman":
            _write_harman(doc, section_data)
        elif kind == "zscreen":
            _write_zscreen(doc, section_data, labels)

    _paragraph(doc, "三、简要讨论", bold=True, size=14, font="黑体")
    for text in payload.get("discussion") or ["结果仅描述本次样本中的统计关系，问卷横断设计不能据此作因果结论。"]:
        _paragraph(doc, text, indent=True)
    _paragraph(doc, "四、过程文件", bold=True, size=14, font="黑体")
    _paragraph(doc, f"分析方案：{payload.get('plan_path', '')}", indent=True)
    _paragraph(doc, f"SPSS 语法：{payload.get('syntax_path', '')}", indent=True)
    _paragraph(doc, f"查看器文本：{payload.get('viewer_path', '')}", indent=True)
    _paragraph(doc, f"OMS 目录：{payload.get('oms_dir', '')}", indent=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)


def _write_frequencies(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "频数", bold=True, size=12, font="黑体")
    rows = section_data.get("rows") or []
    if not rows:
        _missing(doc, "频数表")
        return
    body = [[" / ".join(_label(labels, part) for part in row["labels"]), fmt_stat(row.get("n"), 0), fmt_stat(row.get("percent"), 1)] for row in rows]
    _table(doc, ["类别", "频数", "百分比"], body)


def _write_descriptives(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "描述统计", bold=True, size=12, font="黑体")
    rows = section_data.get("rows") or []
    if not rows:
        _missing(doc, "描述统计表")
        return
    body = []
    for row in rows:
        body.append([
            _label(labels, row["name"]),
            fmt_stat(row.get("n"), 0),
            fmt_stat(row.get("mean"), 2),
            fmt_stat(row.get("sd"), 2),
            fmt_stat(row.get("minimum"), 2),
            fmt_stat(row.get("maximum"), 2),
        ])
    _table(doc, ["变量", "n", "M", "SD", "最小值", "最大值"], body)
    first = rows[0]
    _paragraph(
        doc,
        f"各变量的有效样本量、均值和标准差见表。例如{_label(labels, first['name'])}的均值为 {fmt_stat(first.get('mean'), 2)}（SD = {fmt_stat(first.get('sd'), 2)}）。",
        indent=True,
    )


def _write_reliability(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    title = _label(labels, section_data.get("scale") or "量表")
    _paragraph(doc, section_data.get("heading") or f"{title}的内部一致性", bold=True, size=12, font="黑体")
    if result.get("alpha") is None:
        _missing(doc, f"{title}的信度表")
        return
    _paragraph(
        doc,
        f"{title}包含 {fmt_stat(result.get('n_items'), 0)} 个题项，Cronbach's α = {fmt_stat(result.get('alpha'), 3, drop_leading=True)}。",
        indent=True,
    )
    body = [
        [ _label(labels, item["name"]), fmt_stat(item.get("citc"), 3, True), fmt_stat(item.get("alpha_if_deleted"), 3, True)]
        for item in result.get("items") or []
    ]
    if body:
        _table(doc, ["题项", "CITC", "删除后 α"], body)


def _write_correlation(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "相关分析", bold=True, size=12, font="黑体")
    pairs = section_data.get("pairs") or []
    if not pairs:
        _missing(doc, "相关矩阵")
        return
    body = []
    sentences = []
    for pair in pairs:
        body.append([
            _label(labels, pair["x"]),
            _label(labels, pair["y"]),
            fmt_stat(pair.get("r"), 3, True) + stars(pair.get("p")),
            fmt_p(pair.get("p")),
            fmt_stat(pair.get("n"), 0),
        ])
        if pair.get("r") is None or pair.get("p") is None:
            continue
        direction = "正" if pair["r"] > 0 else "负"
        flag = "显著" if pair["p"] < 0.05 else "不显著"
        sentences.append(
            f"{_label(labels, pair['x'])}与{_label(labels, pair['y'])}呈{direction}相关，r = {fmt_stat(pair['r'], 3, True)}，{p_phrase(pair['p'])}，该相关{flag}。"
        )
    _table(doc, ["变量1", "变量2", "r", "p", "n"], body)
    for sentence in sentences:
        _paragraph(doc, sentence, indent=True)


def _coef_rows(model: dict, labels: dict) -> list[list[str]]:
    rows = []
    for coef in model.get("coefficients") or []:
        rows.append([
            _label(labels, coef["name"]),
            fmt_stat(coef.get("B"), 3),
            fmt_stat(coef.get("se"), 3),
            (fmt_stat(coef.get("beta"), 3, True) + stars(coef.get("p"))) if coef.get("beta") is not None else "—",
            fmt_stat(coef.get("t"), 2),
            fmt_p(coef.get("p")),
            fmt_stat(coef.get("vif"), 2),
        ])
    return rows


def _model_sentence(model: dict) -> str:
    if not model or model.get("r2") is None:
        return "该模型的拟合指标未能从输出中读出。"
    return (
        f"模型 R² = {fmt_stat(model.get('r2'), 3, True)}，调整 R² = {fmt_stat(model.get('adj_r2'), 3, True)}，"
        f"F({fmt_stat(model.get('df_model'), 0)}, {fmt_stat(model.get('df_resid'), 0)}) = {fmt_stat(model.get('F'), 2)}，"
        f"{p_phrase(model.get('p'))}。"
    )


def _write_regression(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "回归分析", bold=True, size=12, font="黑体")
    models = section_data.get("models") or []
    if not models:
        _missing(doc, "回归模型表")
        return
    dependent = _label(labels, section_data.get("dependent") or "因变量")
    _paragraph(doc, f"因变量为{dependent}。", indent=True)
    for model in models:
        change = ""
        if model.get("delta_r2") is not None and str(model.get("model")) != "1":
            change = (
                f"相对上一层 ΔR² = {fmt_stat(model.get('delta_r2'), 3, True)}，"
                f"ΔF = {fmt_stat(model.get('delta_f'), 2)}，{p_phrase(model.get('delta_p'))}。"
            )
        _paragraph(doc, f"模型{model.get('model')}：" + _model_sentence(model) + change, indent=True)
    _table(doc, ["预测变量", "B", "SE", "β", "t", "p", "VIF"], _coef_rows(models[-1], labels))
    high_vif = [coef for coef in models[-1].get("coefficients") or [] if coef.get("vif") is not None and coef["vif"] > 5 and coef["name"] != "(Constant)"]
    if high_vif:
        names = "、".join(_label(labels, coef["name"]) for coef in high_vif)
        _paragraph(doc, f"{names}的 VIF 大于 5，解释回归系数时需要考虑共线性。", indent=True)


def _write_ttest(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "独立样本 t 检验", bold=True, size=12, font="黑体")
    results = section_data.get("results") or []
    if not results:
        _missing(doc, "t 检验表")
        return
    body = []
    for result in results:
        group_text = "；".join(
            f"{group['group']}：M = {fmt_stat(group.get('mean'), 2)}，SD = {fmt_stat(group.get('sd'), 2)}，n = {fmt_stat(group.get('n'), 0)}"
            for group in result.get("groups") or []
        )
        body.append([
            _label(labels, result["outcome"]),
            group_text,
            fmt_stat(result.get("t"), 2),
            fmt_df(result.get("df")),
            fmt_p(result.get("p")) + stars(result.get("p")),
        ])
        if result.get("levene_p") is None:
            variance = "未能读出 Levene 检验"
        elif result.get("equal_var"):
            variance = "方差齐"
        else:
            variance = "方差不齐，采用校正自由度的 t 值"
        if result.get("t") is None:
            _paragraph(doc, f"{_label(labels, result['outcome'])}的 t 检验数值未能读出。", indent=True)
        else:
            _paragraph(
                doc,
                f"{_label(labels, result['outcome'])}的 Levene 检验 {p_phrase(result.get('levene_p'))}，{variance}。"
                f"组间比较 t({fmt_df(result.get('df'))}) = {fmt_stat(result.get('t'), 2)}，{p_phrase(result.get('p'))}，"
                f"Cohen's d = {fmt_stat(result.get('d'), 2)}。d 由 SPSS 给出的两组均值、标准差和样本量计算。",
                indent=True,
            )
    _table(doc, ["因变量", "分组描述", "t", "df", "p"], body)


def _write_anova(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "单因素方差分析", bold=True, size=12, font="黑体")
    results = section_data.get("results") or []
    if not results:
        _missing(doc, "方差分析表")
        return
    body = []
    for result in results:
        outcome = result.get("outcome") or section_data.get("outcomes", [""])[0]
        body.append([
            _label(labels, outcome),
            fmt_stat(result.get("F"), 2),
            fmt_stat(result.get("df_between"), 0),
            fmt_stat(result.get("df_within"), 0),
            fmt_p(result.get("p")) + stars(result.get("p")),
            fmt_stat(result.get("eta2"), 3, True),
            fmt_p(result.get("levene_p")),
        ])
        if result.get("p") is not None and result["p"] >= 0.05:
            _paragraph(doc, f"{_label(labels, outcome)}的总体检验未达到 .05，因此不把事后比较解释为组间差异。", indent=True)
        else:
            pairs = [pair for pair in section_data.get("pairs") or [] if pair.get("p") is not None and pair["p"] < 0.05]
            if pairs:
                shown = "；".join(f"{' 与 '.join(pair['labels'][-2:])}，{p_phrase(pair['p'])}" for pair in pairs[:8])
                _paragraph(doc, f"Bonferroni 校正后 p < .05 的比较：{shown}。", indent=True)
            elif section_data.get("pairs") is not None:
                _paragraph(doc, "已要求 Bonferroni 事后比较。总体检验若显著而这里没有成对结果，说明比较表没有被解析出来。", indent=True)
    _table(doc, ["因变量", "F", "df组间", "df组内", "p", "η²", "Levene p"], body)


def _write_mediation(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "中介效应", bold=True, size=12, font="黑体")
    if result.get("indirect") is None:
        _missing(doc, "中介路径系数")
        return
    x = _label(labels, section_data["x"])
    m = _label(labels, section_data["m"])
    y = _label(labels, section_data["y"])
    _paragraph(
        doc,
        f"以{x}为自变量、{m}为中介变量、{y}为因变量。本机 SPSS 未安装 Hayes PROCESS，因此没有估计 Bootstrap 5000 次的间接效应置信区间。"
        f"路径 a 的 B = {fmt_stat((result.get('a') or {}).get('B'), 3)}，"
        f"{p_phrase((result.get('a') or {}).get('p'))}；路径 b 的 B = {fmt_stat((result.get('b') or {}).get('B'), 3)}，"
        f"{p_phrase((result.get('b') or {}).get('p'))}。总效应 c 的 B = {fmt_stat((result.get('c') or {}).get('B'), 3)}，"
        f"直接效应 c′ 的 B = {fmt_stat((result.get('c_prime') or {}).get('B'), 3)}。"
        f"间接效应 ab = {fmt_stat(result.get('indirect'), 3)}，Sobel z = {fmt_stat(result.get('z'), 2)}，{p_phrase(result.get('p'))}。"
        "该检验不是 Bootstrap 置信区间。",
        indent=True,
    )


def _slope_sentence(name: str, model: dict, slope_var: str, labels: dict) -> str:
    models = model if isinstance(model, list) else [model]
    last = models[-1] if models else {}
    target = None
    for coef in last.get("coefficients") or []:
        if coef["name"] == slope_var:
            target = coef
            break
    if not target:
        return f"{name}的简单斜率未能读出。"
    return (
        f"{name}时，简单斜率 B = {fmt_stat(target.get('B'), 3)}，"
        f"t = {fmt_stat(target.get('t'), 2)}，{p_phrase(target.get('p'))}。"
    )


def _write_moderation(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "调节效应", bold=True, size=12, font="黑体")
    main = section_data.get("main") or []
    if not main:
        _missing(doc, "调节模型")
        return
    last = main[-1]
    interaction = section_data.get("interaction")
    coef = None
    for item in last.get("coefficients") or []:
        if item["name"] == interaction:
            coef = item
            break
    _paragraph(doc, "中心化后的分层回归中，" + _model_sentence(last), indent=True)
    if coef:
        _paragraph(
            doc,
            f"交互项 {_label(labels, section_data['x'])} × {_label(labels, section_data['w'])} 的 B = {fmt_stat(coef.get('B'), 3)}，"
            f"β = {fmt_stat(coef.get('beta'), 3, True)}，t = {fmt_stat(coef.get('t'), 2)}，{p_phrase(coef.get('p'))}。",
            indent=True,
        )
    else:
        _missing(doc, "交互项系数")
    _paragraph(doc, _slope_sentence("调节变量高于均值一个标准差", section_data.get("high") or {}, section_data.get("slope_var") or "", labels), indent=True)
    _paragraph(doc, _slope_sentence("调节变量低于均值一个标准差", section_data.get("low") or {}, section_data.get("slope_var") or "", labels), indent=True)
    _table(doc, ["预测变量", "B", "SE", "β", "t", "p", "VIF"], _coef_rows(last, labels))


def _write_harman(doc, section_data) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "共同方法偏差", bold=True, size=12, font="黑体")
    pct = result.get("first_pct")
    if pct is None:
        present = "、".join(result.get("tables_present") or []) or "无"
        _paragraph(doc, f"未读到未旋转第一因子的方差百分比。OMS 中的表：{present}。", indent=True)
        return
    note = "低于 40% 这一常用参考" if pct < 40 else "不低于 40% 这一常用参考"
    _paragraph(doc, f"将全部题项做未旋转主成分分析，第一因子解释的方差为 {fmt_stat(pct, 2)}%，{note}。这只是 Harman 单因子检验的描述，不能证明没有共同方法偏差。", indent=True)


def _write_zscreen(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "极端值筛查", bold=True, size=12, font="黑体")
    rows = section_data.get("rows") or []
    if not rows:
        _missing(doc, "极端值筛查表")
        return
    bits = []
    for row in rows:
        count = None
        if row.get("mean") is not None and row.get("n") is not None:
            count = int(round(row["mean"] * row["n"]))
        bits.append(f"{_label(labels, row['name'])} {count if count is not None else '—'} 人")
    _paragraph(doc, "按各变量自身均值和标准差计算，绝对值超过 3 个标准差的人数为：" + "，".join(bits) + "。本次不因极端值删除个案。", indent=True)


def _write_efa(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "探索性因素分析", bold=True, size=12, font="黑体")
    if result.get("kmo") is None and result.get("bartlett_chi2") is None:
        present = "、".join(result.get("tables_present") or []) or "无"
        _paragraph(doc, f"未读到 KMO 或 Bartlett 数值。OMS 中实际出现的表为：{present}。", indent=True)
        return
    _paragraph(
        doc,
        f"KMO = {fmt_stat(result.get('kmo'), 3)}，Bartlett 球形检验 χ²({fmt_stat(result.get('bartlett_df'), 0)}) = {fmt_stat(result.get('bartlett_chi2'), 2)}，{p_phrase(result.get('bartlett_p'))}。"
        f"未旋转时第一因子解释方差 {fmt_stat(result.get('first_pct'), 2)}%。下表给出旋转后的载荷，正文不给因子命名。",
        indent=True,
    )
    loads = result.get("loadings") or {}
    items = loads.get("items") or []
    factors = loads.get("factors") or []
    values = loads.get("values") or {}
    if items and factors:
        body = []
        for item in items:
            body.append([_label(labels, item)] + [fmt_stat(values.get(f"{item}|{factor}"), 2) for factor in factors])
        _table(
            doc,
            ["题项"] + [f"因子{factor}" for factor in factors],
            body,
            footnote="注：单元格为 SPSS 旋转后的因子载荷，小于 .40 的数值也保留。",
        )
    elif result.get("kmo") is not None:
        _paragraph(doc, "未从 OMS 读到旋转载荷表，因此这里不列因子载荷。", indent=True)
