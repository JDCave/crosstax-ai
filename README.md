# CrossTax AI

跨境资金结算与多币种账户税籍合规智能网关。以 CRS（共同申报准则）税籍自我证明为切入点，把合规审核从"反复补件"转为"实时诊断"。

人工多轮补件通常耗时 **3–7 个工作日**，CRS 表单错填率 **>35%**。CrossTax AI 用多智能体串联流水线在秒级给出可解释裁决，并把每一次裁决固化为可穿透溯源的审计底稿。

## 系统裁决什么

输入是一份 CRS 自我证明（PDF / JPG / PNG / WEBP）加一条商户底表档案，输出是三态裁决之一，以及支撑该裁决的完整证据链。

### 五步流水线

| # | 阶段 | 输入 | 产出 |
|---|------|------|------|
| 1 | 接收与媒体标准化 | 单/多页 PDF 或凭证图片 | Base64 标准化单页图像流（PDF 按 300 DPI 栅格化；图像 EXIF 旋转纠正、长边 ≤2048px） |
| 2 | 多模态视觉抽取 | 标准化图像 | `CRSFormData`：主体名称、出生/成立日、常设地址、ISO 2 字码辖区、TIN、`has_no_tin` 与 Reason A/B/C、`has_signature`、`signing_date` |
| 3 | 确定性规则校验 | `CRSFormData` | `FormIssues[]`：形式要件 + TIN 算法 + 豁免理由闭环 |
| 4 | 跨源税籍指示研判 | `FormIssues[]` + 商户底表 | `IndiciaIssues[]`：冲突项 + 风险置信度 |
| 5 | 裁决与审计留痕 | 上述全部 | 三态裁决 + 会话快照 + HTML/PDF 复核底稿 |

每一步的产出即下一步的输入，中间结果全程保留——这既是"可解释分流"的来源，也是审计穿透的前提。

### 严重度到裁决的映射

规则层只产出两种严重度，最终裁决由它们**确定性**导出，不存在模型自由裁量：

| 条件 | 裁决 | 业务动作 |
|------|------|----------|
| 存在任一 `BLOCKER`（TIN 算法失败 / 漏签 / 缺豁免理由） | `NEED_USER_FIX` | 暂缓开户结汇，生成商户补正卡指导在线修正 |
| 无 `BLOCKER`，但存在 `WARNING`（税籍指示冲突） | `MANUAL_TRIAGE` | 推送合规官工作台，高亮矛盾证据链，执行增强型尽职调查 |
| 无任何异常项 | `AUTO_PASS` | 声明自动生效，激活多币种收付账户并放行结汇 |

### TIN 校验：四步，零算法幻觉

1. **清洗** — 按辖区配置动态剥离空格、连字符、括号等干扰符号
2. **形态匹配** — 加载该辖区正则，校验长度与字符集
3. **算子分发** — 调用校验位算子：`MOD11_2` / `HKID_WEIGHT` / `NRIC_WEIGHT` / `REGEX_ONLY`
4. **兜底** — 未配置辖区执行长度与非空基础审查（4~30 位），保证业务不被意外中断

第 3 步失败记 `INVALID_TIN`（`BLOCKER`）。算子集与辖区正则均为声明式配置：规则以 JSON 存放于 `rules/`，经 `engine.load_rules(path)` 原子替换内存字典即秒级生效，无需重启服务（ADR-003）。这是"全球自适应"的实现方式——刻意不走在线抓取官方规则的路径，以解耦爬虫合规与稳定性风险。

### 形式要件与豁免理由闭环

`has_signature == False` → `NO_SIGNATURE`；`signing_date` 晚于系统当前日期或早于合理阈值 → `INVALID_DATE`。申报 `has_no_tin == True` 时强制要求 Reason 代码；选 Reason B 时 `reason_explanation` 必填且长度 ≥5。任一逻辑未闭环记 `MISSING_REASON`（均为 `BLOCKER`）。

### 三种跨源税籍指示冲突

研判层将表单声明与商户底表（`incorporation_jurisdiction` / `primary_operating_country` / `bank_settlement_country` / `phone_country_code`）交叉比对：

1. **单国申报 vs 境外运营** — 仅申报单国税籍，但业务留存境外常设实体或运营仓储（如报 CN、仓储在 GB）
2. **离岸主体税籍隐瞒** — 注册于离岸金融中心（HK/SG/KY），却在 CRS 中隐瞒该辖区税务居民身份
3. **主体名称跨源冲突** — 表单声明姓名与底层 KYC 法定注册主体不一致

命中记 `INDICIA_CONFLICT`（`WARNING`），并附量化风险置信度评分。

### 审计为何不可篡改

每次审核固化为会话快照：`会话ID + 商户ID + 原始文件哈希 + 结构化提取数据 + 命中规则条款出处 + rule_version_id + 裁决时间戳`。

关键在 `rule_version_id` 的强绑定：裁决永远引用它当时依据的那一版规则，因此即使规则此后被热重载，历史结论仍可按当时的规则原文复现。Jinja2 渲染的《CRS 合规复核底稿报告》由此支持全链路穿透溯源至原始文件与规则版本。

## 实现边界

