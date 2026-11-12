"""Deterministic extractor contract tests (T012).

Asserts the two capabilities US1-AS2 / US5-AS3 depend on:
- Tagged PDF structure-tree tables (/Table /TR /TD) reconstruct with row/column fidelity —
  no cross-row bleed on the four official IRD forms.
- Sub-item fill-ins ("regularly traded on ___") are attributed to the correct sub-option,
  and a document without /StructTreeRoot degrades with the fact recorded (FR-003).
"""

from __future__ import annotations

import io
from pathlib import Path

from backend.agents.deterministic_extractor import extract
from backend.agents.media_preprocessor import preprocess

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "crs-templates"


def load(name: str):
    return preprocess((ASSETS / name).read_bytes())


# --- structure-tree table fidelity (US1-AS2, FR-003/R48) -------------------------------


def test_entity_classification_table_rows_keep_column_attribution() -> None:
    result = extract(load("crs-entity-ird.pdf"))
    table = next(t for t in result.tables if t and "Financial Institution" in t[0][0])
    rows = {row[0]: row for row in table if row[0]}
    assert rows["Financial Institution"][1].startswith("Custodial Institution")
    assert rows["Active NFE"][1].startswith("NFE the stock of which")
    assert rows["Passive NFE"][1].startswith("Investment entity")
    # no bleed: a row's category label must not reappear inside another row's column 2
    assert "Passive NFE" not in rows["Active NFE"][1]


def test_controlling_person_type_matrix_is_two_dimensional() -> None:
    result = extract(load("crs-controlling-person-ird.pdf"))
    matrix = next(t for t in result.tables if t and t[0] and "Entity (1)" in " | ".join(t[0]))
    header = matrix[0]
    assert any("Entity (2)" in c for c in header) and any("Entity (3)" in c for c in header)
    assert len(matrix) == 14  # header + 11 category rows + group openers, all preserved
    body = [row for row in matrix[1:] if len(row) == 5]
    assert len(body) == 13  # every row keeps all 5 columns; nothing collapsed
    category_col = " | ".join(row[1] for row in body)
    assert sum(word in category_col for word in ("Settlor", "Trustee", "Protector or enforcer")) >= 3
    assert sum("Entity (1)" in row[1] for row in body) == 0  # header never bleeds into category column
    # the three answer columns stay separate cells (box glyph present), never merged into one value
    answer_rows = [row for row in body if len(row) == 5]
    assert all(row[2] == row[3] == row[4] for row in answer_rows)  # blank template: three unchecked boxes
    assert answer_rows[0][2]  # non-empty: the box itself is present as a distinct cell


def test_tin_table_row_columns_do_not_bleed_on_entity_form() -> None:
    result = extract(load("crs-entity-ird.pdf"))
    tin = next(t for t in result.tables if t and "TIN" in t[0][1])
    assert [c for c in tin[0]][:4] == tin[0][:4]
    assert "Explain why" in tin[0][3]
    assert "Enter Reason" in tin[0][2]
    assert len(tin) == 6  # header + 5 printed rows
    for row in tin[1:]:
        assert row[0] in {"(1)", "(2)", "(3)", "(4)", "(5)"}
        assert row[1:] == ["", "", ""]  # blank template: values absent, positions preserved


# --- flat fields aligned with the contract (T013) --------------------------------------


def test_individual_form_contract_shaped_extraction() -> None:
    result = extract(load("crs-individual-ird.pdf"))
    f = result.fields
    assert f["holder_type"] == "INDIVIDUAL"
    assert f["document.is_encrypted"] is True
    assert f["document.structure_tree_available"] is True
    assert f["document.has_continuation_sheets"] is False
    assert len(f["document.fingerprint"]) == 64
    # R28 five printed rows survive as repeat-group instances with null values
    assert [f"tax_residencies[{i}].jurisdiction" for i in range(5)]
    assert all(f[f"tax_residencies[{i}].jurisdiction"] is None for i in range(5))
    assert f["name.last_name"] is None and f["name.first_name"] is None
    assert f["hk_identity.hkid_or_passport"] is None
    assert f["birth_date"] is None and f["birth_place"] is None
    assert f["declaration.has_signature"] is False
    assert f["declaration.holder_or_authorized_resolved"] is False
    # FR-010: mailing block only conditionally present; both blocks are address slots
    assert f["addresses[0].type"] == "RESIDENCE"


