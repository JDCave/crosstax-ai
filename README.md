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
├── design/                 # 设计文档
│   ├── architecture-overview.html   # 系统架构蓝图
│   ├── architecture-overview.md     # 架构设计文档
│   ├── streamlit-ui-wireframe.html  # UI 线框图
│   └── streamlit-ui-spec.md         # UI 设计规范
├── docs/                   # 支撑材料
│   ├── business-workflow-design.md  # 业务流程架构
│   ├── crosstax-ai-solution (from ppt).md  # 方案原始需求
│   └── project-todo.md              # 项目 TODO
├── specs/                  # 需求规格
│   └── crosstax-ai-prd.md          # PRD v1.0
└── src/                    # 源代码
    ├── agents/             # 智能体模块
    ├── backend/            # 后端服务
    └── frontend/           # 前端界面
```

## 技术栈

> 待团队确认后更新

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| UI 框架 | Streamlit |
| Vision API | 待确认（通义千问VL / GPT-4o） |
| 规则引擎 | JSON 配置 + 内存热重载 |
| 部署 | 阿里云 ECS + Docker |

## 快速开始

```bash
# 克隆仓库
git clone git@github.com:JDCave/crosstax-ai.git
cd crosstax-ai

# 安装依赖（待实现）
pip install -r requirements.txt

# 启动应用（待实现）
streamlit run src/app.py
```

## 文档导航

| 文档 | 位置 | 说明 |
|------|------|------|
| PRD | `specs/crosstax-ai-prd.md` | 产品需求文档 v1.0 |
| 架构设计 | `design/architecture-overview.md` | 系统架构与 ADR |
| 架构蓝图 | `design/architecture-overview.html` | 可视化架构图 |
| UI 线框图 | `design/streamlit-ui-wireframe.html` | 5 屏交互原型 |
| UI 规范 | `design/streamlit-ui-spec.md` | 布局、组件、色彩规范 |
| 业务流程 | `docs/business-workflow-design.md` | 业务专家流程设计 |
| 方案原始需求 | `docs/crosstax-ai-solution (from ppt).md` | PPT 摘要 |
| 项目 TODO | `docs/project-todo.md` | 四阶段任务清单 |

## 团队

AI Campaign 2026 竞赛团队（4 人）

## 许可证

Private — 竞赛项目
