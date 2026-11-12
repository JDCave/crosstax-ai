import { useCallback, useEffect, useRef } from 'react';
import { App } from 'antd';
import { getTask, submitTask } from '../api/tasks';
import { validateSync } from '../api/validate';
import { ApiError, uuid } from '../api/client';
import { useAuditStore } from '../stores/auditStore';
import { today } from '../data/cases';
import type { DemoCase, TaskResponse, ValidationRequest, ValidationResponse } from '../types/api';

/** 活动任务轮询间隔（后端建议 poll_after_ms=500 / Retry-After=1s，此处取 800ms） */
const POLL_INTERVAL_MS = 800;
/** 前端轮询超时（与后端 RULE_TASK_TIMEOUT_SECONDS 对齐并留余量） */
const POLL_TIMEOUT_MS = 45_000;

function isTerminal(status: TaskResponse['status']): boolean {
  return status === 'SUCCEEDED' || status === 'FAILED';
}

/** 同步校验结果 → 包装为 TaskResponse 形态，供全部展示组件统一消费 */
function wrapSyncResult(result: ValidationResponse, sessionId: string): TaskResponse {
  const now = new Date().toISOString();
  return {
    task_id: 'sync',
    session_id: sessionId,
    status: 'SUCCEEDED',
    created_at: now,
    deadline_at: now,
    expires_at: now,
    started_at: now,
    completed_at: now,
    rule_version_id: result.rule_version_id,
    rule_revision: result.rule_revision,
    engine_build_id: result.execution?.engine_build_id ?? 'sync',
    poll_after_ms: 0,
    comparison: null,
    report_status: null,
    report_error: null,
    report_url: null,
    result,
    error: null,
  };
}

/** 业务错误码 → 用户友好提示 */
function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'NO_ACTIVE_RULES':
        return '规则引擎尚未发布活动规则，请先在数据库中初始化并激活规则（503）';
      case 'RULE_ENGINE_UNAVAILABLE':
        return '规则引擎存储不可用（503），请确认数据库与 Worker 已启动后重试';
      case 'TASK_ENCRYPTION_UNAVAILABLE':
        return '服务端未配置任务加密密钥 RULE_TASK_ENCRYPTION_KEYS（503）';
      case 'TASK_QUEUE_FULL':
        return '规则引擎任务队列已满（503），请稍后重试';
      case 'VALIDATION_ERROR': {
        const first = err.details?.[0];
        return first
          ? `请求结构无效（422）：${first.field} — ${first.message}`
          : '请求结构无效（422），请检查表单 JSON 字段';
      }
      case 'TASK_SUBMISSION_TIMEOUT':
        return '任务提交超时（503），已按同幂等键安全重试';
      default:
        return `${err.message}（${err.code}）`;
    }
  }
  if (err instanceof TypeError) {
    return '无法连接规则引擎服务，请确认后端已启动（默认 http://localhost:8000）';
  }
  return err instanceof Error ? err.message : '未知错误';
}

export interface RunAuditOptions {
  /** 自定义请求体（上传 JSON / 样例场景）；缺省使用当前 Case 数据 */
  overrideValidation?: ValidationRequest;
  /** 数据来源标签（展示在结果标题，如 doc 样例名 / 上传文件名） */
  label?: string;
}

/**
 * 审核任务编排 Hook：
 * 提交任务 → 轮询至终态 → 写入全局 store；期间驱动流水线动画。
 */
export function useAuditTask() {
  const { message } = App.useApp();
  const timerRef = useRef<number | null>(null);
  const abortedRef = useRef(false);

  const {
    activeCase,
    sessionId,
    running,
    beginTask,
    setPipelineProgress,
    completeTask,
    failTask,
  } = useAuditStore();

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    abortedRef.current = false;
    return () => {
      abortedRef.current = true;
      stopPolling();
    };
  }, [stopPolling]);

  const run = useCallback(
    async (options: RunAuditOptions = {}) => {
      if (running) return;
      const store = useAuditStore.getState();
      const demoCase: DemoCase = store.activeCase;

      const validation: ValidationRequest =
        options.overrideValidation ??
        ({
          form_data: demoCase.form_data,
          policy: { today: today() },
          indicia_issues: demoCase.indicia_issues,
        } satisfies ValidationRequest);

      const idempotencyKey = uuid();
      // 会话 ID 由 store 统一管理：同一会话内的补正复用同一 session_id，便于补正对比
      const taskSessionId = store.sessionId;
      beginTask(
        idempotencyKey,
        validation.form_data as DemoCase['form_data'],
        options.label ?? (options.overrideValidation ? '自定义请求' : null),
      );

      // ---- 同步校验模式（doc/API_INTEGRATION.md：POST /api/v1/rule-engine/validate） ----
      if (store.apiMode === 'sync') {
        try {
          setPipelineProgress(3);
          const result = await validateSync(validation);
          if (abortedRef.current) return;
          setPipelineProgress(4);
          const wrapped = wrapSyncResult(result, taskSessionId);
          useAuditStore.setState({ currentTask: wrapped, currentCaseId: demoCase.case_id });
          window.setTimeout(() => completeTask(wrapped), 350);
        } catch (err) {
          failTask(null);
          message.error(friendlyError(err));
        }
        return;
      }

      // ---- 异步任务模式（默认公开接口：POST /tasks → 轮询 GET /tasks/{id}） ----
      let accepted: TaskResponse;
      try {
        accepted = await submitTask(
          {
            session_id: taskSessionId,
            deadline_at: new Date(Date.now() + 30_000).toISOString(),
            validation,
          },
          idempotencyKey,
        );
      } catch (err) {
        failTask(null);
        message.error(friendlyError(err));
        return;
      }

      if (abortedRef.current) return;

      // 已进入队列：推进到“多模态提取”
      useAuditStore.setState({ currentTask: accepted, currentCaseId: demoCase.case_id });
      setPipelineProgress(2);

      const startedAt = Date.now();
      const poll = async (): Promise<void> => {
        if (abortedRef.current) return;
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          failTask(null);
          message.warning('轮询超时：任务未在预期时间内完成，请确认 Worker 已启动');
          return;
        }
        let task: TaskResponse;
        try {
          task = await getTask(accepted.task_id);
        } catch (err) {
          failTask(null);
          message.error(friendlyError(err));
          return;
        }
        if (abortedRef.current) return;

        useAuditStore.setState({ currentTask: task });

        if (task.status === 'RUNNING') {
          // 执行中：推进到“税规推理校验”
          setPipelineProgress(3);
        }

        if (isTerminal(task.status)) {
          if (task.status === 'SUCCEEDED' && task.result) {
            // 跨源冲突研判步骤完成后进入裁决
            setPipelineProgress(4);
            window.setTimeout(() => completeTask(task), 350);
          } else {
            failTask(task);
            message.error(`任务执行失败：${task.error?.code ?? 'UNKNOWN'} — ${task.error?.message ?? ''}`);
          }
          return;
        }

        const interval = Math.max(POLL_INTERVAL_MS, task.poll_after_ms || 0);
        timerRef.current = window.setTimeout(poll, interval);
      };

      timerRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
    },
    [running, sessionId, activeCase, beginTask, setPipelineProgress, completeTask, failTask, message],
  );

  return { run, running };
}
