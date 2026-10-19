"""Normalize a confirmed plan and reject models this version cannot estimate."""

from __future__ import annotations

import copy
import re

KNOWN_TYPES = {
    "descriptives",
    "frequencies",
    "reliability",
    "efa",
    "harman",
    "zscreen",
    "correlation",
    "regression",
    "ttest",
    "anova",
    "mediation",
    "moderation",
    "moderated_mediation",
    "spearman",
    "chisq",
    "mannwhitney",
    "kruskal",
    "logistic",
}

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class PlanError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("分析方案还不能运行：\n" + "\n".join(f"- {item}" for item in errors))


def moderator_names(analysis: dict) -> list[str]:
    raw = analysis.get("w")
    if isinstance(raw, str) and raw:
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str) and item]
    return []


def mediator_names(analysis: dict) -> list[str]:
    raw = analysis.get("m")
    if isinstance(raw, str) and raw:
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str) and item]
    return []


def required_input_columns(plan: dict) -> set[str]:
    """Column names that must already exist in a CSV or Excel file."""
    computed = set()
    for scale in plan.get("scales") or []:
        if scale.get("name"):
            computed.add(scale["name"])
        for rev in scale.get("reverse") or []:
            if rev.get("name"):
                computed.add(rev["name"])
    for variable in plan.get("variables") or []:
        if variable.get("generated") and variable.get("name"):
            computed.add(variable["name"])
        for dummy in variable.get("dummies") or []:
            computed.add(dummy["name"])

    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for variable in plan.get("variables") or []:
        if not variable.get("generated") and variable.get("name"):
            found.add(variable["name"])
    for scale in plan.get("scales") or []:
        for rev in scale.get("reverse") or []:
            if rev.get("item"):
                found.add(rev["item"])
        walk(scale.get("items") or [])
    for analysis in plan.get("analyses") or []:
        for key in ("vars", "items", "outcomes", "controls", "blocks", "group", "factor", "dependent", "predictors", "row", "col", "x", "m", "y", "w"):
            if key in analysis:
                walk(analysis[key])
    return {name for name in found if name not in computed}


