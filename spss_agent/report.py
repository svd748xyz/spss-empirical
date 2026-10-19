"""Chinese empirical-report writer. Every statistic is passed in; nothing is imputed."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Twips


def fmt_p(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


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
        return "p<0.001"
    return f"p={fmt_p(value)}"


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


def _msd(mean: float | None, sd: float | None) -> str:
    if mean is None and sd is None:
        return "—"
    return f"{fmt_stat(mean, 2)}±{fmt_stat(sd, 2)}"


def _plain_heading(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    if text.startswith("（") and "）" in text:
        return text.split("）", 1)[1] or fallback
    return text


def _next_caption(doc: Document, title: str, n: float | None = None) -> str:
    doc._table_seq = getattr(doc, "_table_seq", 0) + 1
    sample = f"（n={fmt_stat(n, 0)}）" if n is not None else ""
    return f"表{doc._table_seq}  {title}{sample}"


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


def _unique_cells(row):
    seen = []
    ids: set[int] = set()
    for cell in row.cells:
        marker = id(cell._tc)
        if marker in ids:
            continue
        ids.add(marker)
        seen.append(cell)
    return seen


def _write_cell(cell, text: str, *, bold: bool = False, size: float = 10.5, align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(text)
    _set_run_font(run, "宋体", size, bold)
    tc_pr = cell._tc.get_or_add_tcPr()
    align_el = tc_pr.find(qn("w:vAlign"))
    if align_el is None:
        align_el = OxmlElement("w:vAlign")
        tc_pr.append(align_el)
    align_el.set(qn("w:val"), "center")


def _set_table_width(table, weights: list[int]) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    width = tbl_pr.find(qn("w:tblW"))
    if width is None:
        width = OxmlElement("w:tblW")
        tbl_pr.append(width)
    width.set(qn("w:type"), "pct")
    width.set(qn("w:w"), "5000")
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    jc = tbl_pr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        tbl_pr.append(jc)
    jc.set(qn("w:val"), "center")
    usable = 9020
    total = sum(weights) or 1
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        cols = grid.findall(qn("w:gridCol"))
        for index, col in enumerate(cols):
            weight = weights[index] if index < len(weights) else 1
            col.set(qn("w:w"), str(int(usable * weight / total)))
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            weight = weights[index] if index < len(weights) else 1
            tc_w = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tc_w)
            tc_w.set(qn("w:type"), "dxa")
            tc_w.set(qn("w:w"), str(int(usable * weight / total)))


def _paint_three_line(table, *, caption_rows: int, header_rows: int, note: bool) -> None:
    last = len(table.rows) - 1
    note_at = last if note else None
    header_start = caption_rows
    header_end = caption_rows + header_rows - 1
    body_end = (note_at - 1) if note_at is not None else last
    for row_index, row in enumerate(table.rows):
        for cell in _unique_cells(row):
            for edge in ("left", "right", "top", "bottom"):
                _border(cell, edge, None)
            if row_index < caption_rows:
                _border(cell, "bottom", "12")
            elif header_start <= row_index <= header_end:
                if caption_rows == 0 and row_index == header_start:
                    _border(cell, "top", "12")
                if row_index == header_end:
                    _border(cell, "bottom", "6")
            elif row_index == body_end:
                _border(cell, "bottom", "12")


def _table(
    doc: Document,
    headers: list[str],
    rows: list[list[str]],
    *,
    caption: str,
    footnote: str | None = None,
    weights: list[int] | None = None,
    header_matrix: list[list[str]] | None = None,
    h_merges: list[tuple[int, int, int]] | None = None,
    v_merges: list[tuple[int, int, int]] | None = None,
) -> None:
    """Three-line table. Caption sits above the top rule; the note sits below the bottom rule."""
    matrix = header_matrix if header_matrix is not None else [headers]
    cols = max(len(matrix[0]), max((len(row) for row in rows), default=0))
    body = [list(row) + [""] * (cols - len(row)) for row in rows]
    matrix = [list(row) + [""] * (cols - len(row)) for row in matrix]
    footnote_row = [footnote] + [""] * (cols - 1) if footnote else None
    all_rows = [[caption] + [""] * (cols - 1), *matrix, *body]
    if footnote_row:
        all_rows.append(footnote_row)
    table = doc.add_table(rows=len(all_rows), cols=cols)
    for r_index, row in enumerate(all_rows):
        for c_index, value in enumerate(row):
            _write_cell(table.rows[r_index].cells[c_index], value, bold=(r_index == 0))
    table.cell(0, 0).merge(table.cell(0, cols - 1))
    caption_cell = table.cell(0, 0)
    caption_cell.paragraphs[0].paragraph_format.space_before = Pt(6)
    caption_cell.paragraphs[0].paragraph_format.space_after = Pt(2)
    for row_index, start, end in h_merges or []:
        table.cell(1 + row_index, start).merge(table.cell(1 + row_index, end))
    for col, start, end in v_merges or []:
        table.cell(1 + start, col).merge(table.cell(1 + end, col))
    if footnote_row:
        table.cell(len(all_rows) - 1, 0).merge(table.cell(len(all_rows) - 1, cols - 1))
        note_cell = table.cell(len(all_rows) - 1, 0)
        _write_cell(note_cell, footnote or "", size=9, align=WD_ALIGN_PARAGRAPH.LEFT)
    _set_table_width(table, weights or [1] * cols)
    _paint_three_line(table, caption_rows=1, header_rows=len(matrix), note=footnote_row is not None)
    tail = doc.add_paragraph()
    tail.paragraph_format.space_before = Pt(0)
    tail.paragraph_format.space_after = Pt(6)


def _star_note(rows: list[list[str]]) -> str | None:
    if any("*" in cell for row in rows for cell in row):
        return "注：* p<0.05，** p<0.01，*** p<0.001。"
    return None


def _coded(values: dict | None, code: str) -> str:
    if not values:
        return str(code)
    text = str(code)
    if text in values:
        return values[text]
    try:
        number = float(text)
    except ValueError:
        return text
    for key, label in values.items():
        try:
            if float(key) == number:
                return label
        except ValueError:
            continue
    return text


def _label(labels: dict, name: str) -> str:
    return labels.get(name, name)


def _missing(doc: Document, what: str) -> None:
    _paragraph(doc, f"本次运行没有从 SPSS 输出中读到{what}，因此这里不报告相应数字。", indent=True)


def build_report(payload: dict, dest: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    labels = payload.get("labels") or {}
    _paragraph(doc, payload.get("title") or "问卷实证分析报告", center=True, bold=True, size=16, font="黑体")
    if payload.get("errors"):
        _paragraph(doc, "语法日志中出现错误。下文只使用已经成功导出的表格，不补写未算出的结果。", indent=True)
        for error in payload["errors"]:
            _paragraph(doc, error, size=10.5)

    _paragraph(doc, "一、方法", bold=True, size=14, font="黑体")
    _paragraph(doc, payload.get("methods") or "", indent=True)
    method_bits = []
    kinds = {section["kind"] for section in payload.get("sections") or []}
    sections = payload.get("sections") or []
    if "correlation" in kinds:
        method_bits.append("相关分析采用皮尔逊积差相关，缺失按成对删除。")
    if "spearman" in kinds:
        method_bits.append("等级相关采用 Spearman 系数，双尾检验，缺失按成对删除。")
    if "chisq" in kinds:
        method_bits.append("分类变量的关联采用 Pearson 卡方检验。")
    if "mannwhitney" in kinds:
        method_bits.append("两组的非参数比较采用 Mann-Whitney U，比较的是平均秩。")
    if "kruskal" in kinds:
        method_bits.append("多组的非参数比较采用 Kruskal-Wallis H，比较的是平均秩。")
    if "logistic" in kinds:
        method_bits.append("二元因变量采用进入法 logistic 回归，报告发生比 Exp(B)。")
    if "regression" in kinds or "mediation" in kinds or "moderation" in kinds or "moderated_mediation" in kinds:
        method_bits.append("线性回归采用强迫进入法，缺失按列表删除，并报告方差膨胀系数。")
    if any(section.get("structure") == "serial" for section in sections):
        method_bits.append("链式中介按中介变量的书写顺序建立方程。每条特定间接效应用系数乘积的 Sobel 检验，不把路径加总，也不报告 Bootstrap 置信区间。")
    if any(section.get("kind") == "mediation" and section.get("structure") != "serial" and isinstance(section.get("m"), list) and len(section["m"]) > 1 for section in sections):
        method_bits.append("并行中介为每个中介分别估计路径 a，再把全部中介同时纳入因变量方程估计路径 b 和 c′。每条特定间接效应单独做 Sobel 检验，不把间接效应加总后检验，也不报告 Bootstrap 置信区间。")
    if any(section.get("kind") == "mediation" and section.get("structure") != "serial" and not (isinstance(section.get("m"), list) and len(section["m"]) > 1) for section in sections):
        method_bits.append("中介检验报告路径 a、b、c′ 以及 Sobel 检验，不报告 Bootstrap 置信区间。")
    if "moderation" in kinds:
        method_bits.append("调节变量与自变量在形成交互项之前按样本均值中心化。多个调节变量只估计各自与自变量的二阶交互，简单斜率是该调节变量位于均值上下一个标准差、其余调节变量取均值时的自变量系数。")
    if "moderated_mediation" in kinds:
        method_bits.append("有调节的中介在调节变量的均值和均值上下一个标准差上估计条件间接效应，并用 Sobel 公式检验系数乘积。这不是 Hayes PROCESS，也没有 Bootstrap 置信区间。")
    if method_bits:
        _paragraph(doc, "".join(method_bits), indent=True)

    _paragraph(doc, "二、结果", bold=True, size=14, font="黑体")
    sections = payload.get("sections") or []
    index = 0
    while index < len(sections):
        section_data = sections[index]
        kind = section_data["kind"]
        if kind == "reliability":
            end = index + 1
            while end < len(sections) and sections[end]["kind"] == "reliability":
                end += 1
            _write_reliability_group(doc, sections[index:end], labels)
            index = end
            continue
        if kind in {"ttest", "anova"}:
            end = index + 1
            while end < len(sections) and sections[end]["kind"] in {"ttest", "anova"}:
                end += 1
            _write_comparisons(doc, sections[index:end], labels)
            index = end
            continue
        if kind == "frequencies":
            _write_frequencies(doc, section_data, labels)
        elif kind == "descriptives":
            _write_descriptives(doc, section_data, labels)
        elif kind == "correlation":
            _write_correlation(doc, section_data, labels)
        elif kind == "spearman":
            _write_correlation(doc, section_data, labels)
        elif kind == "regression":
            _write_regression(doc, section_data, labels)
        elif kind == "mediation":
            _write_mediation(doc, section_data, labels)
        elif kind == "moderation":
            _write_moderation(doc, section_data, labels)
        elif kind == "moderated_mediation":
            _write_moderated_mediation(doc, section_data, labels)
        elif kind == "chisq":
            _write_chisq(doc, section_data, labels)
        elif kind == "mannwhitney":
            _write_mannwhitney(doc, section_data, labels)
        elif kind == "kruskal":
            _write_kruskal(doc, section_data, labels)
        elif kind == "logistic":
            _write_logistic(doc, section_data, labels)
        elif kind == "efa":
            _write_efa(doc, section_data, labels)
        elif kind == "harman":
            _write_harman(doc, section_data)
        elif kind == "zscreen":
            _write_zscreen(doc, section_data, labels)
        index += 1

    _paragraph(doc, "三、简要讨论", bold=True, size=14, font="黑体")
    for text in payload.get("discussion") or ["结果仅描述本次样本中的统计关系，问卷横断设计不能据此作因果结论。"]:
        _paragraph(doc, text, indent=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)


def _freq_groups(rows: list[dict], labels: dict, variables: list[str]) -> list[tuple[str, list[dict]]]:
    grouped: list[tuple[str, list[dict]]] = []
    index: dict[str, list[dict]] = {}
    single = _label(labels, variables[0]) if len(variables) == 1 else ""
    for row in rows:
        variable = row.get("variable") or ""
        parts = [_label(labels, part) for part in row.get("labels") or ()]
        if variable:
            name = _label(labels, variable)
            category = " / ".join(parts)
        elif single:
            name = single
            category = " / ".join(parts)
        elif len(parts) >= 2:
            name = parts[0]
            category = " / ".join(parts[1:])
        else:
            name = "类别"
            category = " / ".join(parts)
        if name not in index:
            index[name] = []
            grouped.append((name, index[name]))
        index[name].append({"category": category, "n": row.get("n"), "percent": row.get("percent")})
    return grouped


def _write_frequencies(doc, section_data, labels) -> None:
    _paragraph(doc, _plain_heading(section_data.get("heading"), "基本资料"), bold=True, size=12, font="黑体")
    rows = section_data.get("rows") or []
    if not rows:
        _missing(doc, "频数表")
        return
    groups = _freq_groups(rows, labels, section_data.get("vars") or [])
    body = []
    sentences = []
    sample_n = None
    for name, items in groups:
        total = sum(item["n"] or 0 for item in items)
        if sample_n is None and total:
            sample_n = total
        bits = []
        for offset, item in enumerate(items):
            body.append([
                name if offset == 0 else "",
                item["category"],
                fmt_stat(item.get("n"), 0),
                fmt_stat(item.get("percent"), 2),
            ])
            bits.append(f"{item['category']}{fmt_stat(item.get('n'), 0)}例（{fmt_stat(item.get('percent'), 2)}%）")
        sentences.append(f"{name}中，" + "，".join(bits))
    lead = f"有效样本{fmt_stat(sample_n, 0)}例。" if sample_n else ""
    _paragraph(doc, lead + "".join(sentence + "。" for sentence in sentences) + "详见表。", indent=True)
    _table(
        doc,
        ["项目", "分类", "例数", "构成比（%）"],
        body,
        caption=_next_caption(doc, "基本资料", sample_n),
        weights=[3, 3, 2, 2],
    )


def _write_descriptives(doc, section_data, labels) -> None:
    _paragraph(doc, _plain_heading(section_data.get("heading"), "描述统计"), bold=True, size=12, font="黑体")
    rows = section_data.get("rows") or []
    if not rows:
        _missing(doc, "描述统计表")
        return
    bits = [f"{_label(labels, row['name'])}为 {_msd(row.get('mean'), row.get('sd'))}" for row in rows]
    sample_n = rows[0].get("n") if all(row.get("n") == rows[0].get("n") for row in rows) else None
    _paragraph(doc, "得分方面，" + "，".join(bits) + "。详见表。", indent=True)
    body = [[_label(labels, row["name"]), _msd(row.get("mean"), row.get("sd"))] for row in rows]
    _table(
        doc,
        ["项目", "得分（M±SD）"],
        body,
        caption=_next_caption(doc, "描述统计", sample_n),
        weights=[3, 2],
    )


def _item_table(doc, title: str, items: list[dict], labels: dict) -> None:
    if not items or len(items) > 15:
        return
    body = [
        [_label(labels, item["name"]), fmt_stat(item.get("citc"), 3), fmt_stat(item.get("alpha_if_deleted"), 3)]
        for item in items
    ]
    _table(doc, ["题项", "CITC", "删除后 α"], body, caption=_next_caption(doc, f"{title}的题项"), weights=[3, 2, 2])


def _write_reliability_group(doc, sections: list[dict], labels: dict) -> None:
    titled = []
    for section_data in sections:
        result = section_data.get("result") or {}
        title = _label(labels, section_data.get("scale") or "量表")
        titled.append((title, result))
    heading = "信度" if len(sections) > 1 else _plain_heading(sections[0].get("heading"), f"{titled[0][0]}的信度")
    _paragraph(doc, heading, bold=True, size=12, font="黑体")
    ready = [(title, result) for title, result in titled if result.get("alpha") is not None]
    if not ready:
        _missing(doc, "信度表")
        return
    bits = [f"{title}包含 {fmt_stat(result.get('n_items'), 0)} 个题项，Cronbach's α 为 {fmt_stat(result.get('alpha'), 3)}" for title, result in ready]
    _paragraph(doc, "；".join(bits) + "。详见表。", indent=True)
    if len(ready) > 1:
        body = [[title, fmt_stat(result.get("n_items"), 0), fmt_stat(result.get("alpha"), 3)] for title, result in ready]
        _table(doc, ["量表", "题项数", "Cronbach's α"], body, caption=_next_caption(doc, "信度"), weights=[3, 2, 2])
    for title, result in ready:
        _item_table(doc, title, result.get("items") or [], labels)


def _write_correlation(doc, section_data, labels) -> None:
    _paragraph(doc, _plain_heading(section_data.get("heading"), "相关分析"), bold=True, size=12, font="黑体")
    pairs = section_data.get("pairs") or []
    if not pairs:
        _missing(doc, "相关矩阵")
        return
    coefficient = "ρ" if section_data.get("kind") == "spearman" else "r"
    body = []
    sentences = []
    for pair in pairs:
        body.append([
            _label(labels, pair["x"]),
            _label(labels, pair["y"]),
            fmt_stat(pair.get("r"), 3) + stars(pair.get("p")),
            fmt_p(pair.get("p")),
            fmt_stat(pair.get("n"), 0),
        ])
        if pair.get("r") is None or pair.get("p") is None:
            continue
        direction = "正" if pair["r"] > 0 else "负"
        flag = "显著" if pair["p"] < 0.05 else "不显著"
        sentences.append(
            f"{_label(labels, pair['x'])}与{_label(labels, pair['y'])}呈{direction}相关，{coefficient}={fmt_stat(pair['r'], 3)}，{p_phrase(pair['p'])}，该相关{flag}。"
        )
    _paragraph(doc, "各变量之间的相关系数见表。", indent=True)
    _table(
        doc,
        ["变量1", "变量2", coefficient, "P", "n"],
        body,
        caption=_next_caption(doc, "相关分析"),
        footnote=_star_note(body),
        weights=[3, 3, 2, 2, 2],
    )
    for sentence in sentences:
        _paragraph(doc, sentence, indent=True)


def _coef_name(name: str, labels: dict) -> str:
    if name == "(Constant)":
        return "常量"
    return _label(labels, name)


def _regression_table(doc: Document, model: dict, labels: dict, caption: str) -> None:
    body = []
    for coef in model.get("coefficients") or []:
        body.append([
            _coef_name(coef["name"], labels),
            fmt_stat(coef.get("B"), 3),
            fmt_stat(coef.get("se"), 3),
            fmt_stat(coef.get("beta"), 3) if coef.get("beta") is not None else "",
            fmt_stat(coef.get("t"), 3),
            fmt_p(coef.get("p")),
        ])
    p_text = "P<0.001" if model.get("p") is not None and model["p"] < 0.001 else f"P={fmt_p(model.get('p'))}"
    note = (
        f"注：R²={fmt_stat(model.get('r2'), 3)}，调整后的R²={fmt_stat(model.get('adj_r2'), 3)}，"
        f"F={fmt_stat(model.get('F'), 3)}，{p_text}。"
    )
    _table(
        doc,
        [],
        body,
        caption=caption,
        footnote=note,
        weights=[4, 2, 2, 2, 2, 2],
        header_matrix=[
            ["", "未标准化系数", "", "标准化系数", "t", "P"],
            ["", "B", "标准误", "β", "t", "P"],
        ],
        h_merges=[(0, 1, 2)],
    )


def _model_sentence(model: dict) -> str:
    if not model or model.get("r2") is None:
        return "该模型的拟合指标未能从输出中读出。"
    return (
        f"模型 R²={fmt_stat(model.get('r2'), 3)}，调整 R²={fmt_stat(model.get('adj_r2'), 3)}，"
        f"F({fmt_stat(model.get('df_model'), 0)}, {fmt_stat(model.get('df_resid'), 0)})={fmt_stat(model.get('F'), 2)}，"
        f"{p_phrase(model.get('p'))}。"
    )


def _write_regression(doc, section_data, labels) -> None:
    _paragraph(doc, _plain_heading(section_data.get("heading"), "回归分析"), bold=True, size=12, font="黑体")
    models = section_data.get("models") or []
    if not models:
        _missing(doc, "回归模型表")
        return
    dependent = _label(labels, section_data.get("dependent") or "因变量")
    last = models[-1]
    significant = [
        _coef_name(coef["name"], labels)
        for coef in last.get("coefficients") or []
        if coef["name"] != "(Constant)" and coef.get("p") is not None and coef["p"] < 0.05
    ]
    explained = ""
    if last.get("adj_r2") is not None:
        explained = f"上述变量能解释{dependent}总变异的 {fmt_stat(last['adj_r2'] * 100, 1)}%。"
    who = "、".join(significant) if significant else "纳入的自变量"
    flag = "有影响（p<0.05）" if significant else "均未达到 0.05"
    _paragraph(doc, f"以{dependent}为因变量。" + (f"{who}对{dependent}{flag}。" if significant else f"纳入的自变量{flag}。") + explained + "详见表。", indent=True)
    for model in models:
        if model.get("delta_r2") is not None and str(model.get("model")) != "1":
            _paragraph(
                doc,
                f"模型{model.get('model')}相对上一层 ΔR²={fmt_stat(model.get('delta_r2'), 3)}，"
                f"ΔF={fmt_stat(model.get('delta_f'), 2)}，{p_phrase(model.get('delta_p'))}。",
                indent=True,
            )
    _regression_table(doc, last, labels, _next_caption(doc, f"{dependent}的回归分析"))
    high_vif = [coef for coef in last.get("coefficients") or [] if coef.get("vif") is not None and coef["vif"] > 5 and coef["name"] != "(Constant)"]
    if high_vif:
        names = "、".join(_coef_name(coef["name"], labels) for coef in high_vif)
        _paragraph(doc, f"{names}的 VIF 大于 5，解释回归系数时需要考虑共线性。", indent=True)
    elif any(coef.get("vif") is not None for coef in last.get("coefficients") or []):
        _paragraph(doc, "各自变量的 VIF 均未超过 5。", indent=True)


def _comparison_factors(sections: list[dict], labels: dict) -> dict[str, list[dict]]:
    by_outcome: dict[str, list[dict]] = {}
    for section_data in sections:
        if section_data["kind"] == "ttest":
            factor = _label(labels, section_data.get("group") or "分组")
            for result in section_data.get("results") or []:
                outcome = result.get("outcome") or ""
                by_outcome.setdefault(outcome, []).append({
                    "name": factor,
                    "stat": fmt_stat(result.get("t"), 3),
                    "p": result.get("p"),
                    "groups": result.get("groups") or [],
                    "unequal": result.get("equal_var") is False,
                    "df": result.get("df"),
                })
        else:
            factor = _label(labels, section_data.get("factor") or "分组")
            for result in section_data.get("results") or []:
                outcome = result.get("outcome") or (section_data.get("outcomes") or [""])[0]
                by_outcome.setdefault(outcome, []).append({
                    "name": factor,
                    "stat": fmt_stat(result.get("F"), 3),
                    "p": result.get("p"),
                    "groups": result.get("groups") or [],
                    "unequal": result.get("levene_p") is not None and result["levene_p"] < 0.05,
                    "df": None,
                    "pairs": section_data.get("pairs") or [],
                })
    return by_outcome


def _write_comparisons(doc, sections: list[dict], labels: dict) -> None:
    _paragraph(doc, "单因素分析", bold=True, size=12, font="黑体")
    by_outcome = _comparison_factors(sections, labels)
    if not by_outcome:
        _missing(doc, "组间比较")
        return
    for outcome, factors in by_outcome.items():
        outcome_label = _label(labels, outcome) if outcome else "因变量"
        significant = [item["name"] for item in factors if item.get("p") is not None and item["p"] < 0.05]
        quiet = [item["name"] for item in factors if item.get("p") is not None and item["p"] >= 0.05]
        text = f"{outcome_label}的单因素分析显示"
        if significant:
            text += f"，在{'、'.join(significant)}上的差异有统计学意义（p<0.05）"
        if quiet:
            text += f"，在{'、'.join(quiet)}上的差异无统计学意义（p>0.05）"
        text += "。详见表。"
        _paragraph(doc, text, indent=True)
        unequal = [item["name"] for item in factors if item.get("unequal")]
        if unequal:
            _paragraph(doc, f"{'、'.join(unequal)}的方差不齐，两组比较采用校正自由度的 t 值。", indent=True)
        body = []
        sample_n = None
        for item in factors:
            groups = item["groups"]
            if not groups:
                body.append([item["name"], "—", "—", item["stat"], fmt_p(item.get("p"))])
                continue
            for offset, group in enumerate(groups):
                if sample_n is None and group.get("n") is not None:
                    sample_n = sum(entry.get("n") or 0 for entry in groups) or group.get("n")
                body.append([
                    item["name"] if offset == 0 else "",
                    str(group.get("group") or ""),
                    _msd(group.get("mean"), group.get("sd")),
                    item["stat"] if offset == 0 else "",
                    fmt_p(item.get("p")) if offset == 0 else "",
                ])
        _table(
            doc,
            ["项目", "分类", f"{outcome_label}（M±SD）", "t/F", "P"],
            body,
            caption=_next_caption(doc, f"{outcome_label}的单因素分析", sample_n),
            weights=[3, 3, 3, 2, 2],
        )
        shown = []
        seen = set()
        for item in factors:
            if item.get("p") is None or item["p"] >= 0.05:
                continue
            for pair in item.get("pairs") or []:
                if pair.get("p") is None or pair["p"] >= 0.05:
                    continue
                labels_pair = pair.get("labels") or []
                key = tuple(sorted(labels_pair[-2:]))
                if len(key) < 2 or key in seen:
                    continue
                seen.add(key)
                shown.append(f"{key[0]}与{key[1]}（{p_phrase(pair['p'])}）")
        if shown:
            _paragraph(doc, "事后比较中 p<0.05 的组合有：" + "；".join(shown[:8]) + "。", indent=True)


def _mediators(section_data) -> list[str]:
    raw = section_data.get("m")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def _write_mediation(doc, section_data, labels) -> None:
    if section_data.get("structure") == "serial":
        _write_serial(doc, section_data, labels)
        return
    result = section_data.get("result") or {}
    paths = result.get("paths") or []
    _paragraph(doc, section_data.get("heading") or "中介效应", bold=True, size=12, font="黑体")
    mediators = _mediators(section_data)
    if not paths or all(path.get("indirect") is None for path in paths):
        _missing(doc, "中介路径系数")
        return
    x = _label(labels, section_data["x"])
    y = _label(labels, section_data["y"])
    if len(mediators) <= 1:
        path = paths[0]
        m = _label(labels, mediators[0] if mediators else path.get("m"))
        _paragraph(
            doc,
            f"以{x}为自变量、{m}为中介变量、{y}为因变量。本机 SPSS 未安装 Hayes PROCESS，因此没有估计 Bootstrap 5000 次的间接效应置信区间。"
            f"路径 a 的 B = {fmt_stat((path.get('a') or {}).get('B'), 3)}，"
            f"{p_phrase((path.get('a') or {}).get('p'))}；路径 b 的 B = {fmt_stat((path.get('b') or {}).get('B'), 3)}，"
            f"{p_phrase((path.get('b') or {}).get('p'))}。总效应 c 的 B = {fmt_stat((result.get('c') or {}).get('B'), 3)}，"
            f"直接效应 c′ 的 B = {fmt_stat((result.get('c_prime') or {}).get('B'), 3)}。"
            f"间接效应 ab = {fmt_stat(path.get('indirect'), 3)}，Sobel z = {fmt_stat(path.get('z'), 2)}，{p_phrase(path.get('p'))}。"
            "该检验不是 Bootstrap 置信区间。",
            indent=True,
        )
        return
    names = "、".join(_label(labels, name) for name in mediators)
    _paragraph(
        doc,
        f"以{x}为自变量、{names}为并行中介、{y}为因变量。每个中介先单独回归到自变量和控制变量，因变量再同时回归到自变量、全部中介和控制变量。"
        "下表是各条特定间接效应的 Sobel 检验。这些间接效应没有加总后再检验，也没有 Bootstrap 置信区间。",
        indent=True,
    )
    body = []
    for path in paths:
        body.append([
            _label(labels, path.get("m")),
            fmt_stat((path.get("a") or {}).get("B"), 3),
            fmt_stat((path.get("b") or {}).get("B"), 3),
            fmt_stat(path.get("indirect"), 3),
            fmt_stat(path.get("z"), 2),
            fmt_p(path.get("p")) + stars(path.get("p")),
        ])
    _table(doc, ["中介变量", "a", "b", "ab", "Sobel z", "P"], body, caption=_next_caption(doc, "中介效应"), footnote=_star_note(body))
    _paragraph(
        doc,
        f"总效应 c 的 B = {fmt_stat((result.get('c') or {}).get('B'), 3)}，"
        f"{p_phrase((result.get('c') or {}).get('p'))}；直接效应 c′ 的 B = {fmt_stat((result.get('c_prime') or {}).get('B'), 3)}，"
        f"{p_phrase((result.get('c_prime') or {}).get('p'))}。",
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


def _write_serial(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    paths = result.get("paths") or []
    _paragraph(doc, section_data.get("heading") or "链式中介", bold=True, size=12, font="黑体")
    mediators = _mediators(section_data)
    if not paths or all(path.get("indirect") is None for path in paths):
        _missing(doc, "链式中介的路径系数")
        return
    x = _label(labels, section_data["x"])
    y = _label(labels, section_data["y"])
    order = " → ".join(_label(labels, name) for name in mediators)
    _paragraph(
        doc,
        f"以{x}为自变量、{y}为因变量，中介顺序为{order}。前一个中介进入后一个中介的方程。每条特定间接效应单独做系数乘积的 Sobel 检验，不加总，也没有 Bootstrap 置信区间。",
        indent=True,
    )
    body = []
    for path in paths:
        route = " → ".join([x, *[_label(labels, name) for name in path.get("mediators") or []], y])
        body.append([
            route,
            fmt_stat(path.get("indirect"), 3),
            fmt_stat(path.get("z"), 2),
            fmt_p(path.get("p")) + stars(path.get("p")),
        ])
    _table(doc, ["路径", "间接效应", "Sobel z", "P"], body, caption=_next_caption(doc, "链式中介"), footnote=_star_note(body))
    _paragraph(
        doc,
        f"总效应 c 的 B = {fmt_stat((result.get('c') or {}).get('B'), 3)}，{p_phrase((result.get('c') or {}).get('p'))}；"
        f"直接效应 c′ 的 B = {fmt_stat((result.get('c_prime') or {}).get('B'), 3)}，{p_phrase((result.get('c_prime') or {}).get('p'))}。",
        indent=True,
    )


def _write_moderation(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "调节效应", bold=True, size=12, font="黑体")
    if section_data.get("groups"):
        main = section_data.get("main") or []
        if not main:
            _missing(doc, "调节模型")
            return
        last = main[-1]
        _paragraph(doc, "多个调节变量同时进入模型，只估计各自与自变量的二阶交互。" + _model_sentence(last), indent=True)
        for group in section_data["groups"]:
            coef = next((item for item in last.get("coefficients") or [] if item["name"] == group.get("interaction")), None)
            moderator = _label(labels, group.get("name"))
            if coef:
                _paragraph(
                    doc,
                    f"{_label(labels, section_data['x'])} × {moderator} 的 B = {fmt_stat(coef.get('B'), 3)}，"
                    f"t = {fmt_stat(coef.get('t'), 2)}，{p_phrase(coef.get('p'))}。",
                    indent=True,
                )
            else:
                _missing(doc, f"{moderator}的交互项系数")
            _paragraph(doc, _slope_sentence(f"{moderator}高于自身均值一个标准差且其余调节变量取均值", group.get("high") or {}, group.get("slope_var") or "", labels), indent=True)
            _paragraph(doc, _slope_sentence(f"{moderator}低于自身均值一个标准差且其余调节变量取均值", group.get("low") or {}, group.get("slope_var") or "", labels), indent=True)
        _regression_table(doc, last, labels, _next_caption(doc, "调节效应"))
        return
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
            f"β = {fmt_stat(coef.get('beta'), 3)}，t = {fmt_stat(coef.get('t'), 2)}，{p_phrase(coef.get('p'))}。",
            indent=True,
        )
    else:
        _missing(doc, "交互项系数")
    _paragraph(doc, _slope_sentence("调节变量高于均值一个标准差", section_data.get("high") or {}, section_data.get("slope_var") or "", labels), indent=True)
    _paragraph(doc, _slope_sentence("调节变量低于均值一个标准差", section_data.get("low") or {}, section_data.get("slope_var") or "", labels), indent=True)
    _regression_table(doc, last, labels, _next_caption(doc, "调节效应"))


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
            caption=_next_caption(doc, "因子载荷"),
            footnote="注：单元格为旋转后的因子载荷。",
        )
    elif result.get("kmo") is not None:
        _paragraph(doc, "未从 OMS 读到旋转载荷表，因此这里不列因子载荷。", indent=True)


def _write_moderated_mediation(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "有调节的中介", bold=True, size=12, font="黑体")
    levels = result.get("levels") or []
    if not levels or all(level.get("indirect") is None for level in levels):
        _missing(doc, "条件间接效应")
        return
    stage = section_data.get("stage")
    stage_text = {"a": "前半路径", "b": "后半路径", "both": "前半路径和后半路径"}.get(stage, "指定路径")
    _paragraph(
        doc,
        f"以{_label(labels, section_data['x'])}为自变量、{_label(labels, section_data['m'])}为中介、{_label(labels, section_data['y'])}为因变量，"
        f"{_label(labels, section_data['w'])}调节{stage_text}。条件间接效应取调节变量的均值和均值上下一个标准差，并用 Sobel 公式检验。没有 Bootstrap 置信区间。",
        indent=True,
    )
    body = []
    for level in levels:
        body.append([
            level.get("level") or "",
            fmt_stat((level.get("a") or {}).get("B"), 3),
            fmt_stat((level.get("b") or {}).get("B"), 3),
            fmt_stat(level.get("indirect"), 3),
            fmt_stat(level.get("z"), 2),
            fmt_p(level.get("p")) + stars(level.get("p")),
        ])
    _table(doc, ["调节变量水平", "a", "b", "条件间接效应", "Sobel z", "P"], body, caption=_next_caption(doc, "条件间接效应"), footnote=_star_note(body))
    for key, text in (("interaction_a", "前半路径交互项"), ("interaction_b", "后半路径交互项")):
        coef = result.get(key)
        if coef:
            _paragraph(doc, f"{text}的 B = {fmt_stat(coef.get('B'), 3)}，t = {fmt_stat(coef.get('t'), 2)}，{p_phrase(coef.get('p'))}。", indent=True)
    index = result.get("index")
    if index and index.get("indirect") is not None:
        _paragraph(
            doc,
            f"调节中介指数为 {fmt_stat(index.get('indirect'), 3)}，Sobel z = {fmt_stat(index.get('z'), 2)}，{p_phrase(index.get('p'))}。指数只说明间接效应是否随调节变量变化。",
            indent=True,
        )
    _paragraph(
        doc,
        f"总效应 c 的 B = {fmt_stat((result.get('c') or {}).get('B'), 3)}，{p_phrase((result.get('c') or {}).get('p'))}；"
        f"直接效应 c′ 的 B = {fmt_stat((result.get('c_prime') or {}).get('B'), 3)}，{p_phrase((result.get('c_prime') or {}).get('p'))}。",
        indent=True,
    )


def _write_chisq(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "卡方检验", bold=True, size=12, font="黑体")
    if result.get("chi2") is None:
        _missing(doc, "卡方检验")
        return
    _paragraph(
        doc,
        f"{_label(labels, section_data.get('row'))}与{_label(labels, section_data.get('col'))}的 Pearson χ²({fmt_stat(result.get('df'), 0)}) = {fmt_stat(result.get('chi2'), 2)}，"
        f"{p_phrase(result.get('p'))}，有效个案 {fmt_stat(result.get('n'), 0)}。这里不改写成 Fisher 精确检验。",
        indent=True,
    )
    counts = result.get("counts") or []
    columns = []
    for item in counts:
        if item["col"] not in columns:
            columns.append(item["col"])
    row_names = []
    for item in counts:
        if item["row"] not in row_names:
            row_names.append(item["row"])
    if columns and row_names:
        lookup = {(item["row"], item["col"]): item["n"] for item in counts}
        row_values = section_data.get("row_values") or {}
        col_values = section_data.get("col_values") or {}
        body = [[_coded(row_values, row)] + [fmt_stat(lookup.get((row, col)), 0) for col in columns] for row in row_names]
        _table(doc, [_label(labels, section_data.get("row"))] + [_coded(col_values, col) for col in columns], body, caption=_next_caption(doc, "列联表", result.get("n")))


def _write_mannwhitney(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "Mann-Whitney U 检验", bold=True, size=12, font="黑体")
    results = section_data.get("results") or []
    if not results:
        _missing(doc, "Mann-Whitney U 检验")
        return
    body = []
    for result in results:
        ranks = "；".join(
            f"{_coded(section_data.get('group_values'), group.get('group'))}的平均秩 {fmt_stat(group.get('mean_rank'), 2)}（n = {fmt_stat(group.get('n'), 0)}）"
            for group in result.get("groups") or []
        )
        body.append([
            _label(labels, result.get("outcome")),
            fmt_stat(result.get("u"), 2),
            fmt_stat(result.get("z"), 2),
            fmt_p(result.get("p")) + stars(result.get("p")),
            ranks,
        ])
    _table(doc, ["因变量", "U", "z", "P", "平均秩"], body, caption=_next_caption(doc, "Mann-Whitney U 检验"), footnote=_star_note(body))


def _write_kruskal(doc, section_data, labels) -> None:
    _paragraph(doc, section_data.get("heading") or "Kruskal-Wallis 检验", bold=True, size=12, font="黑体")
    results = section_data.get("results") or []
    if not results:
        _missing(doc, "Kruskal-Wallis 检验")
        return
    body = []
    for result in results:
        ranks = "；".join(
            f"{_coded(section_data.get('group_values'), group.get('group'))}的平均秩 {fmt_stat(group.get('mean_rank'), 2)}"
            for group in result.get("groups") or []
        )
        body.append([
            _label(labels, result.get("outcome")),
            fmt_stat(result.get("h"), 2),
            fmt_stat(result.get("df"), 0),
            fmt_p(result.get("p")) + stars(result.get("p")),
            ranks,
        ])
    _table(doc, ["因变量", "H", "df", "P", "平均秩"], body, caption=_next_caption(doc, "Kruskal-Wallis 检验"), footnote=_star_note(body))


def _write_logistic(doc, section_data, labels) -> None:
    result = section_data.get("result") or {}
    _paragraph(doc, section_data.get("heading") or "二元 logistic 回归", bold=True, size=12, font="黑体")
    if not result.get("coefficients"):
        _missing(doc, "logistic 回归系数")
        return
    _paragraph(
        doc,
        f"因变量为{_label(labels, section_data.get('dependent'))}。模型 χ²({fmt_stat(result.get('df'), 0)}) = {fmt_stat(result.get('chi2'), 2)}，"
        f"{p_phrase(result.get('p'))}。Nagelkerke R² = {fmt_stat(result.get('nagelkerke'), 3)}。",
        indent=True,
    )
    body = []
    for coef in result.get("coefficients") or []:
        body.append([
            _label(labels, coef.get("name")),
            fmt_stat(coef.get("B"), 3),
            fmt_stat(coef.get("se"), 3),
            fmt_stat(coef.get("wald"), 2),
            fmt_p(coef.get("p")) + stars(coef.get("p")),
            fmt_stat(coef.get("exp_b"), 3),
        ])
    _table(doc, ["预测变量", "B", "SE", "Wald", "P", "Exp(B)"], body, caption=_next_caption(doc, "二元 logistic 回归"), footnote=_star_note(body))
