"""Turn OMS cells into the statistics the report is allowed to quote."""

from __future__ import annotations

import math

from spss_agent.oms import Cell, lookup, tables_of


def cohen_d(groups: list[dict]) -> float | None:
    if len(groups) != 2:
        return None
    first, second = groups
    n1, n2 = first.get("n"), second.get("n")
    s1, s2 = first.get("sd"), second.get("sd")
    m1, m2 = first.get("mean"), second.get("mean")
    if None in (n1, n2, s1, s2, m1, m2) or n1 + n2 <= 2:
        return None
    pooled = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2))
    if pooled == 0:
        return None
    return (m1 - m2) / pooled


def _models(cells: list[Cell]) -> list[str]:
    found: list[str] = []
    for cell in cells:
        if cell.table == "Model Summary" and cell.row and cell.row[0] not in found:
            found.append(cell.row[0])
    return found


def regression_models(cells: list[Cell]) -> list[dict]:
    models = []
    for model_id in _models(cells):
        row = (model_id,)
        anova_reg = (model_id, "Regression")
        anova_res = (model_id, "Residual")
        predictors = []
        names = []
        for cell in cells:
            if cell.table != "Coefficients" or not cell.row or cell.row[0] != model_id or len(cell.row) < 2:
                continue
            name = cell.row[1]
            if name not in {"B", "Std. Error", "Beta", "t", "Sig.", "Tolerance", "VIF"} and name not in names:
                names.append(name)
        for name in names:
            key = (model_id, name)
            predictors.append(
                {
                    "name": name,
                    "B": lookup(cells, "Coefficients", key + ("B",)),
                    "se": lookup(cells, "Coefficients", key + ("Std. Error",)),
                    "beta": lookup(cells, "Coefficients", key + ("Beta",)),
                    "t": lookup(cells, "Coefficients", key + ("t",)),
                    "p": lookup(cells, "Coefficients", key + ("Sig.",)),
                    "tolerance": lookup(cells, "Coefficients", key + ("Tolerance",)),
                    "vif": lookup(cells, "Coefficients", key + ("VIF",)),
                }
            )
        models.append(
            {
                "model": model_id,
                "r": lookup(cells, "Model Summary", row + ("R",)),
                "r2": lookup(cells, "Model Summary", row + ("R Square",)),
                "adj_r2": lookup(cells, "Model Summary", row + ("Adjusted R Square",)),
                "delta_r2": lookup(cells, "Model Summary", row + ("R Square Change",)),
                "delta_f": lookup(cells, "Model Summary", row + ("F Change",)),
                "df1": lookup(cells, "Model Summary", row + ("df1",)),
                "df2": lookup(cells, "Model Summary", row + ("df2",)),
                "delta_p": lookup(cells, "Model Summary", row + ("Sig. F Change",)),
                "F": lookup(cells, "ANOVA", anova_reg + ("F",)),
                "p": lookup(cells, "ANOVA", anova_reg + ("Sig.",)),
                "df_model": lookup(cells, "ANOVA", anova_reg + ("df",)),
                "df_resid": lookup(cells, "ANOVA", anova_res + ("df",)),
                "coefficients": predictors,
            }
        )
    return models


def reliability(cells: list[Cell]) -> dict:
    alpha = lookup(cells, "Reliability Statistics", ("Cronbach's Alpha",))
    n_items = lookup(cells, "Reliability Statistics", ("N of Items",))
    items = []
    seen: list[str] = []
    for cell in tables_of(cells, "Item Total Statistics"):
        if cell.row and cell.row[0] not in seen:
            seen.append(cell.row[0])
    for name in seen:
        items.append(
            {
                "name": name,
                "citc": lookup(cells, "Item Total Statistics", (name, "Corrected Item-Total Correlation")),
                "alpha_if_deleted": lookup(cells, "Item Total Statistics", (name, "Cronbach's Alpha if Item Deleted")),
            }
        )
    return {"alpha": alpha, "n_items": n_items, "items": items}


_DESC_STATS = {"N", "Mean", "Std. Deviation", "Minimum", "Maximum"}


def descriptives(cells: list[Cell]) -> list[dict]:
    variables: list[str] = []
    for cell in tables_of(cells, "Descriptive Statistics"):
        if not cell.row:
            continue
        name = cell.row[0]
        if name in _DESC_STATS or name.startswith("Valid N"):
            continue
        if name not in variables:
            variables.append(name)
    rows = []
    for name in variables:
        rows.append(
            {
                "name": name,
                "n": lookup(cells, "Descriptive Statistics", (name, "N")),
                "mean": lookup(cells, "Descriptive Statistics", (name, "Mean")),
                "sd": lookup(cells, "Descriptive Statistics", (name, "Std. Deviation")),
                "minimum": lookup(cells, "Descriptive Statistics", (name, "Minimum")),
                "maximum": lookup(cells, "Descriptive Statistics", (name, "Maximum")),
            }
        )
    return rows


def _pair_vars(cell: Cell, statistic: str) -> tuple[str, str] | None:
    labels = [part for part in cell.row + cell.col if part != statistic]
    if len(labels) != 2 or labels[0] == labels[1]:
        return None
    return labels[0], labels[1]


