import { request } from './client';
import type { ValidationRequest, ValidationResponse } from '../types/api';

/**
 * 同步校验接口（doc/crs-templates/API_INTEGRATION.md 描述的队友接入方式）：
 *   POST /api/v1/rule-engine/validate
 * 一次请求直接返回完整校验结果，无任务轮询、无 PDF 报告、无补正对比。
 * 注意：后端默认公开接口为异步任务 API，此同步接口为保留的兼容入口。
 */
export function validateSync(validation: ValidationRequest, signal?: AbortSignal): Promise<ValidationResponse> {
  return request<ValidationResponse>('/api/v1/rule-engine/validate', {
    method: 'POST',
    body: validation,
    signal,
  });
}
