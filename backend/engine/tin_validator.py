"""Deterministic TIN checks against an audit-bound rule snapshot."""

from __future__ import annotations

import re
from collections.abc import Callable
from types import MappingProxyType

from backend.engine.checksums import au_abn, ca_sin, es_nif_nie, jp_corporate, nl_mod11, no_orgnr, pl_nip, pl_pesel
from backend.engine.contracts import AuditIssue, TINCheck
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
        "NL_MOD11": nl_mod11,
        "PL_NIP": pl_nip,
        "PL_PESEL": pl_pesel,
        "AU_ABN": au_abn,
        "NO_ORGNR": no_orgnr,
        "JP_CORPORATE": jp_corporate,
        "CA_SIN": ca_sin,
        "ES_NIF_NIE": es_nif_nie,
        "HKID_WEIGHT": hkid_weight,
        "NRIC_WEIGHT": nric_weight,
        "REGEX_ONLY": lambda value: True,
    }
)


class TINValidatorEngine:
    """One evaluation produces issues and a trace; wrappers preserve old callers."""

    def evaluate(
        self,
        tin: str | None,
        jurisdiction_code: str,
        snapshot: RuleSnapshot,
        holder_type: str | None = None,
        tin_type: str | None = None,
        *,
        strict_coverage: bool = False,
    ) -> tuple[list[AuditIssue], TINCheck]:
        code = jurisdiction_code.strip().upper()
        rule = snapshot.variants.get((code, holder_type or "", tin_type or "")) or snapshot.rules.get(code)
        performed = ["rule_selection"]

        def finish(issues: list[AuditIssue], status: str, reason: str) -> tuple[list[AuditIssue], TINCheck]:
            from typing import Literal, cast

            level: Literal["NONE", "FORMAT_ONLY", "CHECKSUM"] = "NONE"
            if "format" in performed:
                level = "FORMAT_ONLY"
            if "checksum" in performed:
                level = "CHECKSUM"
            pending = [name for name in ("format", "checksum") if name not in performed]
            pending.extend(("issuance", "ownership", "tax_residency"))
            return issues, TINCheck(
                status=cast(Literal["PASSED", "FAILED", "NOT_COVERED", "NOT_APPLICABLE"], status),
                verification_level=level,
                rule_id=rule.rule_id if rule else None,
                source_url=rule.source_url if rule else None,
                algorithm_source_url=rule.algorithm_source_url if rule else None,
                checks_performed=tuple(performed),
                checks_not_performed=tuple(pending),
                reason_code=reason,
            )

        if tin is None or len(tin) > 256:
            return finish(self._invalid("TIN 缺失或长度超出允许范围"), "FAILED", "INVALID_INPUT")
        value = re.sub(r"[\s()\-]", "", tin).upper()
        performed.append("normalization")
        if rule is None:
            country_known = code in snapshot.rules or any(key[0] == code for key in snapshot.variants)
            if snapshot.variants or strict_coverage:
                issue_code = "UNSUPPORTED_TIN_TYPE" if country_known else "UNSUPPORTED_JURISDICTION"
                field = "tin_type" if country_known else "jurisdiction_code"
                return finish(
                    [
                        AuditIssue(
                            code=issue_code,
                            severity="WARNING",
                            field=field,
                            message="规则未覆盖该主体或标识类型。需要人工复核",
                            confidence=1.0,
                        )
                    ],
                    "NOT_COVERED",
                    issue_code,
                )
            performed.append("legacy_length_fallback")
            issues = [] if 4 <= len(value) <= 30 else self._invalid("未配置法域的 TIN 长度必须为 4-30 位")
            return finish(issues, "NOT_COVERED", "LEGACY_LENGTH_FALLBACK")
        performed.append("format")
        if rule.pattern.fullmatch(value) is None:
            return finish(self._invalid("TIN 格式不符合当前规则。请核对后重新提交"), "FAILED", "FORMAT_MISMATCH")
        if rule.algorithm != "REGEX_ONLY":
            performed.append("checksum")
            if not OPERATORS[rule.algorithm](value):
                return finish(
                    self._invalid("TIN 校验位或标识类型不符合当前规则。请核对后重新提交"), "FAILED", "CHECKSUM_MISMATCH"
                )
        return finish([], "PASSED", "CHECKS_PASSED")

    def validate(
        self,
        tin: str | None,
        jurisdiction_code: str,
        snapshot: RuleSnapshot,
        holder_type: str | None = None,
        tin_type: str | None = None,
    ) -> list[AuditIssue]:
        return self.evaluate(tin, jurisdiction_code, snapshot, holder_type, tin_type)[0]

    def trace(
        self, tin: str | None, code: str, snapshot: RuleSnapshot, holder_type: str | None, tin_type: str | None
    ) -> TINCheck:
        return self.evaluate(tin, code, snapshot, holder_type, tin_type)[1]

    @staticmethod
    def _invalid(message: str) -> list[AuditIssue]:
        return [AuditIssue(code="INVALID_TIN", severity="BLOCKER", field="tin", message=message, confidence=1.0)]