def correlations(cells: list[Cell]) -> list[dict]:
    pairs = []
    seen: set[tuple[str, str]] = set()
    for cell in tables_of(cells, "Correlations"):
        if "Pearson Correlation" not in cell.row + cell.col:
            continue
        found = _pair_vars(cell, "Pearson Correlation")
        if found is None:
            continue
        left, right = found
        key = tuple(sorted((left, right)))
        if key in seen:
            continue
        seen.add(key)
        pairs.append(
            {
                "x": left,
                "y": right,
                "r": cell.number,
                "p": lookup(cells, "Correlations", (left, right, "Sig. (2-tailed)")),
                "n": lookup(cells, "Correlations", (left, right, "N")),
            }
        )
    return pairs


def t_tests(cells: list[Cell]) -> list[dict]:
    outcomes: list[str] = []
    for cell in tables_of(cells, "Independent Samples Test"):
        if cell.row and cell.row[0] not in outcomes:
            outcomes.append(cell.row[0])
    results = []
    for outcome in outcomes:
        levene_p = lookup(
            cells,
            "Independent Samples Test",
            (outcome, "Equal variances assumed", "Levene's Test for Equality of Variances", "Sig."),
        )
        levene_f = lookup(
            cells,
            "Independent Samples Test",
            (outcome, "Equal variances assumed", "Levene's Test for Equality of Variances", "F"),
        )
        branch = "Equal variances not assumed" if levene_p is not None and levene_p < 0.05 else "Equal variances assumed"
        groups = []
        seen: list[str] = []
        for cell in tables_of(cells, "Group Statistics"):
            if len(cell.row) >= 2 and cell.row[0] == outcome and cell.row[1] not in seen:
                seen.append(cell.row[1])
        for group in seen:
            groups.append(
                {
                    "group": group,
                    "n": lookup(cells, "Group Statistics", (outcome, group, "N")),
                    "mean": lookup(cells, "Group Statistics", (outcome, group, "Mean")),
                    "sd": lookup(cells, "Group Statistics", (outcome, group, "Std. Deviation")),
                }
            )
        results.append(
            {
                "outcome": outcome,
                "levene_f": levene_f,
                "levene_p": levene_p,
                "equal_var": branch == "Equal variances assumed",
                "t": lookup(cells, "Independent Samples Test", (outcome, branch, "t")),
                "df": lookup(cells, "Independent Samples Test", (outcome, branch, "df")),
                "p": lookup(cells, "Independent Samples Test", (outcome, branch, "Sig. (2-tailed)")),
                "mean_diff": lookup(cells, "Independent Samples Test", (outcome, branch, "Mean Difference")),
                "groups": groups,
                "d": cohen_d(groups),
            }
        )
    return results


def anova(cells: list[Cell]) -> list[dict]:
    """One SPSS ONEWAY command may cover several dependents; rows are labeled by the dependent."""
    dependents: list[str] = []
    for cell in tables_of(cells, "ANOVA"):
        if cell.row and cell.row[0] not in dependents and cell.row[0] not in {"Between Groups", "Within Groups", "Total"}:
            dependents.append(cell.row[0])
    if not dependents:
        dependents = [""]
    results = []
    for dep in dependents:
        prefix = (dep,) if dep else ()
        results.append(
            {
                "outcome": dep,
                "ss_between": lookup(cells, "ANOVA", prefix + ("Between Groups", "Sum of Squares")),
                "df_between": lookup(cells, "ANOVA", prefix + ("Between Groups", "df")),
                "F": lookup(cells, "ANOVA", prefix + ("Between Groups", "F")),
                "p": lookup(cells, "ANOVA", prefix + ("Between Groups", "Sig.")),
                "df_within": lookup(cells, "ANOVA", prefix + ("Within Groups", "df")),
                "ss_within": lookup(cells, "ANOVA", prefix + ("Within Groups", "Sum of Squares")),
                "ss_total": lookup(cells, "ANOVA", prefix + ("Total", "Sum of Squares")),
                "levene_p": lookup(cells, "Test of Homogeneity of Variance", prefix + ("Based on Mean", "Sig.")),
            }
        )
    ready = []
    for item in results:
        if item["F"] is None:
            continue
        if item.get("ss_between") is not None and item.get("ss_total") not in (None, 0):
            item["eta2"] = item["ss_between"] / item["ss_total"]
        ready.append(item)
    return ready


def frequencies(cells: list[Cell]) -> list[dict]:
    rows = []
    seen: set[tuple[str, ...]] = set()
    for cell in tables_of(cells, "Frequencies"):
        path = cell.row + cell.col
        if "Frequency" not in path or cell.number is None:
            continue
        raw = tuple(part for part in path if part not in {"Frequency", "Percent", "Valid Percent", "Cumulative Percent"})
        labels = tuple(part for part in raw if part not in {"Valid", "Missing", "Total", "0", "-1"})
        if not labels or raw in seen:
            continue
        seen.add(raw)
        rows.append({"labels": labels, "n": cell.number, "percent": lookup(cells, "Frequencies", raw + ("Percent",))})
    return rows


