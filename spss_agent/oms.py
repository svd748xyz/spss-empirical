"""Parse SPSS OMS XML into flat table cells. Numbers come only from this file."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NS = "{http://www.ibm.com/software/analytics/spss/xml/oms}"


@dataclass(frozen=True)
class Cell:
    command: str
    table: str
    row: tuple[str, ...]
    col: tuple[str, ...]
    number: float | None
    text: str


def _local(tag: str) -> str:
    return tag[len(NS) :] if tag.startswith(NS) else tag


def _label(elem: ET.Element) -> str:
    text = elem.get("text")
    if text is not None and text != "":
        return text
    return elem.get("varName") or ""


def _number(cell: ET.Element) -> float | None:
    raw = cell.get("number")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _walk(elem: ET.Element, row: tuple[str, ...], col: tuple[str, ...], axis: str, command: str, table: str, out: list[Cell]) -> None:
    tag = _local(elem.tag)
    if tag == "dimension":
        axis = elem.get("axis") or axis
        for child in list(elem):
            _walk(child, row, col, axis, command, table, out)
        return
    if tag in ("category", "group"):
        label = _label(elem)
        if axis == "column":
            col = col + (label,)
        else:
            row = row + (label,)
        for child in list(elem):
            _walk(child, row, col, axis, command, table, out)
        return
    if tag == "cell":
        out.append(
            Cell(
                command=command,
                table=table,
                row=row,
                col=col,
                number=_number(elem),
                text=elem.get("text") or "",
            )
        )
        return
    for child in list(elem):
        _walk(child, row, col, axis, command, table, out)


def parse_oms(path: Path) -> list[Cell]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    root = ET.parse(path).getroot()
    cells: list[Cell] = []
    for command in root:
        if _local(command.tag) != "command":
            continue
        command_name = command.get("command") or ""
        for table in command.iter():
            if _local(table.tag) != "pivotTable":
                continue
            subtype = table.get("subType") or table.get("text") or ""
            _walk(table, (), (), "row", command_name, subtype, cells)
    return cells


def tables_of(cells: list[Cell], subtype: str) -> list[Cell]:
    return [cell for cell in cells if cell.table == subtype]


def lookup(cells: list[Cell], table: str, parts: tuple[str, ...]) -> float | None:
    """Find a numeric cell whose row and column labels contain every requested part."""
    for cell in cells:
        if cell.table != table or cell.number is None:
            continue
        labels = cell.row + cell.col
        if all(part in labels for part in parts):
            return cell.number
    return None
