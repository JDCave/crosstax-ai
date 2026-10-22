# CrossTax AI

全球自适应合规审核引擎 — 跨境资金结算与多币种账户税籍合规智能网关。

> AI Campaign 2026 竞赛项目

## 概述

CrossTax AI 以 CRS（共同申报准则）税籍自我证明为切入点，通过多智能体串联审核，实现 CRS 表单的自动识别、校验、冲突研判与分流处置，将合规审核从反复补件转向实时诊断。

**核心能力：**
- 多模态视觉抽取（Vision Agent）
- 全球自适应 TIN 校验引擎（声明式规则 + 热重载）
- 跨源税籍指示冲突研判
- 三态裁决（AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE）
- 不可篡改审计留痕

## 项目结构

```
crosstax-ai/
├── assets/                 # Mock 数据与规则配置
│   ├── mock-data/          # 商户底表、CRS 样本
│   └── templates/          # Jinja2 审计报告模板
├── backend/                # Python 后端服务 (FastAPI)
│   ├── api/                # REST 路由 + WebSocket
│   ├── agents/             # 智能体模块
│   ├── engine/             # 规则引擎 + 数据模型
│   └── main.py             # FastAPI 入口
├── frontend/               # React 前端应用
│   ├── src/
│   │   ├── components/     # UI 组件
│   │   ├── pages/          # 页面
│   │   ├── api/            # API 客户端
│   │   └── hooks/          # 自定义 Hooks
│   └── vite.config.ts
├── design/                 # 设计文档
│   ├── architecture-overview.html   # 系统架构蓝图
│   ├── architecture-overview.md     # 架构设计文档
│   ├── react-ui-spec.md             # React UI 设计规范
│   └── openapi.yaml                 # 前后端接口契约
├── docs/                   # 支撑材料
│   ├── business-workflow-design.md  # 业务流程架构
│   ├── crosstax-ai-solution (from ppt).md  # 方案原始需求
│   └── project-todo.md              # 项目 TODO
├── specs/                  # 需求规格
│   └── crosstax-ai-prd.md          # PRD v1.1
└── tests/                  # 后端 + 前端测试
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端语言 | Python 3.11+ |
| 后端框架 | FastAPI + Uvicorn |
| 前端语言 | TypeScript |
| 前端框架 | React 18 + Vite |
| UI 组件库 | Ant Design 5.x |
| 实时通信 | WebSocket / SSE |
| Vision API | 待确认（通义千问VL / GPT-4o） |
| 规则引擎 | JSON 配置 + 内存热重载 |
| 部署 | 阿里云 ECS + Docker（多阶段构建） |

## 快速开始

### 后端

```bash
cd crosstax-ai

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r backend/requirements.txt

# 启动 FastAPI 服务（开发模式）
uvicorn backend.main:app --reload --port 8000
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### Docker 一键启动

```bash
# 构建并启动（前后端一体化）
docker compose up --build

# 访问
# 前端: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

## 文档导航

| 文档 | 位置 | 说明 |
|------|------|------|
| PRD | `specs/crosstax-ai-prd.md` | 产品需求文档 v1.1 |
| 架构设计 | `design/architecture-overview.md` | 系统架构与 ADR |
| 架构蓝图 | `design/architecture-overview.html` | 可视化架构图 |
| React UI 规范 | `design/react-ui-spec.md` | 组件、布局、色彩规范 |
| 前后端接口契约 | `design/openapi.yaml` | OpenAPI 3.0 Schema |
| 业务流程 | `docs/business-workflow-design.md` | 业务专家流程设计 |
| 方案原始需求 | `docs/crosstax-ai-solution (from ppt).md` | PPT 摘要 |
| Agent 编码规范 | `AGENTS.md` | AI 辅助编码约定 — 所有成员必须遵循 |
| 项目 TODO | `docs/project-todo.md` | 四阶段任务清单 |

## 团队

AI Campaign 2026 竞赛团队（4 人）

## 许可证

Private — 竞赛项目
