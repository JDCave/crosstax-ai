"""Checksum operators backed by public official calculation specifications."""

import re
from datetime import date


def _digits(value: str, length: int) -> bool:
    return re.fullmatch(rf"[0-9]{{{length}}}", value) is not None


def nl_mod11(value: str) -> bool:
    if not _digits(value, 9):
        return False
    expected = sum(int(d) * w for d, w in zip(value[:8], range(9, 1, -1), strict=True)) % 11
    return expected < 10 and int(value[-1]) == expected


def pl_nip(value: str) -> bool:
    if not _digits(value, 10):
        return False
    expected = sum(int(d) * w for d, w in zip(value[:9], (6, 5, 7, 2, 3, 4, 5, 6, 7), strict=True)) % 11
    return expected < 10 and int(value[-1]) == expected


def pl_pesel(value: str) -> bool:
    if not _digits(value, 11):
        return False
    expected = (-sum(int(d) * w for d, w in zip(value[:10], (1, 3, 7, 9, 1, 3, 7, 9, 1, 3), strict=True))) % 10
    if int(value[-1]) != expected:
        return False
    month_code = int(value[2:4])
    centuries = {0: 1900, 1: 2000, 2: 2100, 3: 2200, 4: 1800}
    century = centuries.get(month_code // 20)
    if century is None:
        return False
    try:
        date(century + int(value[:2]), month_code % 20, int(value[4:6]))
    except ValueError:
        return False
    return True


def au_abn(value: str) -> bool:
    if not _digits(value, 11):
        return False
    digits = [int(d) for d in value]
    digits[0] -= 1
    return sum(d * w for d, w in zip(digits, (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19), strict=True)) % 89 == 0


def no_orgnr(value: str) -> bool:
    core = value[:-3] if value.endswith("MVA") else value
    if not _digits(core, 9) or core[0] not in "89":
        return False
    total = sum(int(d) * w for d, w in zip(core[:8], (3, 2, 7, 6, 5, 4, 3, 2), strict=True))
    return (total + int(core[-1])) % 11 == 0


def jp_corporate(value: str) -> bool:
    if not _digits(value, 13) or value[0] == "0":
        return False
    # Positions are counted from the right; odd weights 1, even weights 2.
    total = sum(int(d) * (1 if i % 2 == 0 else 2) for i, d in enumerate(reversed(value[1:])))
    return int(value[0]) == 9 - total % 9


def ca_sin(value: str) -> bool:
    """Service Canada MOD-10 procedure for the nine-digit SIN."""
    if not _digits(value, 9):
        return False
    total = 0
    for index, digit in enumerate(value):
        number = int(digit) * (2 if index % 2 else 1)
        total += number // 10 + number % 10
    return total % 10 == 0


def es_nif_nie(value: str) -> bool:
    """Interior Ministry formula for DNI and X/Y/Z-series NIE only."""
    if re.fullmatch(r"(?:[0-9]{8}|[XYZ][0-9]{7})[A-Z]", value) is None:
        return False
    body = value[:-1]
    if body[0] in "XYZ":
        body = str("XYZ".index(body[0])) + body[1:]
    return value[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(body) % 23]
