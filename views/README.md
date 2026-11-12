# CrossTax AI — 前端工作台（views）

合规审核工作台单页应用，对齐 `design/ui-spec.md` 与 `design/prototypes/react-ui-wireframe.html`。

**技术栈：** React 18 + TypeScript（strict）+ Vite 5 + Ant Design 5 + Zustand + TanStack Query + React Router v6

## 功能总览

| 区域 | 实现 | 对应契约 |
| --- | --- | --- |
| 接口模式 | 异步任务（默认公开接口）/ 同步校验（doc 队友接入接口）一键切换 | `POST /tasks` / `POST /validate` |
| 样本选择 | 5 个预置 Case（A–E）一键切换，镜像 `assets/mock-data/cases.json` | — |
| doc 官方样例 | 一键载入 `crs-individual-request.json` / `crs-entity-request.json` 并提交 | `POST /tasks` 或 `/validate` |
| 请求上传 | 拖拽上传 `doc/crs-templates` 中 `crs-*-request.json` 格式文件直接提交 | 同上 |
| 流水线状态 | 五步 Steps：接收材料 → 多模态提取 → 税规推理校验 → 跨源冲突研判 → 决策与闭环 | 任务轮询驱动 |
| 裁决横幅 | AUTO_PASS 绿 / NEED_USER_FIX 红 / MANUAL_TRIAGE 琥珀三态 Alert | `result.verdict` |
| 表单数据表 | 实际提交的 CRSFormData 字段表，命中 issue 的字段按严重级着色 | `result.issues` |
| 修复卡片 | BLOCKER 折叠卡片，优先展示后端 `explanation_cards`（含规则/Agent 建议） | `result.explanation_cards` |
| 冲突证据链 | WARNING/上游 indicia 高亮 + 置信度进度条 + 来源标记 | `result.issue_origins` |
| 校验明细 | check_items 逐项 + TIN 状态/校验深度 + 审查范围声明 | `result.check_items` / `checks` / `review_scope` |
| 审计底稿 | 会话/任务快照、规则版本、输入指纹一键复制；PDF 报告下载（异步模式） | `GET /tasks/{id}/report` |
| 补正对比 | 同会话两次成功任务对比（已解决/新引入/仍存在，异步模式） | `GET /tasks/{id}?compare_to=` |
| 规则热重载演示 | `/demo/rule-upgrade` 页展示模拟补丁 before/after、用例迁移、规则差异与风险，保留 SIMULATION 标记 | `GET /demo/upgrade-impact` |

### 两种接口模式

| | 异步任务（默认） | 同步校验 |
| --- | --- | --- |
| 接口 | `POST /api/v1/rule-engine/tasks` + 轮询 | `POST /api/v1/rule-engine/validate` |
| 文档 | `backend/api/RULE_TASKS_API.md` | `doc/crs-templates/API_INTEGRATION.md` |
| 返回 | 202 Accepted → 轮询取结果 | 一次请求直接返回 |
| PDF 报告 | ✅ report READY 后下载 | ❌ |
| 补正对比 | ✅ `compare_to` | ❌ |
| 依赖 | API + Worker + 加密密钥 | 仅 API + 活动规则 |

> 注意：**所有裁决结果均由后端规则引擎实时计算**，前端不写死任何校验结论；
> 预置的 5 个 Case 与 2 份 doc 样例仅为请求输入（与后端测试用例及 doc 官方样例镜像一致）。

## 快速开始

### 1. 启动前端

```bash
cd views
npm install
npm run dev        # http://localhost:5173
```

开发服务器已配置代理：`/api` → `http://localhost:8000`（可用环境变量 `VITE_API_TARGET` 覆盖）。

### 2. 启动后端（规则引擎 API + Worker）

前端依赖后端三条公开接口，完整启动见 `backend/api/RULE_TASKS_API.md`，最小步骤：

```bash
# 项目根目录（crosstax-ai）
uv sync --frozen
uv run alembic upgrade head

# 生成任务加密密钥并写入 .env（RULE_TASK_ENCRYPTION_KEYS=["生成的密钥"]）
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 终端一：API 服务
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 终端二：任务 Worker（不启动则任务永远 PENDING）
uv run python -m backend.workers.rule_tasks
```

首次使用还需发布活动规则（否则提交返回 `503 NO_ACTIVE_RULES`），初始化方式见 `backend/api/COMPETITION_API.md`。

### 3. 可选开关

```dotenv
# 规则热重载演示页数据（只读模拟，不影响真实规则）
RULE_DEMO_ENABLED=true
```

## 构建与检查

```bash
npm run typecheck   # TypeScript strict 检查
npm run build       # tsc --noEmit && vite build → dist/
npm run preview     # 预览生产构建
```

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VITE_API_TARGET` | `http://localhost:8000` | 开发时代理目标 |
| `VITE_API_BASE` | `''`（同源代理） | 生产构建时的 API 基地址 |

## 目录结构

```
views/src/
├── main.tsx                  # 入口（QueryClientProvider）
├── App.tsx                   # 主题令牌 + HashRouter + Layout
├── api/
│   ├── client.ts             # fetch 封装 + ApiError（对齐后端 ErrorResponse）
│   ├── tasks.ts              # 任务提交 / 轮询 / 报告下载地址
│   └── demo.ts               # 规则升级演示（只读）
├── components/
│   ├── layout/               # AppHeader / AppSider
│   ├── PipelineSteps.tsx     # 五步流水线
│   ├── VerdictBanner.tsx     # 三态裁决横幅
│   ├── CrsDataTable.tsx      # 表单数据表
│   ├── RemediationCards.tsx  # BLOCKER 修复卡片
│   ├── ConflictEvidence.tsx  # WARNING 冲突证据链
│   ├── ValidationChecks.tsx  # 校验明细
│   └── AuditTrail.tsx        # 审计底稿 + PDF 下载 + 补正对比
├── pages/
│   ├── AuditPage.tsx         # 主审核页
│   └── UpgradeDemoPage.tsx   # 规则热重载演示页
├── hooks/useAuditTask.ts     # 提交 → 轮询 → 终态编排
├── stores/auditStore.ts      # Zustand 全局状态
├── types/api.ts              # 与后端契约对齐的 TS 类型
└── data/cases.ts             # 5 个预置样本（镜像 mock-data/cases.json）
```

## 注意事项

- **SUCCEEDED ≠ AUTO_PASS**：任务成功仅表示执行完成，裁决必须读取 `result.verdict`。
- **幂等键**：每次提交生成新 UUID 作为 `Idempotency-Key`；补正提交复用同一会话 `session_id` 以支持补正对比。
- **演示标记**：规则升级页数据为只读模拟（`simulation=true`），UI 已保留 SIMULATION 标记，不代表真实规则变更。
- **审查范围**：TIN 校验为 FORMAT_ONLY 时仅表示格式校验，UI 已按文档提示不代表号码签发真实性。
- 当前 UI 使用单税收居民地区契约（`CRSFormData`），与 `doc/API_INTEGRATION.md` 一致。