进度更新于 2026-11-08；当前权威台账见 [实施计划的实现现状](.specify/features/001-crs-contract/plan.md)。本地同步合并提交为 `258be94`，远程 push 尚待 GitHub 登录凭据。


队友主线提供工程底座、规范和新契约规划；本 fork 另已实现数据库版本化规则引擎、单接口校验、多税籍、补正 Agent、影响分析与受控后台更新。完整文件上传审核流水线与前端尚未完成。

当前 fork 对未覆盖地区／类型转人工复核，业务日期由调用方提供；TIN 规则来源和验证深度以实际响应为准。上述主线流程描述不替代当前运行契约。

当前可运行接口见 [API 文档](backend/api/README.md)，规则设计见 [规则引擎详细设计](backend/engine/RULE_ENGINE.md)，后台更新见 [运行手册](backend/engine/RULE_UPDATES.md)。

上游 ADR-003 选择 JSON 文件作为规则载体；本 fork 按当前用户要求使用 PostgreSQL 版本存储。此次同步保留两侧设计记录和现有实现，后续架构统一需团队明确；未在合并中切换存储方式。上游新契约规划也不等同于当前接口已经实现。

技术栈选型的逐条依据记录在 `specs/adr/`（10 个 ADR）。其中 ADR-007 有一项待团队裁定的冲突：决策写 `dashscope` SDK，但该依赖未列入 `pyproject.toml`，而现有依赖已含 `httpx`，且 `design/architecture.md` §2.4 将 Vision/LLM 描述为外部 HTTP 调用——按 `AGENTS.md` 约定，新增顶层依赖需团队同意。

## 快速开始

### 运行

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)（包管理器，替代 pip/venv，无需手动 `python -m venv`）与 Git；Docker + Compose 可选，用于一键起 PostgreSQL 16 / Redis 7。

`Makefile` 是命令的规范入口（`make help` 列出全部目标），但 `make` 在 Windows Git Bash 下通常不可用，因此下面直接给出跨平台的 `uv run` 形式：

```bash
uv sync                                                       # 安装依赖，uv 自动创建 .venv
uv run pre-commit install                                     # 安装提交前钩子
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000   # 开发服务器，默认 SQLite，零配置
uv run pytest tests/                                          # 测试；完整门禁另需 ruff check 与 mypy（等价 make check）
```

API 文档 <http://localhost:8000/docs>；探针 <http://localhost:8000/health> 与 <http://localhost:8000/ready>。容器化启动用 `docker compose up --build`（backend + db + redis 三服务，含健康检查与依赖顺序）。

### 数据库

本地开发无需安装任何数据库：缺省即 `sqlite+aiosqlite:///./crosstax.db`。后端切换**只由 `DATABASE_URL` 决定**，`ENVIRONMENT` 仅控制日志与调试开关。

```bash
# 切换 PostgreSQL（引擎为异步，URL 必须带 +asyncpg 驱动前缀）
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/crosstax_dev \
  uv run uvicorn backend.main:app --reload
```

阿里云 RDS PG 仅支持 ECS 内网连接，本地开发机无法直连；需要本地 PG 时用 `docker compose up -d db`（compose 中的 `postgres:16-alpine` 与云上 RDS 不是同一实例）。

连接池缺省 `pool_size=3` / `max_overflow=0`，由 ADR-010 固定：阿里云 PG 对四人团队总配额 30 连接。`tests/backend/test_config.py` 断言的是这组**缺省值**，通过 `DATABASE_POOL_SIZE` 覆盖在技术上可行，但在共享环境中不得调高。

### 环境变量

复制仓库根目录 `.env.example` 为 `.env`——注意是**根目录**，不是 `backend/.env`（`Settings.model_config` 的 `env_file=".env"` 相对于进程工作目录解析）。

实际被读取的变量、前缀分组与缺省值以 `backend/core/config.py` 为准，不以文档为准。本 fork 已通过 `backend/core/bailian.py` 接入 `DASHSCOPE_API_KEY`；`VISION_API_MODEL` / `SECRET_KEY` 等尚未接入配置模块，待 Vision 与安全模块实现时新增（ADR-004 / ADR-007）。

## 文档地图

三层分类，每层只回答一类问题：**`docs/`（WHY）** 原始提案与业务流程设计，其中 `business-workflow-design.md` 是全仓信息密度最高的权威逻辑描述，本 README 的裁决逻辑即源于此；**`specs/`（WHAT）** 需求与验收标准、前后端共享数据契约、10 个架构决策记录；**`design/`（HOW）** 分层架构与 Agent 接口、UI 规范、可视化蓝图与可交互原型。

逐份文档的位置与用途见 `.specify/features/001-crs-contract/plan.md` 的 §文档归档索引；编码约定与仓库结构约定见 `AGENTS.md`。`specs/` `design/` `docs/` 由 PM 与设计侧维护，编码 Agent 不得修改。

## 团队与许可

AI Campaign 2026 参赛团队，4 人。Private — 竞赛项目，未授权外部使用。


当前验证：锁定依赖下 **227 项测试通过、3 项 PostgreSQL 集成测试跳过**，Ruff 与全量 backend Mypy 通过。
真实百炼调用、云数据库、完整上传审核链路和 cron 安装仍待验收；当前结果不代表完整契约或全部税法条件已覆盖。
