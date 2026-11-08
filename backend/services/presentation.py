"""Deterministic UI projection. Never creates facts or changes verdicts."""

from backend.api.schemas.presentation import ExplanationCard, RuleEvidence
from backend.api.schemas.rule_engine import ValidationResponse

COPY = {
    "NO_SIGNATURE": ("签署声明缺失", "核实实际签署情况,补充签署信息后重新提交"),
    "INVALID_TIN": ("税号校验未通过", "对照签发材料核对税号及标识类型,不要猜测或自动补造号码"),
    "INVALID_DATE": ("签署日期需要核实", "核对原件日期并修正提取或填写错误"),
    "MISSING_REASON": ("无税号说明不完整", "核实适用原因并补充所需说明"),
    "INDICIA_CONFLICT": ("跨源信息需要复核", "核对冲突资料并提交人工复核,不要直接覆盖原事实"),
}


def explanation_cards(result: ValidationResponse) -> list[ExplanationCard]:
    origins = {item.issue_index: item for item in result.issue_origins}
    actions = (
        {item.issue_index: item for item in result.guidance.actions} if result.guidance.status == "GENERATED" else {}
    )
    cards = []
    for index, issue in enumerate(result.issues):
        title, action = COPY.get(issue.code, ("字段或证据需要核实", "核对对应字段及原始材料后重新提交或人工复核"))
        origin = origins.get(index)
        refs = [origin.evidence_ref if origin else f"issue:{index}"]
        agent = actions.get(index)
        use_agent = agent is not None and f"issue:{index}" in agent.evidence_refs
        if agent is not None and use_agent:
            action, refs = agent.instruction, list(agent.evidence_refs)
        evidence = [
            RuleEvidence(
                jurisdiction_code=item.jurisdiction_code,
                rule_id=item.checks.rule_id,
                source_url=item.checks.source_url,
                verification_level=item.checks.verification_level,
            )
            for item in result.residence_results
            if index in item.issue_indexes
        ]
        cards.append(
            ExplanationCard(
                issue_index=index,
                title=title,
                severity=issue.severity,
                field=issue.field,
                reason=issue.message,
                action=action,
                action_source="AGENT" if use_agent else "RULE",
                origin=origin.source if origin else "RULE_ENGINE",
                evidence_refs=refs,
                rule_evidence=evidence,
                confidence=issue.confidence,
            )
        )
    return cards
