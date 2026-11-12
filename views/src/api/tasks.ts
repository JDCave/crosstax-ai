import { request, uuid } from './client';
import type { TaskRequest, TaskResponse } from '../types/api';

/**
 * 规则引擎异步任务 API
 * 见 backend/api/RULE_TASKS_API.md
 */

/** 提交校验任务（202 Accepted）。幂等键由调用方生成并在传输重试时复用。 */
export function submitTask(payload: TaskRequest, idempotencyKey: string): Promise<TaskResponse> {
  return request<TaskResponse>('/api/v1/rule-engine/tasks', {
    method: 'POST',
    body: payload,
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

/** 轮询任务状态；compareTo 传入同会话旧任务 UUID 时返回补正前后对比。 */
export function getTask(taskId: string, compareTo?: string, signal?: AbortSignal): Promise<TaskResponse> {
  const query = compareTo ? `?compare_to=${encodeURIComponent(compareTo)}` : '';
  return request<TaskResponse>(`/api/v1/rule-engine/tasks/${taskId}${query}`, { signal });
}

/** PDF 审计报告下载地址（仅 report_status === 'READY' 时可用） */
export function reportDownloadUrl(taskId: string): string {
  return `/api/v1/rule-engine/tasks/${taskId}/report`;
}

/** 任务请求辅助：生成一次提交所需的会话/幂等键与截止时间 */
export function buildTaskContext(timeoutSeconds = 30): {
  sessionId: string;
  idempotencyKey: string;
  deadlineAt: string;
} {
  return {
    sessionId: uuid(),
    idempotencyKey: uuid(),
    deadlineAt: new Date(Date.now() + timeoutSeconds * 1000).toISOString(),
  };
}
