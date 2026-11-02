"""A small xlsx reader on the standard library (zipfile and xml.etree)."""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree

Cell = str | float | bool | None

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REF = re.compile(r"([A-Z]+)")


def _local(tag: str) -> str:
    """Tag name without its namespace, whatever the prefix."""
    return tag.rsplit("}", 1)[-1]


def _children(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in node if _local(child.tag) == name]


def _text_of(node: ElementTree.Element) -> str:
    """Concatenate every `t` text below a shared or inline string, rich text included."""
    return "".join(el.text or "" for el in node.iter() if _local(el.tag) == "t")


def _column_index(ref: str) -> int:
    """Zero-based column of a cell reference such as `AB12`."""
    match = _REF.match(ref)
    if match is None:
        raise ValueError(f"bad cell reference {ref!r}")
    index = 0
    for ch in match.group(1):
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
    return [_text_of(si) for si in _children(root, "si")]


def _first_sheet(zf: zipfile.ZipFile) -> tuple[str, str]:
    """Name and archive path of the first sheet, resolved through the workbook relationships."""
    workbook = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    sheets = _children(workbook, "sheets")
    first = _children(sheets[0], "sheet")[0]
    rel_id = first.get(f"{{{_REL_NS}}}id")
    rels = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.get("Id") == rel_id:
            target = rel.get("Target", "")
            path = target[1:] if target.startswith("/") else posixpath.join("xl", target)
            return first.get("name", ""), posixpath.normpath(path)
    raise ValueError(f"no relationship {rel_id!r} for the first sheet")


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> Cell:
    kind = cell.get("t")
    if kind == "inlineStr":
        return _text_of(cell)
    value_nodes = _children(cell, "v")
    raw = value_nodes[0].text if value_nodes else None
    if raw is None:
        return None
    if kind == "s":
        return shared[int(raw)]
    if kind == "b":
        return raw.strip() == "1"
    if kind in ("str", "e"):
        return raw
    try:
        return float(raw)
    except ValueError:
        return raw


def read_sheet(data: bytes) -> tuple[str, list[list[Cell]]]:
    """Return (sheet name, rows) of the first sheet of an xlsx file.

    Missing cells inside a row, including leading ones, are None. Raises ValueError when the
    bytes are not a readable workbook.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            name, path = _first_sheet(zf)
            shared = _shared_strings(zf)
            sheet = ElementTree.fromstring(zf.read(path))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, IndexError) as exc:
        raise ValueError(f"not a readable xlsx: {exc}") from exc
    rows: list[list[Cell]] = []
    for sheet_data in _children(sheet, "sheetData"):
        for row in _children(sheet_data, "row"):
            values: list[Cell] = []
            for position, cell in enumerate(_children(row, "c")):
                ref = cell.get("r")
                column = _column_index(ref) if ref else position
                values.extend([None] * (column - len(values)))
                values.append(_cell_value(cell, shared))
            rows.append(values)
    return name, rows
