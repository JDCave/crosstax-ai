# CrossTax AI — 项目 TODO 清单

> 从 PM 视角出发，覆盖需求、设计、实现、部署四个阶段。
> 本清单不绑定具体时间线，按依赖关系排序。

---

## 一、需求阶段 (Requirements)

### 1.1 需求整合与确认

- [x] 将 `crosstax-ai-solution (from ppt).md` 和 `business-workflow-design.md` 整合为正式 PRD，归档至 `specs/` → 已完成：`specs/crosstax-ai-prd.md`
- [ ] 明确 MVP 交付范围 —— 区分竞赛必演示能力 vs 加分项
- [ ] 定义目标用户角色（商户、合规官、系统管理员）及各角色的核心场景
- [ ] 编写用户故事（User Stories），覆盖五步审核流水线的每条主路径
- [ ] 定义验收标准（Acceptance Criteria），每个用户故事附带可测试的通过条件

### 1.2 数据与规则需求

- [ ] 确认首批覆盖法域列表（CN / HK / SG 等）及各国 TIN 格式规则来源
- [ ] 定义 CRS 自证表单的完整字段清单与数据格式（对照方案中的 CRSFormData）
- [ ] 定义 Mock 商户底表数据结构（incorporation_jurisdiction, bank_settlement_country 等）
- [ ] 确定 5 个典型 Case 的测试场景（覆盖 AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE 三态）
- [ ] 明确 Reason A/B/C 豁免逻辑树的完整规则

### 1.3 非功能需求

- [ ] 定义性能指标：单次审核端到端响应时间目标
- [ ] 定义安全需求：传输加密、存储加密、RBAC、数据最小化
- [ ] 定义审计合规需求：审计记录不可篡改、规则版本绑定、全链路溯源

---

## 二、设计阶段 (Design)

### 2.1 系统架构设计

- [x] 整体技术架构设计（前后端分层、模块划分），输出架构图至 `design/` → `design/architecture-overview.html` + `.md`
- [x] 多智能体串联架构设计 —— 明确各 Agent 的输入/输出/职责边界 → 架构文档 §2.2
- [x] 规则引擎热重载机制设计（JSON 配置 → 内存原子替换，无需重启） → 架构文档 §2.3.2
- [x] 审计留痕数据模型设计（Session Snapshot 结构、规则版本绑定） → 架构文档 §2.2.1
- [x] 技术选型确认 —— **已确认：后端 Python + FastAPI，前端 React 18 + TypeScript**（2026-10-22 团队沟通决策）
- [ ] 前后端接口契约定义（OpenAPI 3.0 Schema） → 输出至 `design/openapi.yaml`

### 2.2 核心模块设计

- [x] 媒体预处理流水线设计（PDF 栅格化 / 图像 EXIF 纠正 / 尺寸缩放 / Base64 编码）
- [x] Vision Parser Agent Prompt 设计（抽取字段定义、输出 JSON Schema、置信度策略） → CRSFormData 见架构文档 §2.2.1
- [x] TIN 校验引擎设计（清洗 → 正则匹配 → 算子分发 → 兜底策略） → 架构文档 §2.3.1
- [x] 跨源冲突研判逻辑设计（三种冲突场景的判定规则与置信度评分） → 架构文档 §2.3.3
- [x] 三态裁决器状态机设计（BLOCKER → NEED_USER_FIX / WARNING → MANUAL_TRIAGE / PASS → AUTO_PASS） → 架构文档 §2.3.4
- [ ] 审计报告模板设计（Jinja2 → HTML/PDF，字段与布局） → **待实现**

### 2.3 接口与交互设计

- [x] 内部模块间接口定义（Agent 间数据传递格式） → 架构文档 §2.2.2
- [x] 外部 Vision API 集成接口封装设计 → 架构文档 §2.2.2
- [x] 前后端 REST API 接口设计（FastAPI + OpenAPI） → 架构文档 §2.1
- [x] WebSocket 实时通信设计（流水线状态推送） → 架构文档 §2.1
- [x] React UI 设计规范 → `design/react-ui-spec.md`
  - 样本选择与文件预览区
  - 规则同步模拟区
  - 实时研判看板（WebSocket 驱动）
  - 修复卡片区
  - 审计底稿查阅区

---

## 三、实现阶段 (Implementation)

### 3.1 工程基础设施

- [ ] 后端工程初始化（`backend/` 目录、FastAPI 应用骨架、依赖管理 `requirements.txt`、代码规范）
- [ ] 前端工程初始化（`frontend/` 目录、Vite + React 18 + TypeScript、Ant Design 集成、ESLint/Prettier）
- [ ] Docker Compose 开发环境编排（前后端联调）
- [ ] Mock 数据准备：商户底表 `mock_merchants.json`
- [ ] Mock 数据准备：5 个 CRS 样本表单（PDF / 图片）
- [ ] 规则配置文件编写：`rules_v1_base.json`（CN / HK / SG 等核心法域）
- [ ] 规则补丁文件编写：`rules_v2_patch.json`（演示热重载用）
- [ ] OpenAPI 契约文件编写：`design/openapi.yaml`