def prepare_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise PlanError(["分析方案必须是一个 JSON 对象。"])
    errors: list[str] = []
    plan = copy.deepcopy(plan)
    if not isinstance(plan.get("data_file"), str) or not plan["data_file"].strip():
        errors.append("缺少 data_file。")
    analyses = plan.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        errors.append("analyses 至少要包含一项分析。")
        analyses = []
    variables = plan.get("variables") or []
    if not isinstance(variables, list):
        errors.append("variables 必须是数组。")
        variables = []
        plan["variables"] = variables
    scales = plan.get("scales") or []
    if not isinstance(scales, list):
        errors.append("scales 必须是数组。")
        scales = []
        plan["scales"] = scales

    reverse_map: dict[str, str] = {}
    generated: list[dict] = []
    for scale in scales:
        if not isinstance(scale, dict) or not isinstance(scale.get("name"), str) or not scale["name"]:
            errors.append("每个量表都要有 name。")
            continue
        items = _names(scale.get("items"))
        if items is None:
            errors.append(f"量表 {scale['name']} 的 items 必须是非空变量名数组。")
            continue
        for rev in scale.get("reverse") or []:
            if not isinstance(rev, dict) or not isinstance(rev.get("item"), str) or not rev["item"]:
                errors.append(f"量表 {scale['name']} 的反向题缺少 item。")
                continue
            if rev["item"] not in items:
                errors.append(f"反向题 {rev['item']} 不在量表 {scale['name']} 的题项里。")
            low = _number(rev.get("low"), f"反向题 {rev['item']} 的 low", errors)
            high = _number(rev.get("high"), f"反向题 {rev['item']} 的 high", errors)
            if low is not None and high is not None and float(high) <= float(low):
                errors.append(f"反向题 {rev['item']} 的 high 必须大于 low。")
            dest = f"{rev['item']}_r"
            if dest in items or dest in reverse_map.values():
                errors.append(f"反向计分后的变量名 {dest} 与已有题项重复。")
            rev["name"] = dest
            if low is not None:
                rev["low"] = low
            if high is not None:
                rev["high"] = high
            reverse_map[rev["item"]] = dest
            generated.append({"name": dest, "label": f"{rev['item']}（反向）", "generated": True})
        scale["items"] = [reverse_map.get(item, item) for item in items]

    dummy_parents: dict[str, list[str]] = {}
    for variable in variables:
        if not isinstance(variable, dict) or not isinstance(variable.get("name"), str) or not variable["name"]:
            errors.append("每个变量都要有 name。")
            continue
        if variable.get("coding") != "dummy":
            continue
        values = {str(key): label for key, label in (variable.get("values") or {}).items()}
        if len(values) < 2:
            errors.append(f"{variable['name']} 设为虚拟变量时，values 至少要有两个取值。")
            continue
        reference = variable.get("reference")
        if reference is None:
            errors.append(f"{variable['name']} 设为虚拟变量时要写 reference，作为参照组编码。")
            continue
        reference = str(reference)
        if reference not in values:
            errors.append(f"{variable['name']} 的 reference 不在 values 里。")
            continue
        variable["reference_label"] = str(values[reference])
        dummies = []
        for code, label in values.items():
            if code == reference:
                continue
            literal = _number(code, f"{variable['name']} 的取值 {code}", errors)
            if literal is None:
                continue
            token = literal.replace("-", "m").replace(".", "_")
            name = f"{variable['name']}_d{token}"
            text = f"{variable.get('label') or variable['name']}：{label}（参照：{variable['reference_label']}）"
            dummies.append({"name": name, "code": literal, "label": text})
            generated.append({"name": name, "label": text, "generated": True})
        if not dummies:
            errors.append(f"{variable['name']} 除参照组外还要有至少一个取值。")
        variable["dummies"] = dummies
        dummy_parents[variable["name"]] = [item["name"] for item in dummies]

    taken = {item["name"] for item in generated}
    for variable in variables:
        name = variable.get("name")
        if name in taken and not variable.get("generated"):
            errors.append(f"生成的变量名 {name} 与方案里的变量重复。")
    plan["variables"] = [*variables, *generated]

    def expand(names: list[str]) -> list[str]:
        expanded: list[str] = []
        for name in names:
            pieces = dummy_parents.get(name) or [reverse_map.get(name, name)]
            for piece in pieces:
                if piece not in expanded:
                    expanded.append(piece)
        return expanded

    def substitute(names: list[str]) -> list[str]:
        return [reverse_map.get(name, name) for name in names]

    for index, analysis in enumerate(analyses, start=1):
        if not isinstance(analysis, dict) or not analysis.get("type"):
            errors.append(f"第 {index} 项分析缺少 type。")
            continue
        kind = analysis["type"]
        prefix = f"第 {index} 项 {kind}"
        if kind not in KNOWN_TYPES:
            errors.append(f"{prefix} 还不能做。可做的类型见分析方案说明。")
            continue
        if kind in {"descriptives", "frequencies", "correlation", "spearman", "zscreen"}:
            names = _names(analysis.get("vars"))
            if names is None:
                errors.append(f"{prefix} 需要非空的 vars。")
            elif kind != "frequencies":
                analysis["vars"] = expand(names)
        elif kind in {"reliability", "efa", "harman"}:
            names = _names(analysis.get("items"))
            if names is None:
                errors.append(f"{prefix} 需要非空的 items。")
            else:
                analysis["items"] = substitute(names)
            if kind == "reliability" and not analysis.get("scale"):
                errors.append(f"{prefix} 需要 scale。")
        elif kind == "regression":
            dependent = analysis.get("dependent")
            if not isinstance(dependent, str) or not dependent:
                errors.append(f"{prefix} 需要 dependent。")
            elif dependent in dummy_parents:
                errors.append(f"{prefix} 的因变量 {dependent} 是分类变量，不能直接作为连续因变量。")
            blocks = analysis.get("blocks")
            if not isinstance(blocks, list) or not blocks:
                errors.append(f"{prefix} 需要 blocks。")
            else:
                previous: list[str] | None = None
                expanded_blocks = []
                for layer, block in enumerate(blocks, start=1):
                    names = _names(block)
                    if names is None:
                        errors.append(f"{prefix} 的第 {layer} 层必须是非空变量名数组。")
                        continue
                    if previous is not None:
                        missing = [name for name in previous if name not in names]
                        if missing:
                            errors.append(f"{prefix} 的第 {layer} 层必须包含上一层变量：{'、'.join(missing)}。")
                    previous = names
                    expanded_blocks.append(expand(names))
                analysis["blocks"] = expanded_blocks
        elif kind == "ttest":
            if not isinstance(analysis.get("group"), str) or not analysis["group"]:
                errors.append(f"{prefix} 需要 group。")
            codes = analysis.get("codes") or [1, 2]
            if not isinstance(codes, list) or len(codes) != 2:
                errors.append(f"{prefix} 的 codes 必须是两个分组取值。")
            outcomes = _names(analysis.get("outcomes"))
            if outcomes is None:
                errors.append(f"{prefix} 需要非空的 outcomes。")
            else:
                blocked = [name for name in outcomes if name in dummy_parents]
                if blocked:
                    errors.append(f"{prefix} 的结果变量 {'、'.join(blocked)} 已设为虚拟变量，不能作为 t 检验的结果。")
        elif kind == "anova":
            if not isinstance(analysis.get("factor"), str) or not analysis["factor"]:
                errors.append(f"{prefix} 需要 factor。")
            outcomes = _names(analysis.get("outcomes"))
            if outcomes is None:
                errors.append(f"{prefix} 需要非空的 outcomes。")
            else:
                blocked = [name for name in outcomes if name in dummy_parents]
                if blocked:
                    errors.append(f"{prefix} 的结果变量 {'、'.join(blocked)} 已设为虚拟变量，不能作为方差分析的结果。")
        elif kind == "chisq":
            for role in ("row", "col"):
                if not isinstance(analysis.get(role), str) or not analysis[role]:
                    errors.append(f"{prefix} 需要 {role}。")
        elif kind == "mannwhitney":
            if not isinstance(analysis.get("group"), str) or not analysis["group"]:
                errors.append(f"{prefix} 需要 group。")
            codes = analysis.get("codes") or [1, 2]
            if not isinstance(codes, list) or len(codes) != 2:
                errors.append(f"{prefix} 的 codes 必须是两个分组取值。")
            outcomes = _names(analysis.get("outcomes"))
            if outcomes is None:
                errors.append(f"{prefix} 需要非空的 outcomes。")
            else:
                blocked = [name for name in outcomes if name in dummy_parents]
                if blocked:
                    errors.append(f"{prefix} 的结果变量 {'、'.join(blocked)} 已设为虚拟变量，不能作为非参数检验的结果。")
        elif kind == "kruskal":
            if not isinstance(analysis.get("factor"), str) or not analysis["factor"]:
                errors.append(f"{prefix} 需要 factor。")
            outcomes = _names(analysis.get("outcomes"))
            if outcomes is None:
                errors.append(f"{prefix} 需要非空的 outcomes。")
            else:
                blocked = [name for name in outcomes if name in dummy_parents]
                if blocked:
                    errors.append(f"{prefix} 的结果变量 {'、'.join(blocked)} 已设为虚拟变量，不能作为非参数检验的结果。")
            _fill_group_range(analysis, variables, prefix, errors)
        elif kind == "logistic":
            dependent = analysis.get("dependent")
            if not isinstance(dependent, str) or not dependent:
                errors.append(f"{prefix} 需要二元因变量 dependent。")
            elif dependent in dummy_parents:
                errors.append(f"{prefix} 的因变量是虚拟变量组。请改用其中一个二分类变量，或直接写原二分类变量。")
            predictors = _names(analysis.get("predictors"))
            if predictors is None:
                errors.append(f"{prefix} 需要非空的 predictors。")
            else:
                analysis["predictors"] = expand(predictors)
        elif kind == "mediation":
            _prepare_mediation(analysis, prefix, dummy_parents, expand, errors)
        elif kind == "moderated_mediation":
            _prepare_moderated_mediation(analysis, prefix, dummy_parents, expand, errors)
        elif kind == "moderation":
            _prepare_moderation(analysis, prefix, dummy_parents, expand, errors)

    if errors:
        raise PlanError(errors)
    return plan