def pairwise(cells: list[Cell]) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for cell in tables_of(cells, "Multiple Comparisons"):
        if "Sig." not in cell.row + cell.col or cell.number is None:
            continue
        labels = [part for part in cell.row + cell.col if part not in {"Sig.", "Mean Difference (I-J)", "Std. Error"}]
        key = tuple(labels)
        if key in seen or len(labels) < 2:
            continue
        seen.add(key)
        found.append({"labels": labels, "p": cell.number})
    return found


def _kmo_table(cells: list[Cell]) -> str:
    names = {cell.table for cell in cells}
    for name in ("KMO and Bartlett's Test", "KMO and Bartlett Test"):
        if name in names:
            return name
    return "KMO and Bartlett's Test"


def factor_loadings(cells: list[Cell]) -> dict:
    table = "Rotated Factor Matrix" if any(cell.table == "Rotated Factor Matrix" for cell in cells) else "Factor Matrix"
    items: list[str] = []
    factors: list[str] = []
    grid: dict[tuple[str, str], float] = {}
    for cell in tables_of(cells, table):
        if not cell.row or not cell.col or cell.number is None:
            continue
        item = cell.row[0]
        factor = cell.col[-1]
        if item not in items:
            items.append(item)
        if factor not in factors:
            factors.append(factor)
        grid[(item, factor)] = cell.number
    return {"table": table, "items": items, "factors": factors, "values": {f"{item}|{factor}": value for (item, factor), value in grid.items()}}


def variance_share(cells: list[Cell]) -> dict:
    table = _kmo_table(cells)
    return {
        "kmo": lookup(cells, table, ("Kaiser-Meyer-Olkin Measure of Sampling Adequacy.",))
        or lookup(cells, table, ("Kaiser-Meyer-Olkin Measure of Sampling Adequacy",)),
        "bartlett_chi2": lookup(cells, table, ("Bartlett's Test of Sphericity", "Approx. Chi-Square")),
        "bartlett_df": lookup(cells, table, ("Bartlett's Test of Sphericity", "df")),
        "bartlett_p": lookup(cells, table, ("Bartlett's Test of Sphericity", "Sig.")),
        "first_pct": lookup(cells, "Total Variance Explained", ("1", "Initial Eigenvalues", "% of Variance")),
        "tables_present": sorted({cell.table for cell in cells}),
    }


def efa(cells: list[Cell]) -> dict:
    kmo = lookup(cells, "KMO and Bartlett's Test", ("Kaiser-Meyer-Olkin Measure of Sampling Adequacy.",))
    if kmo is None:
        kmo = lookup(cells, "KMO and Bartlett's Test", ("Kaiser-Meyer-Olkin Measure of Sampling Adequacy",))
    bartlett = lookup(cells, "KMO and Bartlett's Test", ("Bartlett's Test of Sphericity", "Approx. Chi-Square"))
    bartlett_df = lookup(cells, "KMO and Bartlett's Test", ("Bartlett's Test of Sphericity", "df"))
    bartlett_p = lookup(cells, "KMO and Bartlett's Test", ("Bartlett's Test of Sphericity", "Sig."))
    return {
        "kmo": kmo,
        "bartlett_chi2": bartlett,
        "bartlett_df": bartlett_df,
        "bartlett_p": bartlett_p,
        "tables_present": sorted({cell.table for cell in cells}),
    }


def coef(model: dict, name: str) -> dict | None:
    for item in model.get("coefficients") or []:
        if item["name"] == name:
            return item
    return None


def sobel(a: float | None, sa: float | None, b: float | None, sb: float | None) -> dict:
    if None in (a, sa, b, sb) or sa == 0 or sb == 0:
        return {"indirect": None, "se": None, "z": None, "p": None}
    indirect = a * b
    se = math.sqrt((b ** 2) * (sa ** 2) + (a ** 2) * (sb ** 2))
    if se == 0:
        return {"indirect": indirect, "se": se, "z": None, "p": None}
    z = indirect / se
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"indirect": indirect, "se": se, "z": z, "p": p}


def mediation(a_cells: list[Cell], c_cells: list[Cell], b_cells: list[Cell], x: str, m: str) -> dict:
    a_models = regression_models(a_cells)
    c_models = regression_models(c_cells)
    b_models = regression_models(b_cells)
    a_model = a_models[-1] if a_models else {}
    c_model = c_models[-1] if c_models else {}
    b_model = b_models[-1] if b_models else {}
    a_coef = coef(a_model, x) or {}
    c_coef = coef(c_model, x) or {}
    b_coef = coef(b_model, m) or {}
    c_prime = coef(b_model, x) or {}
    effect = sobel(a_coef.get("B"), a_coef.get("se"), b_coef.get("B"), b_coef.get("se"))
    return {
        "a": a_coef,
        "b": b_coef,
        "c": c_coef,
        "c_prime": c_prime,
        "a_model": a_model,
        "c_model": c_model,
        "b_model": b_model,
        **effect,
        "method": "Baron-Kenny steps plus Sobel test; bootstrap CI was not estimated",
    }
