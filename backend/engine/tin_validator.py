"""Deterministic TIN checks against an audit-bound rule snapshot."""

from __future__ import annotations

import re
from collections.abc import Callable
from types import MappingProxyType

from backend.engine.contracts import AuditIssue
from backend.engine.rule_loader import RuleSnapshot


def mod11_2(value: str) -> bool:
    """18-character Chinese resident ID checksum (not entity USCC)."""
    if re.fullmatch(r"[0-9]{17}[0-9X]", value) is None:
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    remainder = sum(int(digit) * weight for digit, weight in zip(value[:17], weights, strict=True)) % 11
    return value[-1] == "10X98765432"[remainder]


def hkid_weight(value: str) -> bool:
    """Weighted modulus-11 check for one/two-letter HKID identifiers."""
    if re.fullmatch(r"[A-Z]{1,2}[0-9]{6}[0-9A]", value) is None:
        return False
    prefix = value[:-7]
    first, second = (36, ord(prefix[0]) - 55) if len(prefix) == 1 else tuple(ord(c) - 55 for c in prefix)
    total = first * 9 + second * 8
    total += sum(int(digit) * weight for digit, weight in zip(value[-7:-1], (7, 6, 5, 4, 3, 2), strict=True))
    return (total + (10 if value[-1] == "A" else int(value[-1]))) % 11 == 0


def nric_weight(value: str) -> bool:
    """S/T-series NRIC checksum; FIN and UEN require separate algorithms."""
    if re.fullmatch(r"[ST][0-9]{7}[A-Z]", value) is None:
        return False
    total = sum(int(digit) * weight for digit, weight in zip(value[1:8], (2, 7, 6, 5, 4, 3, 2), strict=True))
    if value[0] == "T":
        total += 4
    return value[-1] == "JZIHGFEDCBA"[total % 11]


OPERATORS: MappingProxyType[str, Callable[[str], bool]] = MappingProxyType(
    {
        "MOD11_2": mod11_2,
        "HKID_WEIGHT": hkid_weight,
        "NRIC_WEIGHT": nric_weight,
        "REGEX_ONLY": lambda value: True,
    }
)


class TINValidatorEngine:
    """No database access, network calls or country-specific rules in execution."""

    def validate(
        self,
        tin: str | None,
        jurisdiction_code: str,
        snapshot: RuleSnapshot,
        holder_type: str | None = None,
        tin_type: str | None = None,
    ) -> list[AuditIssue]:
        # Guard before regex processing. The input contract expects short identifiers.
        if tin is None or len(tin) > 256:
            return self._invalid("TIN 缺失或长度超出允许范围")
        value = re.sub(r"[\s()\-]", "", tin).upper()
        code = jurisdiction_code.strip().upper()
        rule = snapshot.rules.get(code)
        if snapshot.variants and code in {key[0] for key in snapshot.variants}:
            rule = snapshot.variants.get((code, holder_type or "", tin_type or ""))
            if rule is None:
                return [
                    AuditIssue(
                        code="UNSUPPORTED_TIN_TYPE",
                        severity="WARNING",
                        field="tin_type",
                        message="请补充受支持的主体和 TIN 标识类型以便复核",
                        confidence=1.0,
                    )
                ]

        if rule is None:
            return [] if 4 <= len(value) <= 30 else self._invalid("未配置法域的 TIN 长度必须为 4-30 位")
        if rule.pattern.fullmatch(value) is None:
            return self._invalid("TIN 格式不符合当前规则。请核对后重新提交")
        if not OPERATORS[rule.algorithm](value):
            return self._invalid("TIN 校验位或标识类型不符合当前规则。请核对后重新提交")
        return []

    @staticmethod
    def _invalid(message: str) -> list[AuditIssue]:
        return [AuditIssue(code="INVALID_TIN", severity="BLOCKER", field="tin", message=message, confidence=1.0)]
