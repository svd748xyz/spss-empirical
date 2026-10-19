"""Plan normalization and syntax for reverse items, dummies, and parallel mediation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from spss_agent.plan import PlanError, prepare_plan
from spss_agent.syntax import build_syntax

ROOT = Path(__file__).resolve().parents[1]


def _plan() -> dict:
    return {
        "title": "核对",
        "data_file": "data.csv",
        "variables": [
            {"name": "gender", "label": "性别", "values": {"1": "男", "2": "女"}},
            {
                "name": "grade",
                "label": "年级",
                "values": {"1": "大一", "2": "大二", "3": "大三"},
                "coding": "dummy",
                "reference": "1",
            },
            {"name": "age", "label": "年龄"},
            {"name": "satisfaction", "label": "学业满意度"},
        ],
        "scales": [
            {
                "name": "anxiety",
                "label": "焦虑",
                "items": ["anx1", "anx2", "anx4"],
                "reverse": [{"item": "anx4", "low": 1, "high": 5}],
            },
            {"name": "depression", "label": "抑郁", "items": ["dep1", "dep2"]},
            {"name": "support", "label": "社会支持", "items": ["sup1", "sup2"]},
        ],
        "analyses": [
            {"type": "reliability", "scale": "anxiety", "items": ["anx1", "anx2", "anx4"]},
            {
                "type": "regression",
                "dependent": "satisfaction",
                "blocks": [["grade", "age"], ["grade", "age", "anxiety"]],
            },
            {
                "type": "mediation",
                "x": "support",
                "m": ["anxiety", "depression"],
                "y": "satisfaction",
                "controls": ["grade", "age"],
            },
        ],
    }


class PlanTests(unittest.TestCase):
    def test_examples_still_prepare(self) -> None:
        for relative in (
            "examples/demo_questionnaire/分析方案.json",
            "examples/work_stress/分析方案.json",
        ):
            raw = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            prepared = prepare_plan(raw)
            self.assertEqual(prepared["analyses"][0]["type"], raw["analyses"][0]["type"])

    def test_reverse_dummy_and_parallel_mediation(self) -> None:
        prepared = prepare_plan(_plan())
        self.assertEqual(prepared["scales"][0]["items"], ["anx1", "anx2", "anx4_r"])
        self.assertEqual(prepared["analyses"][0]["items"], ["anx1", "anx2", "anx4_r"])
        self.assertEqual(prepared["analyses"][1]["blocks"][0], ["grade_d2", "grade_d3", "age"])
        self.assertEqual(prepared["analyses"][2]["controls"], ["grade_d2", "grade_d3", "age"])
        job = build_syntax(prepared, Path("prepared.csv"), [("age", "F8.2")], Path("oms"))
        text = job.text()
        self.assertIn("COMPUTE anx4_r=1+5-anx4.", text)
        self.assertIn("COMPUTE anxiety=MEAN(anx1,anx2,anx4_r).", text)
        self.assertIn("COMPUTE grade_d2=(grade = 2).", text)
        self.assertIn("COMPUTE grade_d3=(grade = 3).", text)
        self.assertIn("/DEPENDENT anxiety", text)
        self.assertIn("/DEPENDENT depression", text)
        self.assertIn("/METHOD=ENTER support anxiety depression grade_d2 grade_d3 age.", text)
        self.assertEqual([block["id"] for block in job.blocks if block["id"].startswith("03_")], ["03_mediation_a1", "03_mediation_a2", "03_mediation_c", "03_mediation_b"])

    def test_serial_multiple_moderator_and_extra_procedures(self) -> None:
        plan = _plan()
        plan["analyses"] = [
            {"type": "mediation", "x": "support", "m": ["anxiety", "depression"], "y": "satisfaction", "structure": "serial", "controls": ["grade"]},
            {"type": "moderation", "x": "anxiety", "w": ["support", "age"], "y": "satisfaction"},
            {"type": "moderated_mediation", "x": "support", "m": "anxiety", "y": "satisfaction", "w": "depression", "stage": "both", "controls": ["grade"]},
            {"type": "spearman", "vars": ["anxiety", "depression"]},
            {"type": "chisq", "row": "gender", "col": "grade"},
            {"type": "mannwhitney", "group": "gender", "codes": [1, 2], "outcomes": ["satisfaction"]},
            {"type": "kruskal", "factor": "grade", "outcomes": ["satisfaction"]},
            {"type": "logistic", "dependent": "gender", "predictors": ["age", "grade"]},
        ]
        prepared = prepare_plan(plan)
        self.assertEqual(prepared["analyses"][6]["codes"], ["1", "3"])
        self.assertEqual(prepared["analyses"][7]["predictors"], ["age", "grade_d2", "grade_d3"])
        job = build_syntax(prepared, Path("prepared.csv"), [("age", "F8.2")], Path("oms"))
        text = job.text()
        self.assertIn("/DEPENDENT depression", text)
        self.assertIn("/METHOD=ENTER support anxiety grade_d2 grade_d3.", text)
        self.assertIn("/METHOD=ENTER support anxiety depression grade_d2 grade_d3.", text)
        self.assertIn("xw_2_0", text)
        self.assertIn("xw_2_1", text)
        self.assertIn("COMPUTE mmxw_3=", text)
        self.assertIn("COMPUTE mmmw_3=", text)
        self.assertIn("NONPAR CORR", text)
        self.assertIn("CROSSTABS", text)
        self.assertIn("/M-W=satisfaction BY gender(1 2).", text)
        self.assertIn("/K-W=satisfaction BY grade(1 3).", text)
        self.assertIn("LOGISTIC REGRESSION gender", text)

    def test_rejects_models_outside_the_menu(self) -> None:
        plan = _plan()
        plan["analyses"] = [{"type": "mediation", "x": "support", "m": ["anxiety", "depression"], "y": "satisfaction", "structure": "process"}]
        with self.assertRaises(PlanError) as raised:
            prepare_plan(plan)
        self.assertIn("moderated_mediation", str(raised.exception))

        plan = _plan()
        plan["analyses"] = [{"type": "moderated_mediation", "x": "support", "m": ["anxiety", "depression"], "y": "satisfaction", "w": "age", "stage": "a"}]
        with self.assertRaises(PlanError) as raised:
            prepare_plan(plan)
        self.assertIn("一个中介变量", str(raised.exception))

        plan = _plan()
        plan["analyses"] = [{"type": "regression", "dependent": "satisfaction", "blocks": [["age"], ["anxiety"]]}]
        with self.assertRaises(PlanError) as raised:
            prepare_plan(plan)
        self.assertIn("上一层", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
