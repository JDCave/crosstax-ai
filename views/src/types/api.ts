/**
 * CrossTax AI 前端类型定义
 * 与后端契约对齐：
 *  - backend/engine/contracts.py        (AuditIssue / CRSFormData / ValidationPolicy / TINCheck / ExecutionContext)
 *  - backend/engine/document_contracts.py (CheckItem / IssueOrigin / ResidenceResult / ReviewScope)
 *  - backend/api/schemas/rule_engine.py   (ValidationRequest / ValidationResponse / ErrorResponse)
 *  - backend/api/schemas/rule_tasks.py    (TaskRequest / TaskResponse)
 *  - backend/api/schemas/presentation.py  (ExplanationCard / TaskComparison)
 *  - backend/api/schemas/competition.py + engine/impact.py (UpgradeDemo / ImpactReport)
 */

// ---------------------------------------------------------------------------
// 基础枚举
// ---------------------------------------------------------------------------

export type Verdict = 'AUTO_PASS' | 'NEED_USER_FIX' | 'MANUAL_TRIAGE';
export type Severity = 'BLOCKER' | 'WARNING';
export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
export type ReportStatus = 'PENDING' | 'RUNNING' | 'READY' | 'FAILED';
export type TinCheckStatus = 'PASSED' | 'FAILED' | 'NOT_COVERED' | 'NOT_APPLICABLE';
export type VerificationLevel = 'FORMAT_ONLY' | 'CHECKSUM' | 'NONE';
export type CheckItemStatus = 'PASSED' | 'FAILED' | 'REVIEW_REQUIRED' | 'NOT_APPLICABLE';

// ---------------------------------------------------------------------------
// 表单与校验请求
// ---------------------------------------------------------------------------

export interface AuditIssue {
  code: string;
  severity: Severity;
  field: string | null;
  message: string;
  confidence: number;
}

/** 单税收居民地区 CRS 表单（当前 UI 仅使用单地区契约） */
export interface CRSFormData {
  holder_name: string;
  holder_dob?: string | null;
  incorporation_date?: string | null;
  residence_address: string;
  jurisdiction_code: string;
  holder_type?: 'INDIVIDUAL' | 'ENTITY' | null;
  tin_type?: string | null;
  tin?: string | null;
  has_no_tin: boolean;
  tin_reason_code?: 'A' | 'B' | 'C' | null;
  tin_reason_explanation?: string | null;
  has_signature: boolean;
  signing_date?: string | null;
}

export interface ValidationPolicy {
  /** 业务日期 YYYY-MM-DD */
  today: string;
  earliest_signing_date?: string | null;
  strict_coverage?: boolean;
}

export interface ValidationRequest {
  form_data: CRSFormData;
  policy: ValidationPolicy;
  indicia_issues: AuditIssue[];
  include_guidance?: boolean;
}

// ---------------------------------------------------------------------------
// 校验响应
// ---------------------------------------------------------------------------

export interface TINCheck {
  status: TinCheckStatus;
  verification_level: VerificationLevel;
  rule_id: string | null;
  source_url: string | null;
  algorithm_source_url: string | null;
  checks_performed: string[];
  checks_not_performed: string[];
  reason_code: string | null;
}

export interface ExecutionContext {
  engine_build_id: string;
  form_policy_id: string | null;
  input_fingerprint: string;
  policy: ValidationPolicy;
}

export interface CheckItem {
  check_id: string;
  field: string;
  status: CheckItemStatus;
  issue_indexes: number[];
}

export interface IssueOrigin {
  issue_index: number;
  source: 'RULE_ENGINE' | 'UPSTREAM';
  evidence_ref: string;
}

export interface ResidenceResult {
  index: number;
  jurisdiction_code: string;
  checks: TINCheck;
  issue_indexes: number[];
}

export interface ReviewScope {
  statement: string;
  evaluated: string[];
  not_evaluated: string[];
}

export interface RuleEvidence {
  jurisdiction_code: string;
  rule_id: string | null;
  source_url: string | null;
  verification_level: string;
}