def _prepare_mediation(analysis: dict, prefix: str, dummy_parents: dict[str, list[str]], expand, errors: list[str]) -> None:
    structure = analysis.get("structure") or "parallel"
    if structure not in {"parallel", "serial"}:
        errors.append(f"{prefix} 的 structure 只能是 parallel 或 serial。有调节的中介请用 moderated_mediation。")
    mediators = mediator_names(analysis)
    raw = analysis.get("m")
    if not mediators or (not isinstance(raw, (str, list))):
        errors.append(f"{prefix} 的 m 要写成一个中介变量，或多个中介变量的数组。")
    if len(mediators) != len(set(mediators)):
        errors.append(f"{prefix} 的中介变量有重复。")
    if structure == "serial" and len(mediators) < 2:
        errors.append(f"{prefix} 的链式中介要按先后顺序至少写两个中介变量。")
    if structure == "serial" and len(mediators) > 3:
        errors.append(f"{prefix} 的一条链式中介最多写三个中介变量。")
    for role in ("x", "y"):
        value = analysis.get(role)
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix} 需要 {role}。")
        elif value in dummy_parents:
            errors.append(f"{prefix} 的 {role} 是分类变量。虚拟变量可以放进 controls，不能单独充当这条路径的自变量或因变量。")
    for mediator in mediators:
        if mediator in dummy_parents:
            errors.append(f"{prefix} 的中介变量 {mediator} 是分类变量，不能作为中介。")
        if mediator in {analysis.get("x"), analysis.get("y")}:
            errors.append(f"{prefix} 的中介变量不能与自变量或因变量相同。")
    if len(mediators) == 1:
        analysis["m"] = mediators[0]
    elif mediators:
        analysis["m"] = mediators
    controls = analysis.get("controls") or []
    if controls:
        names = _names(controls)
        if names is None:
            errors.append(f"{prefix} 的 controls 必须是变量名数组。")
        else:
            analysis["controls"] = expand(names)