### 3.2 后端核心模块开发（Python + FastAPI）

- [ ] FastAPI 应用骨架 + 路由注册（`backend/main.py`）
- [ ] Pydantic 请求/响应模型（`backend/api/schemas/`）
- [ ] REST API 路由：`/api/v1/audit`、`/api/v1/rules`、`/api/v1/cases`
- [ ] WebSocket 端点：`/ws/audit/{session_id}` 实时推送流水线状态
- [ ] CORS 配置（允许前端开发服务器跨域）
- [ ] 媒体预处理模块 —— PDF 解析（pdf2image）、图像清洗（EXIF 纠正、缩放）
- [ ] Vision Parser Agent —— 调用 Vision API，输出结构化 CRSFormData
- [ ] TIN 规则引擎 —— 正则匹配 + 校验位算法（MOD11_2 / HKID_WEIGHT / NRIC_WEIGHT / REGEX_ONLY）
- [ ] 规则热重载引擎 —— `engine.load_rules(path)` 原子替换
- [ ] 形式完备性校验 —— 签名判定、签署日期校验、Reason A/B/C 逻辑闭环
- [ ] 跨源冲突研判模块 —— 三种冲突场景检测 + 置信度评分
- [ ] 三态裁决器 —— 汇总 FormIssues + IndiciaIssues，输出最终裁决
- [ ] 审计留痕引擎 —— 会话快照固化（会话ID / 商户ID / 文件哈希 / 规则版本 / 时间戳）
- [ ] 审计报告生成 —— Jinja2 模板渲染 HTML/PDF 底稿

### 3.3 前端 SPA 开发（React + TypeScript）

- [ ] Layout 框架搭建（Header + Sider + Content）
- [ ] Axios 客户端封装 + API 模块（audit / rules / cases）
- [ ] WebSocket Hook 封装（`useAuditStream`）
- [ ] 文件上传组件（react-dropzone + Ant Design Upload）
- [ ] 样本选择与 Case 切换组件
- [ ] PipelineStatus 流水线状态组件（Ant Design Steps + WebSocket 驱动）
- [ ] VerdictBanner 裁决横幅（Alert 组件，按裁决类型切换语义）
- [ ] RemediationCard 修复卡片（Collapse 组件，字段级提示）
- [ ] ConflictEvidence 冲突证据链（Descriptions + Progress 展示置信度）
- [ ] AuditTrail 审计底稿 + 报告下载
- [ ] RuleReload 规则热重载演示

### 3.4 测试

- [ ] 后端各模块单元测试（TIN 校验、冲突判定、裁决逻辑）
- [ ] 后端 API 路由测试（FastAPI TestClient）
- [ ] 前端组件单元测试（Vitest + React Testing Library）
- [ ] 5 个典型 Case 端到端集成测试（前后端联调）
- [ ] 边界条件测试（未配置法域的兜底策略、空文件、损坏 PDF）
- [ ] 热重载验证（加载 v2 补丁后规则即时生效，无需重启）
- [ ] WebSocket 实时推送验证（流水线状态无延迟）
- [ ] 审计完整性验证（报告可穿透溯源至原始文件 + 规则版本）

---

## 四、部署阶段 (Deployment)

### 4.1 云基础设施

- [ ] 阿里云资源规划与开通（ECS / 容器服务 / 存储 / 网络）
- [ ] 应用容器化（Dockerfile 编写）
- [ ] 部署流水线配置（代码推送 → 构建 → 部署）
- [ ] 环境变量与配置管理（API Key、规则路径等敏感配置外置）

### 4.2 安全加固

- [ ] HTTPS / TLS 传输加密
- [ ] 数据存储加密
- [ ] RBAC 权限控制（合规官 / 管理员角色隔离）
- [ ] 数据最小化与留存策略配置

### 4.3 竞赛演示准备

- [ ] Demo 环境部署与冒烟测试
- [ ] 演示脚本编写（覆盖三态裁决的完整流程）
- [ ] 演示数据走查（5 个 Case 全部可正常演示）
- [ ] 热重载演示环节准备（一键加载 OECD 规则补丁）
- [ ] 团队预演与排错

---

## 文档归档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| 方案原始需求（PPT 摘要） | `docs/crosstax-ai-solution (from ppt).md` | 原始 Proposal |
| 业务流程架构 | `docs/business-workflow-design.md` | 团队业务专家输出 |
| 项目 TODO 清单 | `docs/project-todo.md` | 本文件 |
| PRD（已完成） | `specs/crosstax-ai-prd.md` | 正式需求规格 v1.1 |
| 架构蓝图（已完成） | `design/architecture-overview.html` | 四层分层架构可视化 |
| 架构设计文档（已完成） | `design/architecture-overview.md` | ADR、数据模型、接口契约、部署方案（v1.1） |
| React UI 设计规范（已完成） | `design/react-ui-spec.md` | 组件、布局、色彩、交互规范 |
| 前后端接口契约（待完成） | `design/openapi.yaml` | OpenAPI 3.0 Schema |
| 代码 | `backend/` + `frontend/` | 实现代码 |
| Mock 数据 | `assets/` | 样本数据与规则配置 |