export interface ExplanationCard {
  issue_index: number;
  title: string;
  severity: Severity;
  field: string | null;
  reason: string;
  action: string;
  action_source: 'RULE' | 'AGENT';
  origin: 'RULE_ENGINE' | 'UPSTREAM';
  evidence_refs: string[];
  rule_evidence: RuleEvidence[];
  confidence: number;
}

export interface ValidationResponse {
  verdict: Verdict;
  issues: AuditIssue[];
  rule_version_id: string;
  rule_revision: number;
  checks: TINCheck | null;
  execution: ExecutionContext | null;
  residence_results: ResidenceResult[];
  check_items: CheckItem[];
  issue_origins: IssueOrigin[];
  review_scope: ReviewScope;
  guidance: unknown;
  explanation_cards: ExplanationCard[];
}

// ---------------------------------------------------------------------------
// 异步任务
// ---------------------------------------------------------------------------

export interface TaskError {
  code: string;
  message: string;
}

export interface FindingSummary {
  code: string;
  field: string | null;
  severity: string;
  origin: string;
  count: number;
}

export interface TaskComparison {
  before_task_id: string;
  after_task_id: string;
  before_verdict: string;
  after_verdict: string;
  context: 'SAME_CONTEXT' | 'DIFFERENT_CONTEXT';
  context_changes: string[];
  changed_field_count: number;
  changed_fields: string[];
  changed_fields_truncated: boolean;
  resolved: FindingSummary[];
  introduced: FindingSummary[];
  remaining: FindingSummary[];
  findings_truncated: boolean;
  statement: string;
}

export interface TaskResponse {
  task_id: string;
  session_id: string;
  status: TaskStatus;
  created_at: string;
  deadline_at: string;
  expires_at: string;
  started_at: string | null;
  completed_at: string | null;
  rule_version_id: string;
  rule_revision: number;
  engine_build_id: string;
  poll_after_ms: number;
  comparison: TaskComparison | null;
  report_status: ReportStatus | null;
  report_error: TaskError | null;
  report_url: string | null;
  result: ValidationResponse | null;
  error: TaskError | null;
}

export interface TaskRequest {
  session_id: string;
  deadline_at?: string | null;
  validation: ValidationRequest;
}

// ---------------------------------------------------------------------------
// 错误响应
// ---------------------------------------------------------------------------

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

export interface ErrorResponse {
  code: string;
  message: string;
  details?: FieldError[] | null;
}

// ---------------------------------------------------------------------------
// 规则升级演示（模拟，只读）
// ---------------------------------------------------------------------------

export interface RuleChange {
  selector: [string, string, string];
  change: 'ADDED' | 'REMOVED' | 'MODIFIED';
  execution_changed: boolean;
  changed_fields: string[];
}

export interface ImpactCaseSummary {
  verdict: Verdict;
  findings: Array<{ code: string; field: string | null; severity: Severity }>;
  upstream_issue_count: number;
  residences: Array<{
    index: number;
    jurisdiction_code: string;
    status: TinCheckStatus;
    verification_level: VerificationLevel;
    reason_code: string | null;
  }>;
}

export interface ImpactCaseRow {
  case_id: string;
  changed: boolean;
  before: ImpactCaseSummary;
  after: ImpactCaseSummary;
}

export interface ImpactReport {
  base_version_id: string;
  candidate_version_id: string;
  base_revision: number;
  engine_build_id: string;
  policy: ValidationPolicy;
  suite_hash: string;
  sample_count: number;
  changed_case_count: number;
  transitions: Record<string, number>;
  rule_changes: RuleChange[];
  cases: ImpactCaseRow[];
  risks: string[];
  report_hash: string;
  form_policy_id: string | null;
}

export interface UpgradeDemo {
  simulation: boolean;
  statement: string;
  impact: ImpactReport;
}

// ---------------------------------------------------------------------------
// 预置样本（前端本地镜像 assets/mock-data/cases.json）
// ---------------------------------------------------------------------------

export interface DemoCase {
  case_id: string;
  title: string;
  description: string;
  merchant_id: string;
  expected_verdict: Verdict;
  expected_before_reload?: Verdict;
  form_data: CRSFormData;
  indicia_issues: AuditIssue[];
}
