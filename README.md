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
│   ├── core/               # 数据库抽象层 + 配置
│   ├── api/                # REST 路由 + WebSocket
│   ├── agents/             # 智能体模块
│   ├── engine/             # 规则引擎 + 数据模型
│   ├── models/             # SQLAlchemy ORM 模型
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
| LLM 平台 | 阿里云神机百炼（Qwen-VL-Max / Qwen-Max / GLM / DeepSeek） |
| 规则引擎 | JSON 配置 + 内存热重载 |
| 数据库（本地开发） | SQLite（Python 内置，零配置） |
| 数据库（生产/测试） | PostgreSQL 16 + pgvector 0.8.0.2（阿里云 RDS，ECS 内网直连） |
| ORM | SQLAlchemy + Alembic |
| 部署 | 阿里云 ECS + Docker（多阶段构建） |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- Git

### 后端

```bash
cd crosstax-ai

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r backend/requirements.txt

# 启动 FastAPI 服务（开发模式，默认使用 SQLite）
uvicorn backend.main:app --reload --port 8000
```

访问 API 文档：http://localhost:8000/docs

### 数据库配置

本地开发**无需安装任何数据库**，Python 内置 SQLite 自动启用。

```bash
# 本地开发（默认 SQLite，零配置）
APP_ENV=development uvicorn backend.main:app --reload

# 切换阿里云 PG（集成测试 / 生产部署）
APP_ENV=testing \
DATABASE_URL=postgresql://user:pass@rm-xxx.pg.rds.aliyuncs.com:5432/crosstax_dev \
uvicorn backend.main:app --reload
```

> **注意：** 阿里云 PG 仅支持 ECS 内网连接，本地开发机无法直连。
> 本地开发请使用默认的 SQLite 模式。
> PG 连接池限制：每人 ≤ 3 连接，团队总上限 30。

### 环境变量配置

在 `backend/.env` 中填写配置：

```bash
# 应用环境（development / testing / production）
APP_ENV=development

# 数据库（development 环境不设置 DATABASE_URL 则自动使用 SQLite）
# DATABASE_URL=postgresql://user:pass@rm-xxx.pg.rds.aliyuncs.com:5432/crosstax_dev
DB_POOL_SIZE=3

# 阿里云神机百炼 API
DASHSCOPE_API_KEY=sk-xxx
VISION_API_MODEL=qwen-vl-max
LLM_API_MODEL=qwen-max

# 安全
SECRET_KEY=your-secret-key
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
| PRD | `specs/crosstax-ai-prd.md` | 产品需求文档 v1.2 |
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
