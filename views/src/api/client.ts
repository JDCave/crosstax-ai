import type { ErrorResponse } from '../types/api';

/**
 * 统一 API 客户端。
 * 默认走 Vite 代理（/api -> http://localhost:8000），
 * 生产环境可通过 VITE_API_BASE 指向规则引擎服务。
 */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '';

/** 后端业务错误（ErrorResponse 结构） */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: ErrorResponse['details'];

  constructor(status: number, code: string, message: string, details?: ErrorResponse['details']) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details ?? null;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let code = `HTTP_${response.status}`;
  let message = response.statusText || '请求失败';
  let details: ErrorResponse['details'] | undefined;
  try {
    const body = (await response.json()) as Partial<ErrorResponse>;
    if (typeof body.code === 'string') code = body.code;
    if (typeof body.message === 'string') message = body.message;
    if (body.details) details = body.details as ErrorResponse['details'];
  } catch {
    // 非 JSON 错误体（如 502 网关页面），保留默认信息
  }
  return new ApiError(response.status, code, message, details);
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = options;
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    signal,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

/** 生成 UUID（幂等键 / 会话 ID），优先使用加密安全实现 */
export function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