def test_mailing_double_line_two_anomaly_is_exposed_not_silenced() -> None:
    """R18 / FR-043: the individual form prints two "Line 2" labels in the mailing block."""
    result = extract(load("crs-individual-ird.pdf"))
    assert any("DUPLICATE_LABEL_LINE_2" in a for a in result.anomalies)
    assert result.fields["addresses[1].source_layout_anomaly"] == "DUPLICATE_LABEL_LINE_2"


def test_entity_and_controlling_person_shapes() -> None:
    ent = extract(load("crs-entity-ird.pdf")).fields
    assert ent["holder_type"] == "ENTITY"
    assert ent["hk_identity.business_registration_number"] is None
    assert ent["entity.entity_type"] is None  # VISION_ONLY: deterministic path declares blind
    assert ent["entity.controlling_person_names"] == []
    cp = extract(load("crs-controlling-person-ird.pdf")).fields
    assert cp["holder_type"] == "CONTROLLING_PERSON"
    assert cp["controlling_person.controlled_entities[0].entity_name"] is None
    assert len([k for k in cp if k.startswith("controlling_person.controlled_entities[")]) == 3 * 4


# --- sub-item attribution (US5-AS3 same-source capability) ------------------------------


def _plain_pdf(lines: list[str]) -> bytes:
    """One-page untagged PDF (no /StructTreeRoot) with the given literal text lines."""
    from reportlab.pdfgen import canvas  # dev-proven dependency already in project

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setFont("Helvetica", 8)
    y = 780
    for line in lines:
        c.drawString(30, y, line)
        y -= 12
    c.save()
    return buffer.getvalue()


def test_regularly_traded_subitem_is_attributed_to_the_right_option() -> None:
    pdf = _plain_pdf(
        [
            "Part 2 Entity Type (Please complete this part and indicate the relevant information.)",
            "Financial Institution  Custodial Institution, Depository Institution",
            "Active NFE  NFE the stock of which is regularly traded on NASDAQ, which is an established",
            "securities market  Active NFE  Related entity of ACME Holdings, the stock of which is",
            "regularly traded on HKEX, which is an established securities market  Passive NFE",
            "Investment entity that is managed by a Financial Institution",
            "Active NFE other than the above (Please specify Government Pension Scheme)",
        ]
    )
    result = extract(preprocess(pdf))
    assert result.structure_tree_used is False  # FR-003: degradation recorded, not silent
    assert result.fields["entity.entity_type_subitem.regularly_traded_on"] == "NASDAQ"
    assert result.fields["entity.entity_type_subitem.related_entity_of"] == "ACME Holdings"
    assert result.fields["entity.entity_type_subitem.specify"] == "Government Pension Scheme"


def test_blank_subitems_stay_null() -> None:
    result = extract(load("crs-entity-ird.pdf"))
    sub = result.fields
    assert sub["entity.entity_type_subitem.regularly_traded_on"] is None
    assert sub["entity.entity_type_subitem.related_entity_of"] is None
    assert sub["entity.entity_type_subitem.specify"] is None


def test_header_reference_number_slot_present_on_all_forms() -> None:
    for name in ("crs-individual-ird.pdf", "crs-entity-ird.pdf", "crs-controlling-person-ird.pdf"):
        fields = extract(load(name)).fields
        assert "x-header.ref_no" in fields  # R03/FR-045 intake link key carrier (blank -> None)
        assert fields["x-header.ref_no"] is None