def _prepare_moderated_mediation(analysis: dict, prefix: str, dummy_parents: dict[str, list[str]], expand, errors: list[str]) -> None:
    if analysis.get("stage") not in {"a", "b", "both"}:
        errors.append(f"{prefix} 要写 stage：a 调节前半路径，b 调节后半路径，both 表示同一调节变量同时调节两段。")
    if not isinstance(analysis.get("m"), str) or not analysis.get("m"):
        errors.append(f"{prefix} 一次只放一个中介变量。多个中介请改用 mediation。")
    if isinstance(analysis.get("w"), list) or not isinstance(analysis.get("w"), str) or not analysis.get("w"):
        errors.append(f"{prefix} 一次只放一个调节变量。")
    for role in ("x", "m", "y", "w"):
        value = analysis.get(role)
        if isinstance(value, str) and value in dummy_parents:
            errors.append(f"{prefix} 的 {role} 是分类变量。虚拟变量可以放进 controls。")
    named = [analysis.get(role) for role in ("x", "m", "y", "w")]
    if all(isinstance(item, str) for item in named) and len(set(named)) < 4:
        errors.append(f"{prefix} 的自变量、中介、因变量和调节变量必须是四个不同变量。")
    controls = analysis.get("controls") or []
    if controls:
        names = _names(controls)
        if names is None:
            errors.append(f"{prefix} 的 controls 必须是变量名数组。")
        else:
            analysis["controls"] = expand(names)


def _prepare_moderation(analysis: dict, prefix: str, dummy_parents: dict[str, list[str]], expand, errors: list[str]) -> None:
    moderators = moderator_names(analysis)
    if not moderators:
        errors.append(f"{prefix} 需要 w。多个调节变量写成数组，只估计各自的二阶交互。")
    if len(moderators) != len(set(moderators)):
        errors.append(f"{prefix} 的调节变量有重复。")
    if len(moderators) > 3:
        errors.append(f"{prefix} 一次最多放三个调节变量。")
    for moderator in moderators:
        if moderator in dummy_parents:
            errors.append(f"{prefix} 的调节变量 {moderator} 是分类变量。虚拟变量可以放进 controls。")
        if moderator in {analysis.get("x"), analysis.get("y")}:
            errors.append(f"{prefix} 的调节变量不能与自变量或因变量相同。")
    for role in ("x", "y"):
        value = analysis.get(role)
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix} 需要 {role}。")
        elif value in dummy_parents:
            errors.append(f"{prefix} 的 {role} 是分类变量。虚拟变量可以放进 controls，不能作为调节模型里的自变量或因变量。")
    if len(moderators) == 1:
        analysis["w"] = moderators[0]
    elif moderators:
        analysis["w"] = moderators
    controls = analysis.get("controls") or []
    if controls:
        names = _names(controls)
        if names is None:
            errors.append(f"{prefix} 的 controls 必须是变量名数组。")
        else:
            analysis["controls"] = expand(names)


def _fill_group_range(analysis: dict, variables: list[dict], prefix: str, errors: list[str]) -> None:
    codes = analysis.get("codes")
    if isinstance(codes, list) and len(codes) == 2:
        return
    factor = analysis.get("factor")
    variable = next((item for item in variables if item.get("name") == factor), None)
    values = (variable or {}).get("values") or {}
    numeric = []
    for key in values:
        literal = _number(key, f"{prefix} 的分组取值 {key}", [])
        if literal is None:
            numeric = []
            break
        numeric.append(literal)
    if len(numeric) < 2:
        errors.append(f"{prefix} 需要 codes，写成分组变量的最小和最大取值，例如 [1, 3]。")
        return
    analysis["codes"] = [min(numeric, key=float), max(numeric, key=float)]


def _names(value) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    names = []
    for item in value:
        if not isinstance(item, str) or not item:
            return None
        names.append(item)
    return names


def _number(value, what: str, errors: list[str]) -> str | None:
    if isinstance(value, bool) or value is None:
        errors.append(f"{what}必须是数字。")
        return None
    text = str(value).strip()
    if not _NUMBER.fullmatch(text):
        errors.append(f"{what}必须是数字。")
        return None
    if "." not in text:
        return str(int(text))
    return text
