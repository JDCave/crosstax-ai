# CrossTax AI 前端开发任务清单

> 依据 `doc/crs-templates/API_INTEGRATION.md`、`design/ui-spec.md`、`design/prototypes/react-ui-wireframe.html`、`specs/prd.md` §F8 及 `backend/api/` 接口文档拆分。
> 状态：✅ 已完成 / 🔲 待开发 / ⚠️ 需后端配合

## 阶段一：工程基建（P0）

| # | 任务 | 状态 | 产出 |
| --- | --- | --- | --- |
| 1.1 | Vite + React 18 + TS strict 工程初始化 | ✅ | `package.json` `vite.config.ts` `tsconfig.json` |
| 1.2 | Ant Design 5 集成 + 主题令牌（success#16a34a / error#dc2626 / warning#d97706 / info#2563eb） | ✅ | `App.tsx` ConfigProvider |
| 1.3 | Layout：Header 64px + Sider 260px + Content 24px | ✅ | `components/layout/` |
| 1.4 | API 客户端封装（ErrorResponse 解析、ApiError、UUID） | ✅ | `api/client.ts` |
| 1.5 | TS 类型层对齐后端契约（Task / Validation / Comparison / Demo） | ✅ | `types/api.ts` |

## 阶段二：核心审核流（P0）

| # | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| 2.1 | 任务提交：POST /tasks + Idempotency-Key + deadline_at | ✅ | `useAuditTask.run()` |
| 2.2 | 任务轮询：GET /tasks/{id}，800ms 间隔 + 45s 超时 + poll_after_ms 自适应 | ✅ | 同上 |
| 2.3 | Pipeline 五步 Steps 轮询驱动动画 | ✅ | `PipelineSteps.tsx` |
| 2.4 | VerdictBanner 三态裁决横幅 | ✅ | `VerdictBanner.tsx` |
| 2.5 | 5 个预置 Case 切换（镜像 mock-data/cases.json，含 D 的上游 WARNING） | ✅ | `data/cases.ts` |
| 2.6 | 错误处理：503 NO_ACTIVE_RULES / 422 / 网络不可达等友好提示 | ✅ | `friendlyError()` |
| 2.7 | Zustand 全局状态：当前 Case / 会话 / 任务 / 历史 | ✅ | `stores/auditStore.ts` |

## 阶段三：结果展示（P1）

| # | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| 3.1 | CRSFormData 字段表 + issue 字段级着色 | ✅ | `CrsDataTable.tsx` |
| 3.2 | RemediationCards：BLOCKER 折叠卡片，优先渲染 explanation_cards（RULE/AGENT 来源标签） | ✅ | `RemediationCards.tsx` |
| 3.3 | ConflictEvidence：WARNING 高亮 + 置信度 Progress + 上游/引擎来源 | ✅ | `ConflictEvidence.tsx` |
| 3.4 | ValidationChecks：check_items + TIN 状态 + review_scope 声明 | ✅ | `ValidationChecks.tsx` |
| 3.5 | AuditTrail：快照字段 copyable + 规则版本绑定 | ✅ | `AuditTrail.tsx` |
| 3.6 | PDF 报告下载：report_status READY 时启用，REPORT_GENERATING 提示 | ✅ | `AuditTrail.tsx` |

## 阶段四：竞赛加分项（P1）

| # | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| 4.1 | 请求 JSON 上传（doc/crs-templates 样例格式）解析并提交 | ✅ | `AppSider.tsx` Upload.Dragger |
| 4.2 | 补正前后对比：同会话 succeeded 历史 + compare_to + 差异 Modal | ✅ | `AuditTrail.tsx` |
| 4.3 | 规则热重载演示页：upgrade-impact before/after + 用例迁移 + 规则差异 + 风险标记 + SIMULATION 标记 | ✅ | `UpgradeDemoPage.tsx` |
| 4.4 | 上下文不同时的归因提示（DIFFERENT_CONTEXT 不完全归因用户修复） | ✅ | 对比 Modal 内提示 |
| 4.5 | 同步校验模式：POST /validate（doc 队友接入接口），模式一键切换 | ✅ | `api/validate.ts` + Sider Segmented |
| 4.6 | doc 官方样例一键载入（香港个人版/实体版） | ✅ | `data/sampleRequests.ts` |

## 阶段五：待办与联调（P2）

| # | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| 5.1 | 端到端联调：API + Worker + 初始化规则 + 5 Case + doc 样例 + 补正对比 + PDF | ✅ 12/12 通过 | `scripts_e2e_check.py`（SQLite + global v4） |
| 5.2 | 规则热重载演示联调（RULE_DEMO_ENABLED=true） | ✅ | Case E：MANUAL_TRIAGE→NEED_USER_FIX，5 项 SG 规则 ADDED |
| 5.3 | 单元测试：核心组件与 Hooks（Vitest + Testing Library） | 🔲 | ui-spec §8.3 验收项 |
| 5.4 | 多税籍表单（MultiResidenceForm）与结构化契约（FormData）录入界面 | 🔲 | 后端已支持，前端当前仅单税籍契约 |
| 5.5 | WebSocket 实时流水线（如后端后续提供 /ws 推送） | 🔲 | 当前为轮询模拟推进 |
| 5.6 | 1280×720 分辨率走查 + 可访问性（对比度/键盘导航）复核 | 🔲 | ui-spec §7.3 |
| 5.7 | include_guidance=true 的 AI 修复建议接入（需配置百炼 Key） | 🔲 | 后端 RULE_AI_* 配置后开启 |

## 验收对照（ui-spec §8.3）

- [x] 5 个 Case 可一键切换，主区域自动刷新
- [x] 三态裁决横幅颜色正确（绿/红/琥珀）
- [x] BLOCKER 修复卡片字段级提示
- [x] WARNING 冲突证据链高亮 + 置信度
- [x] TypeScript strict 模式无类型错误（`npm run typecheck` 通过）
- [x] 生产构建通过（`npm run build`，已做 antd/react vendor 分包）
- [x] 端到端：真实后端下 5 Case 三态裁决全覆盖（A=PASS / B,C,E=FIX / D=TRIAGE）
- [x] 同步校验接口（doc 队友接入）双样例 AUTO_PASS + 异常分支（INVALID_TIN / 422）
- [x] 补正对比：NEED_USER_FIX→AUTO_PASS，resolved=1，SAME_CONTEXT
- [x] PDF 报告下载（53 KB，含 SHA256 头）
- [x] 热重载演示接口联通（浏览器实操验证）
- [ ] 单元测试覆盖核心组件（待开发 5.3）

## 联调环境（2026-11-11 已验证）

- 工具链：`D:\workSpace\Project\tools\bin\uv.exe`（uv 0.13.7，清华 PyPI 镜像安装）
- Python：uv 托管 CPython 3.11（南大镜像下载），虚拟环境 `crosstax-ai/.venv`
- 后端：`uv run uvicorn backend.main:app --port 8000` + `uv run python -m backend.workers.rule_tasks`
- 数据库：SQLite（`crosstax.db`），初始化接口已执行（11 表 / 3 来源 / global v4 激活 rev#1），初始化开关已按文档关闭
- 前端：`npm run dev`（5173，代理 /api → 8000）
- 一键联调校验：`uv run python scripts_e2e_check.py`（12 项断言）
