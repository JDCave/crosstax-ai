"""Public specification vectors and checksum rejection boundaries."""

import pytest

from backend.engine.checksums import au_abn, ca_sin, es_nif_nie, jp_corporate, nl_mod11, no_orgnr, pl_nip, pl_pesel


@pytest.mark.parametrize(
    ("operator", "valid", "invalid"),
    [
        (ca_sin, "998986731", "998986732"),
        (es_nif_nie, "12345678Z", "12345678A"),
        (es_nif_nie, "X1234567L", "X1234567A"),
        (au_abn, "51824753556", "51824753557"),  # ABR published worked example
        (jp_corporate, "8700110005901", "9700110005901"),  # NTA worked example
        (pl_pesel, "02070803628", "02070803629"),  # OECD Poland worked example
        (pl_nip, "2234567895", "2234567896"),  # OECD Poland worked example
        (nl_mod11, "123456782", "123456783"),  # arithmetic fixture, no existence assertion
        (no_orgnr, "974760673", "974760674"),
    ],
)
def test_public_checksum_operators(operator, valid, invalid):
    assert operator(valid)
    assert not operator(invalid)
    for malformed in ("", "A", "\uff11\uff12\uff13", valid + "0"):
        assert not operator(malformed)


def test_optional_norwegian_vat_suffix():
    assert no_orgnr("974760673MVA")
    assert not no_orgnr("974760674MVA")
    assert not no_orgnr("174760673")


def test_pesel_rejects_impossible_dates_even_with_checksum():
    # February 31, 1902: checksum is computed independently for a date-negative fixture.
    digits = "0202310362"
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    check = (-sum(int(d) * w for d, w in zip(digits, weights, strict=True))) % 10
    assert not pl_pesel(digits + str(check))


def test_pesel_century_month_mappings():
    for month in ("01", "21", "41", "61", "81"):
        digits = "00" + month + "010001"
        weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
        check = (-sum(int(d) * w for d, w in zip(digits, weights, strict=True))) % 10
        assert pl_pesel(digits + str(check))
