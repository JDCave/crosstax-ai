"""Offline, bounded PDF presentation of an already completed rule-engine task."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

from backend.api.schemas.rule_tasks import TaskResponse

TEMPLATE_VERSION = "crs-rule-report-v1"
FONT_NAME = "CrossTaxSansSC"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_PAGES = 100
MAX_PDF_BYTES = 8 * 1024 * 1024
FONT_LOCK = threading.Lock()
VERDICTS = {"AUTO_PASS": "已执行规则检查通过", "NEED_USER_FIX": "需要补正", "MANUAL_TRIAGE": "需要人工复核"}
CHECK_LABELS = {
    "MULTI_HOLDER_DOCUMENT": "持有人数量",
    "STRUCTURE_TREE_UNAVAILABLE": "文档结构证据",
    "DOCUMENT_FINGERPRINT_MISSING": "文档指纹",
    "MISSING_REQUIRED_FIELD": "必填字段",
    "INVALID_DOB": "出生日期",
    "INVALID_RESIDENCE_ADDRESS_COUNTRY": "居住地址国家",
    "DUPLICATE_ADDRESS_COUNTRY": "重复地址国家",
    "INVALID_ADDRESS_COUNTRY": "地址国家代码",
    "MISSING_ADDRESS_CITY": "地址城市",
    "SOURCE_LAYOUT_ANOMALY": "提取版式一致性",
    "UNRESOLVED_DECLARATION": "声明人身份",
    "MISSING_SIGNATORY_CAPACITY": "签署身份",
    "MISSING_POWER_OF_ATTORNEY": "授权签署依据",
    "NO_SIGNATURE": "签署声明",
    "INVALID_DATE": "签署日期",
    "hk_identity_equality": "香港身份字段一致性",
    "tax_residence": "税籍及标识规则",
}
CHECK_STATUSES = {"PASSED": "通过", "FAILED": "未通过", "REVIEW_REQUIRED": "待复核", "NOT_APPLICABLE": "不适用"}


class ReportTooLarge(Exception):
    """Export limits exceeded; never return a truncated report."""


@dataclass(frozen=True)
class ReportData:
    task: TaskResponse
    validation: dict[str, Any]


@lru_cache(maxsize=1)
def registered_font() -> TTFont:
    with FONT_LOCK:
        font = TTFont(FONT_NAME, str(Path(__file__).parent / "fonts/CrossTaxSansSC-Regular.ttf"))
        pdfmetrics.registerFont(font)
        return font


def printable(text: str) -> str:
    """Preserve unsupported characters explicitly instead of producing silent tofu glyphs."""
    widths = registered_font().face.charWidths
    return "".join(
        char
        if char == "\n" or (ord(char) >= 32 and ord(char) in widths)
        else (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        for char in text
    )


def display(value: object) -> str:
    if value is None:
        return "未提供"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_report(data: ReportData) -> bytes:
    task, validation = data.task, data.validation
    result = task.result
    if result is None:
        raise ValueError("Completed report requires a result")
    registered_font()
    snapshot = {
        "task": task.model_dump(mode="json", exclude={"result", "poll_after_ms"}),
        "validation": validation,
        "result": result.model_dump(mode="json"),
    }
    canonical = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(canonical.encode("ascii")) > MAX_SNAPSHOT_BYTES:
        raise ReportTooLarge()
    if len(result.issues) + len(result.check_items) + len(result.residence_results) > 5000:
        raise ReportTooLarge()
    snapshot_hash = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    navy, teal = colors.HexColor("#17324D"), colors.HexColor("#087F8C")
    body = ParagraphStyle(
        "body",
        fontName=FONT_NAME,
        fontSize=9,
        leading=14,
        textColor=navy,
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=5,
        splitLongWords=True,
    )
    title = ParagraphStyle("title", parent=body, fontSize=23, leading=32, spaceAfter=10)
    heading = ParagraphStyle(
        "heading", parent=body, fontSize=13, leading=20, spaceBefore=13, spaceAfter=7, textColor=teal, keepWithNext=True
    )
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=11, textColor=colors.HexColor("#536779"))
    code = ParagraphStyle("code", parent=small, fontSize=7, leading=10)
    story: list[Any] = []  # ReportLab's heterogeneous Flowable API has no type annotations.

    def paragraph(text: object, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(escape(printable(display(text))).replace("\n", "<br/>"), style))

    def section(text: str) -> None:
        paragraph(text, heading)

    paragraph("规则引擎校验报告", title)
    paragraph("CrossTax AI · CRS Rule Validation", small)
    paragraph(f"{VERDICTS[result.verdict]}  |  {result.verdict}", heading)
    paragraph(result.review_scope.statement)
    paragraph("本报告记录规则引擎已完成的检查。主流程仍需汇总抽取及跨源核验后作最终审核裁决。", small)
    form = validation["form_data"]
    section("01 / 主体与任务")
    name = form.get("holder_name")
    if not name:
        parts = form.get("name", {})
        name = " ".join(
            str(part)
            for part in [parts.get("first_name"), *parts.get("middle_names", []), parts.get("last_name")]
            if part
        )
    paragraph(f"主体:{display(name)}")
    paragraph(f"主体类型:{display(form.get('holder_type'))}")
    value: object
    for label, value in [
        ("任务编号", task.task_id),
        ("主会话编号", task.session_id),
        ("完成时间 UTC", task.completed_at),
        ("规则版本", task.rule_version_id),
        ("发布 revision", task.rule_revision),
        ("任务构建", task.engine_build_id),
    ]:
        paragraph(f"{label}:{display(value)}", small)
    if result.execution:
        for label, value in [
            ("校验构建", result.execution.engine_build_id),
            ("输入指纹", result.execution.input_fingerprint),
            ("表单策略", result.execution.form_policy_id),
            ("业务日期", result.execution.policy.today),
        ]:
            paragraph(f"{label}:{display(value)}", small)
    document = form.get("document", {})
    if document.get("fingerprint"):
        paragraph(f"上游原文件指纹:{document['fingerprint']}", small)
    paragraph(f"报告模板:{TEMPLATE_VERSION}", small)
    paragraph(f"报告源快照 SHA-256:{snapshot_hash}", small)
    section(f"02 / 问题与证据 · {len(result.issues)} 项")
    origins = {origin.issue_index: origin for origin in result.issue_origins}
    if not result.issues:
        paragraph("本次已执行的规则检查未产生问题;未核实范围见后文。")
    for index, issue in enumerate(result.issues):
        paragraph(f"{index + 1}. [{issue.severity}] {issue.code}")
        paragraph(issue.message)
        origin = origins.get(index)
        paragraph(f"字段:{display(issue.field)} | 置信度:{issue.confidence}", small)
        if origin:
            paragraph(f"来源:{origin.source} | 证据:{origin.evidence_ref}", small)
        story.append(Spacer(1, 5))
    section("03 / 税籍与规则出处")
    if not result.residence_results:
        paragraph("无逐税籍结果;完整检查字段保留于 JSON 附录。")
    for residence in result.residence_results:
        check = residence.checks
        paragraph(f"第 {residence.index + 1} 项 · {residence.jurisdiction_code} · {check.status}")
        paragraph(f"验证深度:{check.verification_level} | 规则:{display(check.rule_id)}", small)
        for label, value in [
            ("官方规则出处", check.source_url),
            ("算法出处", check.algorithm_source_url),
            ("已执行", list(check.checks_performed)),
            ("未执行", list(check.checks_not_performed)),
            ("原因", check.reason_code),
        ]:
            paragraph(f"{label}:{display(value)}", small)
    section(f"04 / 逐项检查 · {len(result.check_items)} 项")
    for check_item in result.check_items:
        label = CHECK_LABELS.get(check_item.check_id.split(":")[0], check_item.check_id)
        status = CHECK_STATUSES[check_item.status]
        paragraph(
            f"[{status}] {label} | {check_item.field} | issue:{check_item.issue_indexes}",
            small,
        )
    section("05 / 执行范围")
    paragraph("已执行:" + display(result.review_scope.evaluated))
    paragraph("未核实:" + display(result.review_scope.not_evaluated))
    paragraph(result.review_scope.statement)
    section("06 / 补正建议")
    guidance = result.guidance
    paragraph(f"Agent 状态:{guidance.status} | 模型:{display(guidance.model)}", small)
    paragraph(guidance.summary or "本次未请求 AI 补正。")
    for action in guidance.actions:
        paragraph(f"问题 {action.issue_index}:{action.instruction}")
        paragraph(f"字段:{display(action.field)} | 引用:{display(action.evidence_refs)}", small)
    if guidance.omitted_action_count:
        paragraph(f"Agent 省略建议 {guidance.omitted_action_count} 项;完整问题均已保留。")
    story.append(PageBreak())
    section("附录 / 输入与完整结果快照")
    paragraph("以下 JSON 按展示宽度换行。Unicode 转义保留原字符;不附密钥或完整监管规则包。", small)
    paragraph("源快照摘要算法:对象键排序、ASCII Unicode 转义、无额外空格的 JSON,按 ASCII 字节计算 SHA-256。", small)
    raw_lines = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, indent=2).splitlines()
    widths = {chr(i): pdfmetrics.stringWidth(chr(i), FONT_NAME, code.fontSize) for i in range(32, 127)}
    lines: list[str] = []
    for line in raw_lines:
        segment, width = "", 0.0
        for char in line:
            char_width = widths.get(char, code.fontSize)
            if width + char_width > A4[0] - 84 and segment:
                lines.append(segment)
                segment, width = "", 0.0
            segment += char
            width += char_width
        lines.append(segment)
    for start in range(0, len(lines), 45):
        story.append(Preformatted("\n".join(lines[start : start + 45]), code))

    def decorate(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        if doc.page > MAX_PAGES:
            raise ReportTooLarge()
        canvas.saveState()
        canvas.setFont(FONT_NAME, 7)
        canvas.setFillColor(navy)
        canvas.drawString(42, A4[1] - 29, "CrossTax AI / CRS")
        canvas.drawRightString(A4[0] - 42, A4[1] - 29, printable("内部校验资料"))
        canvas.setStrokeColor(teal)
        canvas.line(42, A4[1] - 36, A4[0] - 42, A4[1] - 36)
        canvas.setFillColor(colors.HexColor("#536779"))
        canvas.drawString(42, 25, f"{str(task.task_id)[:8]} / {TEMPLATE_VERSION}")
        canvas.drawRightString(A4[0] - 42, 25, f"{doc.page}")
        canvas.restoreState()

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=51,
        bottomMargin=43,
        title="CrossTax AI Rule Validation Report",
        author="CrossTax AI",
        subject=f"Task {task.task_id}",
        invariant=1,
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    pdf = output.getvalue()
    if len(pdf) > MAX_PDF_BYTES:
        raise ReportTooLarge()
    return pdf
