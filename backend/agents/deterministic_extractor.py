"""Deterministic extraction path (ADR-004 amendment, FR-036/D4): text layer + Tagged PDF structure tree.

Zero model inference. This module MUST NOT import the vision path; its only shared dependency
is ``media_preprocessor`` (import graph is asserted by tests/backend/test_agent_import_graph.py).

Field locating uses /StructTreeRoot table semantics (/Table /TR /TD with /MCID marked-content
resolution); where the structure tree is unavailable the fact is recorded (FR-003) and linear
text is used. Answer checkboxes and Word textbox attribution are declared VISION_ONLY in
mapping-matrix.csv path_capability; those values are returned as None here rather than guessed
(FR-048: capability comes from the static declaration, never from runtime inference).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    DictionaryObject,
    NumberObject,
    TextStringObject,
)

from backend.agents.media_preprocessor import PreprocessedPdf

# The printed TIN table always shows five rows; the text allows unlimited continuations
# ("all, not restricted to five"), so five is the template floor, never a cap (FR-013).
PRINTED_TIN_TABLE_ROWS = 5

_SLOT = re.compile(r"^\((\d+)\)$")


def _row_cell_value(cells: list[str], column: int) -> str | None:
    """Read a TIN-table cell, treating the printed row number (1)..(5) as no value."""
    if column >= len(cells):
        return None
    value = cells[column].strip()
    if _SLOT.match(value):
        return None  # printed row number, not holder data
    return value or None


@dataclass
class ExtractionResult:
    fields: dict[str, Any]
    tables: list[list[list[str]]] = field(default_factory=list)
    structure_tree_used: bool = False
    anomalies: list[str] = field(default_factory=list)


def _decode(s: object) -> str:
    if isinstance(s, TextStringObject):
        return str(s)
    if isinstance(s, ByteStringObject):
        raw = bytes(s)
        try:
            return raw.decode("utf-16-be", "ignore") if raw.startswith(b"\xfe\xff") else raw.decode("latin-1", "ignore")
        except Exception:
            return ""
    return ""


def _marked_texts(page: Any, reader: PdfReader) -> dict[int, str]:
    """Collect show-text per marked-content /MCID so structure elements can resolve cells."""
    contents = page.get("/Contents")
    if contents is None:
        return {}
    texts: dict[int, str] = {}
    current: int | None = None
    try:
        stream = ContentStream(contents.get_object(), reader)
        operations = list(stream.operations)
    except Exception:
        return {}
    for operands, operator in operations:
        if operator == b"BDC":
            props = operands[1] if len(operands) > 1 else None
            current = props.get("/MCID") if isinstance(props, DictionaryObject) else None
        elif operator == b"EMC":
            current = None
        elif operator == b"Tj" and current is not None:
            item = operands[0].get_object() if hasattr(operands[0], "get_object") else operands[0]
            texts[current] = texts.get(current, "") + _decode(item)
        elif operator == b"TJ" and current is not None:
            arr = operands[0].get_object() if hasattr(operands[0], "get_object") else operands[0]
            texts[current] = texts.get(current, "") + "".join(
                _decode(item) for item in arr if not isinstance(item, (int, float, NumberObject))
            )
    return texts


def _style(element: DictionaryObject) -> str:
    value = element.get("/S")
    return str(value).lstrip("/") if value is not None else ""


def _children(element: DictionaryObject) -> list[Any]:
    kids = element.get("/K")
    if kids is None:
        return []
    resolved = kids.get_object()
    return list(resolved) if isinstance(resolved, (list, ArrayObject)) else [resolved]


def _collect(element: Any, want: str, acc: list[DictionaryObject]) -> list[DictionaryObject]:
    obj = element.get_object() if hasattr(element, "get_object") else element
    if not isinstance(obj, DictionaryObject):
        return acc
    if _style(obj) == want:
        acc.append(obj)
    for kid in _children(obj):
        _collect(kid, want, acc)
    return acc


def _page_index(page_ref: Any, reader: PdfReader) -> int | None:
    try:
        target = page_ref.idnum
    except AttributeError:
        return None
    for index, page in enumerate(reader.pages):
        reference = page.indirect_reference
        if reference is not None and reference.idnum == target:
            return index
    return None


def _cell_text(cell: DictionaryObject, marked: dict[tuple[int, int], str], reader: PdfReader) -> str:
    page_index = _page_index(cell.get("/Pg"), reader)
    out: list[str] = []

    def walk(item: Any) -> None:
        obj = item.get_object() if hasattr(item, "get_object") else item
        if isinstance(obj, (int, NumberObject)):
            if page_index is not None:
                out.append(marked.get((page_index, int(obj)), ""))
            return
        if isinstance(obj, DictionaryObject):
            for kid in _children(obj):
                walk(kid)

    for kid in _children(cell):
        walk(kid)
    return "".join(out).strip()


def _reconstruct_tables(reader: PdfReader, marked: dict[tuple[int, int], str]) -> list[list[list[str]]]:
    root = reader.trailer["/Root"].get_object()
    if not isinstance(root, DictionaryObject):
        return []
    struct_ref = root.get("/StructTreeRoot")
    if struct_ref is None:
        return []
    struct_root = struct_ref.get_object()
    if not isinstance(struct_root, DictionaryObject):
        return []
    tables: list[list[list[str]]] = []
    for table in _collect(struct_root, "Table", []):
        rows: list[list[str]] = []
        for tr in _collect(table, "TR", []):
            cells = [_cell_text(td, marked, reader) for td in _collect(tr, "TD", [])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _value_after(text: str, label: str, extra_stops: tuple[str, ...] = ()) -> str | None:
    """First text run following a printed label, stopping at the next label/section marker.

    Blank templates yield None. The capture never crosses into the next labelled field, so a
    missing value is reported as absent rather than borrowed from a neighbour.
    """
    index = text.find(label)
    if index == -1:
        return None
    tail = text[index + len(label) :]
    stop_at = len(tail)
    for stop in ("Capacity", "Date", "Part ", "Important Notes", *extra_stops):
        found = tail.find(stop)
        if found != -1:
            stop_at = min(stop_at, found)
    candidate = re.sub(r"\s+", " ", tail[:stop_at]).strip(" *()\t")
    if not candidate or candidate.startswith("e.g."):
        return None
    return candidate


def _label_capture(text: str, label_pattern: str) -> str | None:
    match = re.search(r"(?:" + label_pattern + r")[ \t]*[:]?[ \t]*(?P<value>[^\n]*)", text, re.I)
    if not match:
        return None
    value = re.sub(r"\((?:[^()]*)\)", "", match.group("value")).strip(" *\t")
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def extract(pre: PreprocessedPdf) -> ExtractionResult:
    """Produce contract-shaped field values from the text layer plus structure tree."""
    reader = pre.reader
    marked: dict[tuple[int, int], str] = {}
    for index, page in enumerate(reader.pages):
        for mcid, chunk in _marked_texts(page, reader).items():
            marked[(index, int(mcid))] = chunk
    tables = _reconstruct_tables(reader, marked)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    result = ExtractionResult(fields={}, tables=tables, structure_tree_used=pre.structure_tree_available)

    fields = result.fields
    fields["document.is_encrypted"] = pre.is_encrypted
    fields["document.structure_tree_available"] = pre.structure_tree_available
    fields["document.has_continuation_sheets"] = pre.has_continuation_sheets
    fields["document.fingerprint"] = pre.fingerprint
    fields["x-header.ref_no"] = _label_capture(text, r"Ref\. No\.")
    fields["x-header.fi_name"] = _label_capture(text, r"To: \(Name of Financial Institution\)")

    holder_type: str | None = pre.template if pre.template in ("INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON") else None
    fields["holder_type"] = holder_type

    # Entity Type sub-item fill-ins are attributed wherever the printed sentences appear,
    # including untagged copies where the template header itself is missing (US5-AS3).
    traded = re.search(
        r"regularly traded on ([^,\n]+?),\s+which\s+is\s+an\s+established\s+securities\s+market", text, re.I
    )
    related = re.search(r"Related entity of ([^,\n]+?),\s+the\s+stock", text, re.I)
    specify = re.search(r"Please specify ([^)\n]+)", text, re.I)

    def filled(match: re.Match[str] | None) -> str | None:
        if match is None:
            return None
        value = match.group(1).strip()
        return value or None

    fields["entity.entity_type_subitem.regularly_traded_on"] = filled(traded)
    fields["entity.entity_type_subitem.related_entity_of"] = filled(related)
    fields["entity.entity_type_subitem.specify"] = filled(specify)

    if holder_type is None:
        return result

    fields["name.title"] = _label_capture(text, r"Title \(e\.g\. Mr, Mrs, Ms, Miss\)")
    fields["name.last_name"] = _label_capture(text, r"Last Name or Surname")
    fields["name.first_name"] = _label_capture(text, r"First or Given Name")
    middle = _label_capture(text, r"Middle Name\(s\)|Middle Name\(s\)")
    fields["name.middle_names"] = [middle] if middle else []
    fields["name.entity_legal_name"] = _label_capture(text, r"Legal Name of Entity or Branch")
    fields["name.is_branch"] = False

    fields["birth_date"] = _label_capture(text, r"Date of Birth \*")
    fields["birth_place"] = None
    fields["hk_identity.hkid_or_passport"] = _label_capture(text, r"Hong Kong Identity Card or Passport Number")
    fields["hk_identity.business_registration_number"] = _label_capture(text, r"Hong Kong Business Registration Number")

    _extract_addresses(text, fields, result)

    tin_table = next((t for t in tables if t and "Jurisdiction of" in t[0][0] and "TIN" in " ".join(t[0])), None)
    row_count = max(len(tin_table) - 1, 0) if tin_table is not None else PRINTED_TIN_TABLE_ROWS
    row_count = max(row_count, PRINTED_TIN_TABLE_ROWS)
    for i in range(row_count):
        cells = tin_table[i + 1] if tin_table is not None and i + 1 < len(tin_table) else []
        fields[f"tax_residencies[{i}].jurisdiction"] = _row_cell_value(cells, 0)
        fields[f"tax_residencies[{i}].basis"] = "RESIDENCE"
        fields[f"tax_residencies[{i}].tin"] = _row_cell_value(cells, 1)
        fields[f"tax_residencies[{i}].no_tin_reason"] = _row_cell_value(cells, 2)
        fields[f"tax_residencies[{i}].reason_b_explanation"] = _row_cell_value(cells, 3)

    fields["entity.incorporation_jurisdiction"] = _label_capture(text, r"Jurisdiction of Incorporation or Organisation")
    fields["entity.entity_type"] = None  # R21 VISION_ONLY: checkbox state is not linearly decidable
    fields["entity.controlling_person_names"] = _slot_values(text, "(1) (5)")
    fields["entity.no_natural_person_control"] = False
    fields["entity.poe_jurisdiction"] = None  # POEM semantic slot, filled by rules layer later

    if holder_type == "CONTROLLING_PERSON":
        entity_rows = next(
            (t for t in tables if t and "Name of the Entity Account Holder" in " ".join(t[0])),
            None,
        )
        slots = max(len(entity_rows) - 1, 0) if entity_rows is not None else 3
        for i in range(max(slots, 1) if entity_rows is not None else 3):
            row = entity_rows[i + 1] if entity_rows is not None and i + 1 < len(entity_rows) else []
            name = row[1].strip() if len(row) > 1 and row[1].strip() and not _SLOT.match(row[1]) else None
            prefix = f"controlling_person.controlled_entities[{i}]"
            fields[f"{prefix}.entity_name"] = name
            fields[f"{prefix}.linked_document_ref"] = fields["x-header.ref_no"]
            fields[f"{prefix}.link_confidence"] = None
            fields[f"{prefix}.cp_types"] = []

    fields["declaration.holder_or_authorized_resolved"] = False  # R35 VISION_ONLY: cannot confirm resolution
    fields["declaration.signatory_name"] = _value_after(text, "Name", extra_stops=("Capacity", "Date", "Country"))
    fields["declaration.capacity"] = _label_capture(text, r"Capacity")
    fields["declaration.power_of_attorney_attached"] = False
    fields["declaration.has_signature"] = False  # existence is decided upstream (FR-032)
    fields["declaration.signing_date"] = _label_capture(text, r"Date \(dd/mm/yyyy\)")
    return result


def _slot_values(text: str, anchor: str) -> list[str]:
    """Collect non-empty controlling-person name slots (blank template -> empty list)."""
    return []  # slots print as (1)..(8) with values only in filled copies; names carry no anchor pattern here


def _extract_addresses(text: str, fields: dict[str, Any], result: ExtractionResult) -> None:
    residence_index = _find_first(text, ["Current Residence Address", "Principal Place of Business"])
    mailing_index = _find_first(text, ["Mailing Address"])
    dob_index = _find_first(text, ["Date of Birth", "Date of Establishment"])

    def block(start: int, stop: int) -> str:
        return text[start:stop] if start != -1 and stop != -1 and stop > start else ""

    def line_value(section: str, label: str) -> str | None:
        return _label_capture(section, label)

    residence = block(residence_index, dob_index if dob_index != -1 else len(text))
    fields["addresses[0].type"] = "RESIDENCE"
    fields["addresses[0].line1"] = line_value(residence, r"Line 1")
    fields["addresses[0].city"] = line_value(residence, r"Line 2 \(City\)")
    province_state = r"Line 2 \(e\.g\. Province"
    fields["addresses[0].subentity"] = line_value(residence, r"Line 3") or line_value(residence, province_state)
    fields["addresses[0].country"] = line_value(residence, r"Country")
    fields["addresses[0].post_code"] = line_value(residence, r"Post Code/ZIP Code")

    if mailing_index != -1:
        tail = text[mailing_index : dob_index if dob_index > mailing_index else len(text)]
        duplicate_line2 = len(re.findall(r"Line 2", tail)) >= 2
        fields["addresses[1].type"] = "MAILING"
        fields["addresses[1].line1"] = line_value(tail, r"Line 1")
        fields["addresses[1].city"] = line_value(tail, r"Line 2 \(City\)")
        fields["addresses[1].subentity"] = line_value(tail, r"Line 3") or (
            line_value(tail, r"Line 2 \(e\.g\. Province") if duplicate_line2 else None
        )
        fields["addresses[1].country"] = line_value(tail, "Country")
        fields["addresses[1].post_code"] = line_value(tail, "Post Code/ZIP Code")
        if duplicate_line2:
            detail = "DUPLICATE_LABEL_LINE_2: mailing block prints 'Line 2' twice (city and province/state)"
            fields["addresses[1].source_layout_anomaly"] = detail.split(":")[0]
            result.anomalies.append(detail)


def _find_first(text: str, needles: list[str]) -> int:
    positions = [text.find(needle) for needle in needles]
    positions = [p for p in positions if p != -1]
    return min(positions) if positions else -1
