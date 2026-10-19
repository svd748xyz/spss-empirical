"""Create a small correlated questionnaire so the README example can be rerun."""

from __future__ import annotations

import csv
import random
from pathlib import Path


def likert(value: float) -> int:
    return max(1, min(5, int(round(value))))


def main() -> None:
    rng = random.Random(19)
    root = Path(__file__).resolve().parent / "demo_questionnaire"
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for _ in range(120):
        gender = rng.choice([1, 2])
        grade = rng.choice([1, 2, 3])
        age = rng.randint(18, 24)
        anxiety = rng.gauss(0, 1)
        support = rng.gauss(0, 1)
        depression = 0.55 * anxiety - 0.25 * support + rng.gauss(0, 0.8)
        satisfaction = 0.35 * support - 0.45 * anxiety - 0.2 * depression + 0.15 * (anxiety * support) + rng.gauss(0, 0.7)
        anx = [likert(3.1 + 0.7 * anxiety + rng.gauss(0, 0.45)) for _ in range(4)]
        dep = [likert(2.8 + 0.7 * depression + rng.gauss(0, 0.5)) for _ in range(4)]
        sup = [likert(3.2 + 0.7 * support + rng.gauss(0, 0.45)) for _ in range(3)]
        rows.append([gender, grade, age, *anx, *dep, *sup, round(3 + satisfaction, 3)])
    header = [
        "gender", "grade", "age",
        "anx1", "anx2", "anx3", "anx4",
        "dep1", "dep2", "dep3", "dep4",
        "sup1", "sup2", "sup3",
        "satisfaction",
    ]
    with (root / "data.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(root / "data.csv")


if __name__ == "__main__":
    main()
