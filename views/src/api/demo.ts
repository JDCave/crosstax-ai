import { request } from './client';
import type { UpgradeDemo } from '../types/api';

/**
 * 规则升级演示 API（只读模拟，需后端 RULE_DEMO_ENABLED=true）
 * 见 backend/api/COMPETITION_API.md
 * 注意：返回 simulation=true，展示时必须保留“模拟演示”标记。
 */
export function getUpgradeImpact(signal?: AbortSignal): Promise<UpgradeDemo> {
  return request<UpgradeDemo>('/api/v1/rule-engine/demo/upgrade-impact', { signal });
}
