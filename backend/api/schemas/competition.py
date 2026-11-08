"""Opt-in setup and read-only competition simulation API contracts."""

from pydantic import BaseModel, ConfigDict

from backend.engine.impact import ImpactReport


class InitializationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InitializationResult(BaseModel):
    migration_revision: str
    table_count: int
    sources_added: int
    bundled_rule_version_id: str
    active_rule_version_id: str | None
    active_revision: int
    active_rule_preserved: bool
    next_steps: list[str]


class UpgradeDemo(BaseModel):
    simulation: bool = True
    statement: str = "合成演示用例和模拟规则补丁,不代表最新官方法规;不切换实际活动规则"
    impact: ImpactReport
