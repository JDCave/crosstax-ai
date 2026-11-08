"""Validate upstream D3 facts without flattening away fields or inventing extraction evidence."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.engine.contracts import AuditIssue, ExecutionContext, TINCheck, ValidationPolicy
from backend.engine.document_contracts import CheckItem, IssueOrigin, ResidenceResult, ReviewScope
from backend.engine.document_validation import DocumentResult
from backend.engine.reproducibility import canonical_hash, engine_build_id
from backend.engine.rule_loader import RuleSnapshot
from backend.engine.structured_contracts import FormData
from backend.engine.tin_validator import TINValidatorEngine
from backend.engine.verdict import resolve_verdict


def normalized_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value).isoformat()
        if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
            day, month, year = map(int, value.split("/"))
            return date(year, month, day).isoformat()
    except ValueError:
        pass
    return None


class FormPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1]
    policy_revision_date: str
    source_kind: Literal["PROJECT_REQUIREMENT"]
    source_reference: str = Field(min_length=1)
    reason_b_min_length: int = Field(ge=1, le=4000)
    required_fields: dict[str, list[str]]
    entity_types: list[str] = Field(min_length=1)
    passive_entity_type: str
    trusted_link_confidences: list[str] = Field(min_length=1)
    country_codes: list[str] = Field(min_length=1)
    country_code_source: dict[str, str]
    poem_holder_types: list[str] = Field(min_length=1)
    power_of_attorney_capacities: list[str] = Field(min_length=1)
    declared_non_poa_capacities: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_required_groups(self) -> FormPolicy:
        if set(self.required_fields) != {"INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON"}:
            raise ValueError("Missing holder policy")
        if any(not fields or any(not path.strip() for path in fields) for fields in self.required_fields.values()):
            raise ValueError("Empty required-field policy")
        return self


def load_form_policy() -> tuple[dict[str, Any], str]:
    path = Path(__file__).resolve().parents[2] / "rules/hk/form_policy.json"
    with path.open("rb") as stream:
        content = stream.read(65537)
    if len(content) > 65536:
        raise ValueError("Form policy exceeds size limit")
    config = FormPolicy.model_validate_json(content)
    date.fromisoformat(config.policy_revision_date)  # Software policy revision, not a legal effective date.
    data = config.model_dump(mode="json")
    return data, canonical_hash(data)


def validate_structured(
    form: FormData,
    policy: ValidationPolicy,
    snapshot: RuleSnapshot,
    upstream: list[AuditIssue],
    form_policy: tuple[dict[str, Any], str] | None = None,
) -> DocumentResult:
    birth_date = normalized_date(form.birth_date)
    signing_date = normalized_date(form.declaration.signing_date)
    updates: dict[str, Any] = {}
    if birth_date is not None:
        updates["birth_date"] = birth_date
    if signing_date is not None:
        updates["declaration"] = form.declaration.model_copy(update={"signing_date": signing_date})
    form = form.model_copy(update=updates)
    config, policy_id = form_policy if form_policy is not None else load_form_policy()
    issues: list[AuditIssue] = []
    items: list[CheckItem] = []
    residences: list[ResidenceResult] = []

    def add(code: str, field: str, message: str, severity: Literal["BLOCKER", "WARNING"] = "BLOCKER") -> int:
        issues.append(AuditIssue(code=code, field=field, message=message, severity=severity, confidence=1.0))
        return len(issues) - 1

    def check(
        identifier: str, field: str, failed: bool, message: str, severity: Literal["BLOCKER", "WARNING"] = "BLOCKER"
    ) -> None:
        indexes = [add(identifier, field, message, severity)] if failed else []
        status = "FAILED" if failed and severity == "BLOCKER" else "REVIEW_REQUIRED" if failed else "PASSED"
        items.append(CheckItem(check_id=identifier + ":" + field, field=field, status=status, issue_indexes=indexes))

    def value_at(path: str) -> Any:
        value: Any = form
        for part in path.split("."):
            value = getattr(value, part, None)
            if value is None:
                return None
        return value

    def blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    check(
        "MULTI_HOLDER_DOCUMENT",
        "document.holders_declared",
        form.document.holders_declared != 1,
        "每位持有人须单独提交表格, 不能按税籍或控权人重复组计数",
    )
    if form.document.holders_declared != 1:
        return finish(form, policy, snapshot, policy_id, issues, items, residences, upstream)
    check(
        "STRUCTURE_TREE_UNAVAILABLE",
        "document.structure_tree_available",
        not form.document.structure_tree_available,
        "上游未提供结构树, 字段归属需要复核",
        "WARNING",
    )
    check(
        "DOCUMENT_FINGERPRINT_MISSING",
        "document.fingerprint",
        blank(form.document.fingerprint),
        "缺少原始文档指纹, 无法核查抽取证据来源",
        "WARNING",
    )
    for field in config["required_fields"][form.holder_type]:
        check("MISSING_REQUIRED_FIELD", field, blank(value_at(field)), "请补充该必填字段")
    if form.holder_type != "ENTITY":
        check(
            "INVALID_BIRTH_DATE",
            "birth_date",
            not blank(form.birth_date) and normalized_date(form.birth_date) is None,
            "出生日期须为有效 YYYY-MM-DD 或 dd/mm/yyyy",
        )
    residence_addresses = [address for address in form.addresses if address.type == "RESIDENCE"]
    check("INVALID_RESIDENCE_ADDRESS_COUNT", "addresses", len(residence_addresses) != 1, "必须提供一项现居或营业地址")
    check(
        "DUPLICATE_ADDRESS_TYPE",
        "addresses",
        len({address.type for address in form.addresses}) != len(form.addresses),
        "同一类型地址不能重复, 以免静默选取一个",
    )
    for index, address in enumerate(form.addresses):
        check(
            "INVALID_ADDRESS_COUNTRY",
            f"addresses.{index}.country",
            address.country not in config["country_codes"],
            "国家字段须为已登记的 ISO 两位大写地区代码",
        )
        if address.type == "RESIDENCE":
            check("MISSING_ADDRESS_CITY", f"addresses.{index}.city", blank(address.city), "请补充城市")
        check(
            "SOURCE_LAYOUT_ANOMALY",
            f"addresses.{index}.source_layout_anomaly",
            bool(address.source_layout_anomaly),
            "上游标记了原始文档排版异常, 需复核字段归属",
            "WARNING",
        )
    if form.holder_type == "ENTITY":
        entity = form.entity
        check(
            "INVALID_ENTITY_CLASSIFICATION",
            "entity.entity_type",
            entity is None or entity.entity_type not in config["entity_types"],
            "实体须明确选择一个分类",
        )
        if entity is not None:
            check(
                "INCORPORATION_SOURCE_CONFLICT",
                "entity.incorporation_jurisdiction_source",
                entity.incorporation_jurisdiction_source == "BOTH_CONFLICT",
                "上游报告注册地来源冲突, 须保留双方事实复核",
                "WARNING",
            )
            passive = entity.entity_type == config["passive_entity_type"]
            check(
                "MISSING_CONTROLLING_PERSON",
                "entity.controlling_person_names",
                passive and not any(name.strip() for name in entity.controlling_person_names),
                "被动非财务实体须提供控权人; 无自然人控制也不能省略高管信息",
            )
            if passive or entity.no_natural_person_control:
                add(
                    "CROSS_DOCUMENT_VERIFICATION_REQUIRED",
                    "entity.controlling_person_names",
                    "本请求未包含对应控权人文档或高管身份依据, 不能核实回指或人员资格",
                    "WARNING",
                )
    if form.holder_type == "CONTROLLING_PERSON":
        controlled = form.controlling_person.controlled_entities if form.controlling_person else []
        check(
            "MISSING_CONTROLLED_ENTITY",
            "controlling_person.controlled_entities",
            not controlled,
            "控权人须列出至少一个所控实体",
        )
        for index, controlled_entity in enumerate(controlled):
            prefix = f"controlling_person.controlled_entities.{index}"
            check(
                "MISSING_ENTITY_NAME",
                prefix + ".entity_name",
                blank(controlled_entity.entity_name),
                "请填写所控实体名称",
            )
            check(
                "MISSING_CP_TYPE",
                prefix + ".cp_types",
                not controlled_entity.cp_types or not all(t.strip() for t in controlled_entity.cp_types),
                "请按每个实体分别填写控权人类型",
            )
            check(
                "UNCONFIRMED_ENTITY_LINK",
                prefix + ".linked_document_ref",
                blank(controlled_entity.linked_document_ref)
                or controlled_entity.link_confidence not in config["trusted_link_confidences"],
                "缺少可靠文档关联, 不得把低置信链接当作已确认",
                "WARNING",
            )
        if controlled and any(
            not entity.linked_document_ref or entity.link_confidence not in config["trusted_link_confidences"]
            for entity in controlled
        ):
            add(
                "CROSS_DOCUMENT_VERIFICATION_REQUIRED",
                "controlling_person.controlled_entities",
                "仅有链接声明不能核实对方文档, 须由上游跨文档流程提供实际验证依据",
                "WARNING",
            )
    declaration = form.declaration
    check(
        "UNRESOLVED_DECLARATION",
        "declaration.holder_or_authorized_resolved",
        not declaration.holder_or_authorized_resolved,
        "请明确本人签署或获授权代签",
    )
    holder_name = (
        form.name.entity_legal_name
        if form.holder_type == "ENTITY"
        else " ".join(
            [value for value in [form.name.first_name, *form.name.middle_names, form.name.last_name] if value]
        )
    )

    def normalize_name(name: str | None) -> str:
        return " ".join((name or "").casefold().split())

    names = {normalize_name(holder_name)}
    if form.holder_type != "ENTITY":
        names.add(
            normalize_name(
                " ".join(
                    value for value in [form.name.last_name, form.name.first_name, *form.name.middle_names] if value
                )
            )
        )
    different_signer = bool(declaration.signatory_name) and normalize_name(declaration.signatory_name) not in names
    requires_capacity = form.holder_type == "ENTITY" or different_signer
    check(
        "MISSING_SIGNATORY_CAPACITY",
        "declaration.capacity",
        requires_capacity and blank(declaration.capacity),
        "请补充签署人身份或授权资格",
    )
    capacity = normalize_name(declaration.capacity)
    poa = capacity in config["power_of_attorney_capacities"]
    check(
        "MISSING_POWER_OF_ATTORNEY",
        "declaration.power_of_attorney_attached",
        poa and not declaration.power_of_attorney_attached,
        "声明以授权书签署时须附证明副本",
    )
    if requires_capacity and capacity and not poa and capacity not in config["declared_non_poa_capacities"]:
        add(
            "SIGNATORY_CAPACITY_REVIEW_REQUIRED",
            "declaration.capacity",
            "签署身份未被当前术语映射覆盖, 无法判断授权书适用性",
            "WARNING",
        )
    check("NO_SIGNATURE", "declaration.has_signature", not declaration.has_signature, "请补充签名")
    signing = normalized_date(declaration.signing_date)
    check(
        "INVALID_DATE",
        "declaration.signing_date",
        signing is None
        or signing > policy.today.isoformat()
        or bool(policy.earliest_signing_date and signing < policy.earliest_signing_date.isoformat()),
        "请核对签署日期和日期策略",
    )
    holder_type = "ENTITY" if form.holder_type == "ENTITY" else "INDIVIDUAL"
    for index, residence in enumerate(form.tax_residencies):
        start = len(issues)
        prefix = f"tax_residencies.{index}"
        valid_country = residence.jurisdiction in config["country_codes"]
        if not valid_country:
            add("INVALID_JURISDICTION", prefix + ".jurisdiction", "税籍地区须为已登记的 ISO 两位大写代码")
        tin = residence.tin
        has_tin = bool(tin and tin.strip())
        if has_tin and (residence.no_tin_reason is not None or residence.reason_b_explanation):
            add("INCONSISTENT_TIN_DECLARATION", prefix + ".no_tin_reason", "TIN 与无 TIN 理由不能同时填写")
        if residence.basis == "POEM":
            if form.holder_type not in config["poem_holder_types"]:
                add("POEM_NOT_APPLICABLE", prefix + ".basis", "当前主体类型不适用实体实际管理地申报")
            if not form.entity or form.entity.poe_jurisdiction != residence.jurisdiction:
                add("POEM_DECLARATION_MISMATCH", "entity.poe_jurisdiction", "实际管理地事实须与独立 POEM 申报相符")
            add(
                "POEM_REVIEW_REQUIRED",
                prefix + ".basis",
                "实际管理地已保留为独立申报事实, 不等同于税收居民身份",
                "WARNING",
            )
            trace = TINCheck(
                status="NOT_APPLICABLE",
                verification_level="NONE",
                checks_performed=("declaration_basis",),
                checks_not_performed=("poem_applicability", "tax_residency"),
                reason_code="POEM_REVIEW_REQUIRED",
            )
        elif not has_tin:
            if residence.no_tin_reason is None:
                add("MISSING_REASON", prefix + ".no_tin_reason", "无税号时须填写 A/B/C")
            if (
                residence.no_tin_reason == "B"
                and len((residence.reason_b_explanation or "").strip()) < config["reason_b_min_length"]
            ):
                add("MISSING_REASON", prefix + ".reason_b_explanation", "请补充无法取得税号的具体原因")
            add("EXEMPTION_REVIEW_REQUIRED", prefix + ".no_tin_reason", "仅检查豁免声明完整性, 适用性未核实", "WARNING")
            trace = TINCheck(
                status="NOT_APPLICABLE",
                verification_level="NONE",
                checks_performed=("exemption_declaration_completeness",),
                checks_not_performed=("exemption_applicability", "issuance", "ownership", "tax_residency"),
                reason_code="EXEMPTION_REVIEW_REQUIRED",
            )
        else:
            tin_type = ("HK_BR" if holder_type == "ENTITY" else "HKID") if residence.jurisdiction == "HK" else None
            candidates = [key[2] for key in snapshot.variants if key[:2] == (residence.jurisdiction, holder_type)]
            if tin_type is None and len(candidates) == 1:
                tin_type = candidates[0]
            found, trace = TINValidatorEngine().evaluate(
                tin, residence.jurisdiction, snapshot, holder_type, tin_type, strict_coverage=True
            )
            for issue in found:
                issues.append(
                    issue.model_copy(
                        update={
                            "field": prefix + "." + ("jurisdiction" if issue.field == "jurisdiction_code" else "tin")
                        }
                    )
                )
            if residence.jurisdiction == "HK":
                identity = form.hk_identity
                reference = (
                    (identity.business_registration_number if holder_type == "ENTITY" else identity.hkid_or_passport)
                    if identity
                    else None
                )
                source_field = "hk_identity." + (
                    "business_registration_number" if holder_type == "ENTITY" else "hkid_or_passport"
                )

                def normal(value: str | None) -> str:
                    return re.sub(r"[\s()\-]", "", value or "").upper()

                identity_start = len(issues)
                if not reference or not reference.strip():
                    add("HK_IDENTITY_EVIDENCE_MISSING", source_field, "缺少独立证件字段, 无法执行香港 TIN 派生等值检查")
                    trace = trace.model_copy(
                        update={
                            "status": "NOT_COVERED" if trace.status == "PASSED" else trace.status,
                            "reason_code": "HK_IDENTITY_EVIDENCE_MISSING",
                            "checks_not_performed": (*trace.checks_not_performed, "hk_identity_equality"),
                        }
                    )
                else:
                    trace = trace.model_copy(
                        update={"checks_performed": (*trace.checks_performed, "hk_identity_equality")}
                    )
                    if normal(reference) != normal(tin):
                        add("HK_TIN_IDENTITY_MISMATCH", prefix + ".tin", f"请核对本字段与 {source_field}, 两来源不一致")
                        trace = trace.model_copy(update={"status": "FAILED", "reason_code": "HK_TIN_IDENTITY_MISMATCH"})
                identity_indexes = list(range(identity_start, len(issues)))
                items.append(
                    CheckItem(
                        check_id=f"hk_identity_equality:{index}",
                        field=prefix + ".tin",
                        status="FAILED" if identity_indexes else "PASSED",
                        issue_indexes=identity_indexes,
                    )
                )
        indexes = list(range(start, len(issues)))
        residences.append(
            ResidenceResult(
                index=index,
                jurisdiction_code=residence.jurisdiction if valid_country else "",
                checks=trace,
                issue_indexes=indexes,
            )
        )
        items.append(
            CheckItem(
                check_id=f"tax_residence:{index}",
                field=prefix,
                status="FAILED"
                if any(issues[i].severity == "BLOCKER" for i in indexes)
                else "REVIEW_REQUIRED"
                if indexes
                else "PASSED",
                issue_indexes=indexes,
            )
        )
    return finish(form, policy, snapshot, policy_id, issues, items, residences, upstream)


def finish(
    form: FormData,
    policy: ValidationPolicy,
    snapshot: RuleSnapshot,
    policy_id: str,
    issues: list[AuditIssue],
    items: list[CheckItem],
    residences: list[ResidenceResult],
    upstream: list[AuditIssue],
) -> DocumentResult:
    all_issues = [*issues, *upstream]
    scope = ReviewScope()
    scope.evaluated = ["document_holder_cardinality"]
    if form.document.holders_declared != 1:
        scope.not_evaluated.append("remaining_checks_after_document_rejection")
    else:
        scope.evaluated.extend(
            [
                "structured_identity_and_address_fields",
                "signature_presence_declaration",
                "date_format",
                "signing_date_policy",
                "tin_declaration_consistency",
                "declaration_capacity",
            ]
        )
        for operation in (
            "rule_selection",
            "hk_identity_equality",
            "exemption_declaration_completeness",
            "declaration_basis",
        ):
            if any(operation in r.checks.checks_performed for r in residences):
                scope.evaluated.append(operation)
    scope.not_evaluated.extend(
        [
            "cross_document_counterpart_verification",
            "ownership_threshold_applicability",
            "regulatory_effective_date_applicability",
            "power_of_attorney_applicability",
            "controlled_person_type_legal_classification",
            "financial_institution_addressee_verification",
            "document_reference_number_verification",
            "independent_kyc_fact_comparison",
        ]
    )
    return DocumentResult(
        rule_version_id=snapshot.version_id,
        rule_revision=snapshot.revision,
        tin_check=None,
        execution=ExecutionContext(
            engine_build_id=engine_build_id(),
            policy=policy,
            form_policy_id=policy_id,
            input_fingerprint=canonical_hash(
                {
                    "form": form.model_dump(mode="json", exclude_unset=True),
                    "policy": policy.model_dump(mode="json"),
                    "indicia_issues": [i.model_dump(mode="json") for i in upstream],
                    "form_policy_id": policy_id,
                }
            ),
        ),
        form_issues=tuple(issues),
        indicia_issues=tuple(upstream),
        verdict=resolve_verdict(all_issues),
        residence_results=residences,
        check_items=items,
        issue_origins=[
            IssueOrigin(
                issue_index=i, source="RULE_ENGINE" if i < len(issues) else "UPSTREAM", evidence_ref=f"issue:{i}"
            )
            for i in range(len(all_issues))
        ],
        review_scope=scope,
    )
