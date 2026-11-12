import { create } from 'zustand';
import type { CRSFormData, DemoCase, TaskResponse } from '../types/api';
import { DEMO_CASES } from '../data/cases';
import { uuid } from '../api/client';

/**
 * 审核工作台全局状态（Zustand）。
 * 仅保留：当前 Case、当前会话、当前任务、会话内任务历史（用于补正对比）。
 */

/** 流水线五步骤（对齐 UI 线框图） */
export const PIPELINE_STEPS = [
  { key: 'receive', title: '接收材料' },
  { key: 'extract', title: '多模态提取' },
  { key: 'validate', title: '税规推理校验' },
  { key: 'conflict', title: '跨源冲突研判' },
  { key: 'verdict', title: '决策与闭环' },
] as const;

export interface SucceededTaskRecord {
  task: TaskResponse;
  caseId: string;
  submittedAt: string;
}

/** 接口模式：async=异步任务（默认公开接口）；sync=同步校验（doc 队友接入接口） */
export type ApiMode = 'async' | 'sync';

interface AuditState {
  /** 当前选中的预置样本 */
  activeCase: DemoCase;
  /** 接口模式 */
  apiMode: ApiMode;
  /** 当前审核会话 UUID（同一会话内的补正复用，用于补正对比） */
  sessionId: string;
  /** 当前任务（进行中或最近一次终态；同步模式为适配展示的包装对象） */
  currentTask: TaskResponse | null;
  /** 当前任务对应的 Case（区分历史任务） */
  currentCaseId: string | null;
  /** 最近一次实际提交的表单数据（上传/样例场景与 activeCase 可能不同） */
  submittedFormData: CRSFormData | null;
  /** 最近一次提交的数据来源标签（如 doc 样例 / 上传文件名） */
  submittedLabel: string | null;
  /** 提交中的幂等键（展示用） */
  idempotencyKey: string | null;
  /** 是否正在提交/轮询 */
  running: boolean;
  /** 流水线当前推进到第几步（0-5，SUCCEEDED 后为 5） */
  pipelineProgress: number;
  /** 本次会话内已成功完成的任务历史（补正对比的 before 候选） */
  succeededHistory: SucceededTaskRecord[];

  selectCase: (caseId: string) => void;
  setApiMode: (mode: ApiMode) => void;
  beginTask: (idempotencyKey: string, submitted: CRSFormData, label?: string | null) => void;
  setPipelineProgress: (step: number) => void;
  completeTask: (task: TaskResponse) => void;
  failTask: (task: TaskResponse | null) => void;
  /** 开始新一轮审核：保留会话（补正场景）或重置会话（切换样本/手动重置） */
  resetForResubmit: () => void;
  resetSession: () => void;
}

export const useAuditStore = create<AuditState>((set, get) => ({
  activeCase: DEMO_CASES[1], // 默认展示 Case B（NEED_USER_FIX，信息最丰富）
  apiMode: 'async',
  sessionId: uuid(),
  currentTask: null,
  currentCaseId: null,
  submittedFormData: null,
  submittedLabel: null,
  idempotencyKey: null,
  running: false,
  pipelineProgress: 0,
  succeededHistory: [],

  selectCase: (caseId) => {
    const target = DEMO_CASES.find((c) => c.case_id === caseId);
    if (!target) return;
    // 切换样本即开启全新会话
    set({
      activeCase: target,
      sessionId: uuid(),
      currentTask: null,
      currentCaseId: null,
      submittedFormData: null,
      submittedLabel: null,
      idempotencyKey: null,
      running: false,
      pipelineProgress: 0,
      succeededHistory: [],
    });
  },

  setApiMode: (mode) =>
    set({
      apiMode: mode,
      currentTask: null,
      currentCaseId: null,
      submittedFormData: null,
      submittedLabel: null,
      idempotencyKey: null,
      running: false,
      pipelineProgress: 0,
    }),

  beginTask: (idempotencyKey, submitted, label = null) =>
    set({
      running: true,
      idempotencyKey,
      submittedFormData: submitted,
      submittedLabel: label,
      pipelineProgress: 1, // 材料已接收
      currentTask: null,
    }),

  setPipelineProgress: (step) =>
    set((state) => ({ pipelineProgress: Math.max(state.pipelineProgress, step) })),

  completeTask: (task) => {
    const { currentCaseId, succeededHistory } = get();
    const record: SucceededTaskRecord = {
      task,
      caseId: currentCaseId ?? '-',
      submittedAt: task.created_at,
    };
    const already = succeededHistory.some((r) => r.task.task_id === task.task_id);
    set({
      currentTask: task,
      running: false,
      pipelineProgress: PIPELINE_STEPS.length,
      succeededHistory: already ? succeededHistory : [...succeededHistory, record],
    });
  },

  failTask: (task) =>
    set({
      currentTask: task,
      running: false,
      pipelineProgress: 2, // 失败时停留在校验阶段附近
    }),

  resetForResubmit: () =>
    set({
      currentTask: null,
      submittedFormData: null,
      submittedLabel: null,
      idempotencyKey: null,
      running: false,
      pipelineProgress: 0,
      // 保留 sessionId 与 succeededHistory —— 补正场景
    }),

  resetSession: () =>
    set({
      sessionId: uuid(),
      currentTask: null,
      submittedFormData: null,
      submittedLabel: null,
      idempotencyKey: null,
      running: false,
      pipelineProgress: 0,
      succeededHistory: [],
    }),
}));
