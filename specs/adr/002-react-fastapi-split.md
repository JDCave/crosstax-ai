# ADR-002: React + FastAPI 前后端分离

## 状态
已采纳 (2026-10-22)

## 背景
最初方案使用 Streamlit 作为 UI 框架，但竞赛评审对工程化能力有加分要求。

## 决策
采用 React 18 + TypeScript 前端 + FastAPI 后端的前后端分离架构，单仓库（monorepo）管理。

## 否决方案
- **Streamlit**：定制性有限，无法实现复杂交互与组件化；竞赛评审对工程化能力有加分
- **Vue**：团队更熟悉 React 生态，Ant Design 组件库更丰富

## 理由
- React 生态成熟、交互体验更佳
- FastAPI 天然适配 Python AI 生态，自动生成 OpenAPI Schema
- 可展示团队全栈工程能力，竞赛加分
- 单仓库减少跨 repo 同步开销（4 人团队）

## 后果
- 需额外开发 FastAPI API 层（约 350 行）
- 前端开发周期约 6.5 人天
- 目标部署形态：Dockerfile 多阶段构建，前端编译产物由 FastAPI 静态托管，实现单容器部署
- 依赖管理：后端 `pyproject.toml` + `uv`（见 ADR-001），前端 `frontend/package.json` + npm

## 实现状态
- 后端已落地：`backend/`（FastAPI 应用工厂 + lifespan + CORS + 全局异常处理 + `/health`、`/ready` 探针）
- `Dockerfile` 现为 uv 多阶段构建的**后端单服务**镜像（非 root 运行 + 健康检查），前端构建阶段待 `frontend/` 落地后接入
- 前端尚未创建：仓库内无 `frontend/` 目录，本决策的前端部分仍待实施
