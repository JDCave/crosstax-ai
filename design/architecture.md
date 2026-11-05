# CrossTax AI — 架构设计文档

> **版本：** v1.3 | **日期：** 2026-11-02 | **作者：** PM + Tech Lead  
> **关联图表：** [diagrams/architecture-overview.html](./diagrams/architecture-overview.html)  
> **输入来源：** `specs/prd.md`、`docs/proposal/crosstax-ai-solution (from ppt).md`  
> **状态：** 草案，待团队评审  
> **变更记录：**  
> - v1.0 (2026-10-22): 初始草案  
> - v1.1 (2026-10-22): 技术选型确认 — 前端由 Streamlit 切换为 React 18 + TypeScript，后端新增 FastAPI API 层，详见 ADR-002
> - v1.2 (2026-10-23): 数据库方案确认 — 混合方案（本地 SQLite + 阿里云 PG 生产），LLM 平台确认神机百炼，pgvector 竞赛阶段豁免，详见 ADR-008/009/010
> - v1.3 (2026-11-02): 与已落地代码对齐 — §2.4.1 改为异步 SQLAlchemy 实现、§4.2 改为 uv 多阶段 Dockerfile、§4.3 环境变量改为实际名称、§5 目录树标注实现状态；修正失效链接与 `docs/` 路径；补充 Redis

---

## 1. 架构概述

### 1.1 架构风格

采用 **多智能体流水线（Multi-Agent Pipeline）** 架构，核心特征：

- **分层解耦**：展现层、编排层、引擎层、基础设施层严格分离
- **串联式 Agent**：5 个审核步骤形成有向无环图（DAG），每步将中间结果传递给下一步
- **确定性 + 智能混合**：TIN 校验等规则层为确定性计算，跨源冲突研判引入 LLM 推理
- **声明式规则热重载**：规则配置与引擎运行时彻底解耦，支持秒级生效

### 1.2 架构决策记录 (ADR)

> 详细决策记录已迁移至 [`specs/adr/`](../specs/adr/) 目录，每个决策独立一个文件。

| ADR | 决策 | 文件 | 状态 |
|-----|------|------|------|
| ADR-001 | Python 作为主语言 | [`001-python-main-language.md`](../specs/adr/001-python-main-language.md) | 已采纳 |
| ADR-002 | React + FastAPI 前后端分离 | [`002-react-fastapi-split.md`](../specs/adr/002-react-fastapi-split.md) | 已采纳 |
| ADR-003 | JSON 文件存储规则 | [`003-json-rule-storage.md`](../specs/adr/003-json-rule-storage.md) | 已采纳 |
| ADR-004 | 调用第三方 Vision API | [`004-vision-api.md`](../specs/adr/004-vision-api.md) | 已采纳 |
| ADR-005 | Mock 数据替代真实对接 | [`005-mock-data.md`](../specs/adr/005-mock-data.md) | 已采纳 |
| ADR-006 | 阿里云 ECS 部署 | [`006-alibaba-ecs.md`](../specs/adr/006-alibaba-ecs.md) | 已采纳 |
| ADR-007 | 阿里云神机百炼 LLM 平台 | [`007-shenji-bailian-llm.md`](../specs/adr/007-shenji-bailian-llm.md) | 已采纳 |
| ADR-008 | 混合数据库方案（SQLite + PG） | [`008-hybrid-database.md`](../specs/adr/008-hybrid-database.md) | 已采纳 |
| ADR-009 | 竞赛阶段豁免 pgvector | [`009-pgvector-exemption.md`](../specs/adr/009-pgvector-exemption.md) | 已采纳 |
| ADR-010 | PG 连接池限制（每人 ≤ 3） | [`010-pg-connection-limit.md`](../specs/adr/010-pg-connection-limit.md) | 已采纳 |

---

## 2. 分层架构详设

### 2.1 L1 — 展现层 (Presentation)

前端采用 **React 18 + TypeScript** 单页应用，通过 REST API 与后端 FastAPI 服务通信。

| 组件 | 技术 | 职责 |
|------|------|------|
| 主界面框架 | React 18 + TypeScript + Vite | SPA 路由、布局、状态管理 |
| 文件上传与样本切换 | react-dropzone + Ant Design Upload | 本地上传 / 切换 5 个预置 Case |
| 实时研判看板 | Ant Design Steps + 自定义 Pipeline 动画 | Agent 执行阶段可视化 |
| 修复卡片区 | Ant Design Collapse / Card | BLOCKER 场景的通俗整改建议 |
| 规则同步模拟 | Ant Design Button + WebSocket / SSE | 触发热重载，展示规则版本变化 |
| 审计底稿区 | 内嵌 iframe + 下载按钮 | HTML 报告预览与下载 |
| HTTP 客户端 | Axios / fetch | 调用后端 FastAPI REST 接口 |

**后端 API 层（FastAPI）：**

| 端点 | 方法 | 职责 |
|------|------|------|
| `/api/v1/audit` | POST | 提交文件，触发审核流水线 |
| `/api/v1/audit/{session_id}` | GET | 查询审核会话状态与结果 |
| `/api/v1/rules` | GET | 获取当前规则版本摘要 |
| `/api/v1/rules/reload` | POST | 触发规则热重载 |
| `/api/v1/cases` | GET | 获取预置 Case 列表 |
| `/api/v1/cases/{case_id}` | GET | 加载预置 Case 样本 |
| `/api/v1/audit/{session_id}/report` | GET | 下载 HTML 审计报告 |
| `/ws/audit/{session_id}` | WebSocket | 实时推送 Agent 执行阶段状态 |

**设计约束：**
- 所有 UI 组件必须响应式适配 1280px+ 屏幕
- 审核结果必须在 30 秒内完整渲染
- 修复卡片必须按字段级粒度展示错误与修改建议
- 前后端通过 OpenAPI Schema 自动生成交互契约

### 2.2 L2 — 智能体编排层 (Orchestration)

编排层是整个架构的核心，负责串联 5 个审核步骤。

#### 2.2.1 流水线数据模型

```python
@dataclass
class CRSFormData:
    """Vision Agent 抽取的结构化输出"""
    holder_name: str
    holder_dob: str                    # 出生日期 / 成立日
    residence_address: str
    jurisdiction_code: str             # ISO 2字码
    tin: Optional[str]
    has_no_tin: bool
    tin_reason_code: Optional[str]     # A / B / C
    tin_reason_explanation: Optional[str]
    has_signature: bool
    signing_date: Optional[str]

@dataclass
class AuditIssue:
    """单条审核问题"""
    code: str                          # e.g. INVALID_TIN, NO_SIGNATURE
    severity: str                      # BLOCKER / WARNING
    field: Optional[str]               # 关联字段
    message: str                       # 通俗描述
    confidence: float                  # 0.0 - 1.0

@dataclass
class AuditSession:
    """审核会话 — 审计留痕的最小单元"""
    session_id: str
    merchant_id: str
    file_hash: str                     # 原始文件 SHA-256
    rule_version_id: str
    form_data: CRSFormData
    form_issues: List[AuditIssue]
    indicia_issues: List[AuditIssue]
    verdict: str                       # AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE
    timestamp: datetime
```

#### 2.2.2 Agent 接口契约

| Agent | 输入 | 输出 | 异常处理 |
|-------|------|------|----------|
| MediaPreprocessor | 原始文件 (PDF/Image) | Base64 图像流 | 文件损坏 → 返回错误提示 |
| VisionParserAgent | Base64 图像流 | CRSFormData + 置信度 | API 超时 → 重试 1 次 → 降级手动输入 |
| TINValidatorEngine | CRSFormData.tin + 规则库 | List[AuditIssue] | 未配置法域 → 兜底长度校验 |
| FormCompletenessChecker | CRSFormData | List[AuditIssue] | — |
| IndiciaReasoningAgent | CRSFormData + 商户底表 | List[AuditIssue] | 底表缺失 → 跳过冲突研判 |
| VerdictResolver | form_issues + indicia_issues | verdict string | — |
| AuditTrailEngine | AuditSession | HTML 报告 | — |

#### 2.2.3 编排流程伪代码

```python
def run_audit_pipeline(file, merchant_id) -> AuditSession:
    session = create_session(merchant_id, file)

    # Step 1: 媒体预处理
    images = media_preprocessor.process(file)

    # Step 2: Vision 抽取
    form_data, confidence = vision_agent.extract(images)
    session.form_data = form_data

    # Step 3: 形式完备性 + TIN 校验
    form_issues = []
    form_issues += form_completeness_checker.check(form_data)
    form_issues += tin_validator.validate(form_data, session.rule_version_id)
    session.form_issues = form_issues

    # Step 4: 跨源冲突研判
    merchant = load_merchant(merchant_id)
    indicia_issues = indicia_reasoner.analyze(form_data, merchant)
    session.indiciaissues = indicia_issues

    # Step 5: 裁决
    session.verdict = verdict_resolver.resolve(form_issues, indicia_issues)

    # 审计留痕
    audit_trail.persist(session)
    return session
```

### 2.3 L3 — 核心引擎层 (Engine)

#### 2.3.1 TIN 校验引擎

```
输入: tin (str), jurisdiction_code (str)
处理:
  1. 清洗: 剥离空格、连字符、括号
  2. 正则匹配: 加载 rules[jurisdiction].regex，校验长度与字符集
  3. 算子分发: 调用 rules[jurisdiction].algorithm
     - MOD11_2: 模 11 权重 2 校验
     - HKID_WEIGHT: 香港身份证加权校验
     - NRIC_WEIGHT: 新加坡 NRIC 加权校验
     - REGEX_ONLY: 仅正则匹配
  4. 兜底: 未配置国家 → 长度 4-30 位 + 非空
输出: PASS / INVALID_TIN
```

#### 2.3.2 规则热重载机制

```python
class RuleEngine:
    def __init__(self):
        self._rules: dict = {}
        self._version_id: str = ""
        self._lock = threading.Lock()

    def load_rules(self, path: str):
        """原子替换规则字典，线程安全"""
        new_rules = json.load(open(path))
        new_version = generate_version_id(new_rules)
        with self._lock:
            self._rules = new_rules
            self._version_id = new_version

    @property
    def current_version(self) -> str:
        return self._version_id
```

**关键设计：**
- 使用 `threading.Lock` 保证原子替换
- 版本号基于规则内容哈希生成，确保可溯源
- 审核会话创建时快照当前版本号，后续校验使用该快照

#### 2.3.3 跨源冲突研判

| 冲突场景 | 输入字段 | 判定逻辑 | 输出 |
|----------|----------|----------|------|
| 场景 1: 单国申报 vs 境外运营 | jurisdiction_code, primary_operating_country | 申报国 ≠ 运营国 | INDICIA_CONFLICT (confidence: 0.8) |
| 场景 2: 离岸主体税籍隐瞒 | jurisdiction_code, incorporation_jurisdiction | 注册地 ∈ 离岸列表 且 申报国 ≠ 注册地 | INDICIA_CONFLICT (confidence: 0.9) |
| 场景 3: 主体名称冲突 | holder_name, kyc_legal_name | 名称不匹配（模糊匹配） | INDICIA_CONFLICT (confidence: 0.7) |

#### 2.3.4 三态裁决器

```
输入: form_issues: List[AuditIssue], indicia_issues: List[AuditIssue]
判定:
  IF any(issue.severity == BLOCKER for issue in form_issues):
    → NEED_USER_FIX
  ELIF any(issue.severity == WARNING for issue in indicia_issues):
    → MANUAL_TRIAGE
  ELSE:
    → AUTO_PASS
输出: verdict string
```

### 2.4 L4 — 基础设施层 (Infrastructure)

| 组件 | 技术选型 | 部署方式 | 说明 | 状态 |
|------|----------|----------|------|------|
| 规则配置库 | JSON 文件 | 本地磁盘 + 内存缓存 | `rules/`（ADR-003；原稿写的 `assets/mock-data/rules/` 已废弃） | 规划中 |
| Vision API | 阿里云神机百炼（Qwen-VL-Max） | 外部调用（SDK / HTTP 待裁定，见 ADR-007） | API Key 通过环境变量注入 | 规划中 |
| LLM 推理 | 神机百炼（Qwen-Max / GLM / DeepSeek） | 外部调用（同上） | 跨源冲突研判 + 名称模糊匹配 fallback | 规划中 |
| Embedding | 神机百炼 Embedding 模型 | 外部调用 | 竞赛阶段不启用向量检索，预留接口（ADR-009） | 规划中 |
| Mock 商户数据 | JSON 文件 | 本地磁盘 | `assets/mock-data/mock_merchants.json`（ADR-005） | 规划中 |
| 数据库（本地开发） | SQLite + `aiosqlite` | 本地文件 | 缺省 `sqlite+aiosqlite:///./crosstax.db` | 已落地 |
| 数据库（生产/测试） | PostgreSQL 16 + `asyncpg` | 阿里云 RDS（ECS 内网） | 连接池 ≤ 3/人且禁止溢出，总上限 30（ADR-010） | 待部署验证 |
| pgvector | 0.8.0.2 扩展 | 阿里云 RDS | 竞赛阶段豁免，降级为规则 + LLM fallback（ADR-009） | 豁免 |
| 缓存 | Redis 7 | compose 容器 / 阿里云 | `REDIS_URL`；依赖与编排已就位，业务尚未接入 | 部分落地 |
| 审计存储 | 数据库（SQLite / PG） | 本地文件 / 阿里云 RDS | 后端由 `DATABASE_URL` 决定，**非** `APP_ENV` | 规划中 |
| 运行时 | Python 3.11+（uv 管理依赖） | 阿里云 ECS | 容器化部署，非 root 运行 | 已落地 |

#### 2.4.1 数据库抽象层设计

采用 **SQLAlchemy 2.0 异步 ORM** 屏蔽 SQLite 与 PG 差异。后端切换只由 `DATABASE_URL` 决定，`ENVIRONMENT` 仅控制日志与调试开关（原稿设计的 `APP_ENV` 分支切换未采用）。

配置集中在 `backend/core/config.py`，引擎与会话工厂在 `backend/infrastructure/database.py`：

```python
# backend/core/config.py（节选）
class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(default="sqlite+aiosqlite:///./crosstax.db")
    # ADR-010: 阿里云 PG 总连接上限 30，4 人团队每人 ≤ 3 且禁止溢出
    pool_size: int = Field(default=3, ge=1)
    max_overflow: int = Field(default=0, ge=0)
    pool_recycle: int = Field(default=1800)
    pool_pre_ping: bool = Field(default=True)
    echo: bool = Field(default=False)
```

```python
# backend/infrastructure/database.py（节选）
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)

engine: AsyncEngine = create_async_engine(
    db.url,
    pool_size=db.pool_size,
    max_overflow=db.max_overflow,
    pool_recycle=db.pool_recycle,
    pool_pre_ping=db.pool_pre_ping,
    echo=db.echo,
)

async_session_factory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False,
)

async def get_session() -> AsyncSession:
    """FastAPI 依赖：自动 commit / rollback。"""
```

**关键约定：**
- 连接 URL **必须带异步驱动前缀**：`sqlite+aiosqlite://`（本地）/ `postgresql+asyncpg://`（PG）
- ORM 声明基类 `Base` 位于 `backend/models/base.py`（含 `TimestampMixin`），**不在** `database.py` 中
- 会话通过 FastAPI 依赖 `get_session()` 注入，路由内不得自建 session
- 连接池上限由 ADR-010 锁定为 `pool_size=3, max_overflow=0`，`tests/backend/test_config.py` 断言防回归

**兼容性约束：**
- 仅使用 SQLAlchemy 标准类型（String, Integer, Float, Boolean, DateTime, JSON, Text）
- 避免 PG 特有语法（如 `ILIKE`、`::` 类型转换）
- JSON 字段 SQLite ≥ 3.38 原生支持，PG 使用 `jsonb`
- 迁移工具：Alembic（`alembic/env.py` 已对接异步引擎，双后端均可生成 migration script）

**尚未实现的原设计点：**
- SQLite `PRAGMA journal_mode=WAL`（原稿通过 `event.listens_for` 注入）当前未实现，异步引擎下需改用 `connect` 事件 + `AsyncAdaptedQueuePool` 适配
- 原稿的 `SQLITE_PATH` 独立环境变量未采用，统一由 `DATABASE_URL` 表达

**环境切换：**
```bash
# 本地开发（不设 DATABASE_URL，走缺省 SQLite）
uv run uvicorn backend.main:app --reload

# 集成测试 / 本地 PG 容器
DATABASE_URL=postgresql+asyncpg://crosstax:crosstax@localhost:5432/crosstax \
  uv run pytest tests/

# 生产部署（ECS 内网连阿里云 RDS PG 16）
ENVIRONMENT=prod \
DATABASE_URL=postgresql+asyncpg://user:pass@rm-xxx.pg.rds.aliyuncs.com:5432/crosstax \
  uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 3. 数据流设计

### 3.1 端到端数据流

```
用户上传文件
    │
    ▼
[MediaPreprocessor]
    │ Base64 图像流
    ▼
[VisionParserAgent] ──→ Vision API (外部)
    │ CRSFormData + confidence
    ▼
┌───────────────────────────────────┐
│          并行校验                  │
│  ┌─────────────┐ ┌─────────────┐ │
│  │FormChecker  │ │TINValidator │ │
│  └──────┬──────┘ └──────┬──────┘ │
│         │               │         │
│         ▼               ▼         │
│     FormIssues[]    (TIN结果)     │
└─────────────────┬─────────────────┘
                  │
                  ▼
[IndiciaReasoner] ──→ mock_merchants.json
    │ IndiciaIssues[]
    ▼
[VerdictResolver]
    │ verdict ∈ {AUTO_PASS, NEED_USER_FIX, MANUAL_TRIAGE}
    ▼
[AuditTrailEngine]
    │ AuditSession (快照)
    ▼
┌──────────────────────────────────┐
│          输出分支                 │
│  AUTO_PASS    → 放行通知         │
│  NEED_FIX     → 修复卡片         │
│  MANUAL_TRIAGE → 合规官工作台    │
│  ALL          → HTML 审计报告    │
└──────────────────────────────────┘
```

### 3.2 关键数据格式

**CRSFormData (JSON)**
```json
{
  "holder_name": "ACME Trading Ltd",
  "holder_dob": "2015-03-15",
  "residence_address": "Unit 12, 88 Queen's Road, HK",
  "jurisdiction_code": "HK",
  "tin": "A123456(7)",
  "has_no_tin": false,
  "tin_reason_code": null,
  "tin_reason_explanation": null,
  "has_signature": true,
  "signing_date": "2026-09-01"
}
```

**AuditIssue (JSON)**
```json
{
  "code": "INVALID_TIN",
  "severity": "BLOCKER",
  "field": "tin",
  "message": "TIN 校验位不匹配，预期值 7，实际值 8",
  "confidence": 1.0
}
```

---

## 4. 部署架构

### 4.1 阿里云资源规划

| 资源 | 规格 | 用途 | 状态 |
|------|------|------|------|
| ECS 实例 | 2C4G（竞赛足够） | 应用运行 | 待开通 |
| 系统盘 | 40GB SSD | 操作系统 + 应用 | 待开通 |
| 数据盘 | 20GB | Mock 数据 + 审计存储 | 待开通 |
| RDS PostgreSQL 16 | 仅 ECS 内网可达，账号总连接上限 30 | 生产/测试数据库（ADR-008 / ADR-010） | 组委会提供 |
| Redis | 阿里云 Redis 或 ECS 自建 | 缓存 / 流水线状态 | 待确认 |
| 安全组 | 开放 80/443/8000 | HTTP/HTTPS/FastAPI | 待配置 |
| 域名 | 可选 | 演示用 | 待确认 |

### 4.2 容器化方案

**目标形态：** 多阶段构建，前端编译产物由 FastAPI 静态托管，实现单容器部署（ADR-002）。

**当前实现：** `Dockerfile` 为 **后端单服务** uv 多阶段镜像（前端阶段待 `frontend/` 落地后接入）：

```dockerfile
# ---- Build stage ----
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini .

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime
RUN groupadd -r app && useradd -r -g app -G app app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/backend /app/backend
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

与原稿设计的差异（均为有意调整）：
- 依赖安装由 `pip install -r backend/requirements.txt` 改为 **`uv sync --frozen`**（仓库内无 `requirements.txt`，见 ADR-001）
- 健康检查用 Python `urllib` 而非 `curl`（`python:3.11-slim` 不含 curl）
- 以非 root 用户 `app` 运行
- 尚未 `COPY assets/ rules/`，待规则与 Mock 数据产出后补入

**前端阶段接入后**需追加（目标）：

```dockerfile
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# runtime 阶段追加：COPY --from=frontend-builder /app/frontend/dist ./static/
```

**本地编排：** `docker-compose.yml` 起 `backend` + `postgres:16-alpine` + `redis:7-alpine` 三服务（含健康检查与依赖顺序）。其中 PG 为**本地开发容器**，与仅 ECS 内网可达的阿里云 RDS 不是同一实例。环境变量须用单下划线前缀（`DATABASE_URL` / `REDIS_URL`），与 `config.py` 的 `env_prefix="DATABASE_"` / `"REDIS_"` 匹配。

### 4.3 环境变量

配置文件位于**仓库根目录** `.env`（模板 `.env.example`），由 `backend/core/config.py` 的 pydantic-settings 读取。

**已实现（与 `.env.example` 一致）：**

```bash
# 应用（ENVIRONMENT 取值 dev / test / prod；仅控制日志与调试，不切换数据库后端）
ENVIRONMENT=dev
DEBUG=true
LOG_LEVEL=INFO
LOG_FORMAT=console                     # console / json
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]   # JSON 数组格式

# 数据库（前缀 DATABASE_；URL 必须带异步驱动前缀）
DATABASE_URL=sqlite+aiosqlite:///./crosstax.db
# DATABASE_URL=postgresql+asyncpg://user:pass@rm-xxx.pg.rds.aliyuncs.com:5432/crosstax
DATABASE_POOL_SIZE=3                   # ADR-010：每人 ≤ 3（总上限 30）
DATABASE_MAX_OVERFLOW=0                # ADR-010：禁止溢出
DATABASE_POOL_RECYCLE=1800
DATABASE_ECHO=false

# Redis（前缀 REDIS_）
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=10
```

**规划中（尚未在 `config.py` 中定义，接入 Vision/LLM 与安全模块时新增）：**

```bash
# Vision API（阿里云神机百炼）— 调用方式待 ADR-007 裁定
DASHSCOPE_API_KEY=sk-xxx
VISION_API_MODEL=qwen-vl-max

# LLM 推理（神机百炼）
LLM_API_MODEL=qwen-max                 # qwen-max / glm-4 / deepseek-v3

# 规则引擎（ADR-003）
RULES_BASE_PATH=./rules/rules_v1_base.json
RULES_PATCH_PATH=./rules/rules_v2_patch.json

# 审计报告模板
AUDIT_TEMPLATE_PATH=./assets/templates/audit_report.html.j2

# 前端（构建时注入，待 frontend/ 落地）
VITE_API_BASE_URL=http://localhost:8000/api/v1

# 安全
SECRET_KEY=xxx
```

与原稿设计的差异：
- `APP_ENV`（development/testing/production）→ 实际 `ENVIRONMENT`（dev/test/prod），且不再承担数据库后端切换职责
- `BACKEND_HOST` / `BACKEND_PORT` → 实际 `HOST` / `PORT`
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` → 实际 `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW`
- `CORS_ORIGINS` 为 JSON 数组格式，非逗号分隔字符串
- 原稿 `VISION_API_PROVIDER` / `LLM_API_PROVIDER` / `SQLITE_PATH` / `AUDIT_STORAGE_PATH` 未采用（审计落数据库而非本地文件）

---

## 5. 模块目录结构

> 标注 **(规划中)** 的为设计目标，尚未创建或为空；其余为当前真实结构。

```
crosstax-ai/
├── backend/                            # Python 后端服务 (uv-managed)
│   ├── main.py                         # 应用工厂 create_app() + lifespan + 中间件注册
│   ├── api/
│   │   ├── routes/
│   │   │   ├── health.py               # /health 存活 + /ready 就绪探针
│   │   │   ├── audit.py                # /api/v1/audit            (规划中)
│   │   │   ├── rules.py                # /api/v1/rules            (规划中)
│   │   │   └── cases.py                # /api/v1/cases            (规划中)
│   │   ├── schemas/                    # Pydantic 请求/响应模型    (规划中)
│   │   └── websocket.py                # WebSocket 实时推送        (规划中)
│   ├── core/
│   │   ├── config.py                   # pydantic-settings 配置
│   │   └── logging/                    # config / formatter / RequestId 中间件
│   ├── infrastructure/
│   │   ├── database.py                 # 异步引擎 + async_sessionmaker + get_session()
│   │   └── exceptions.py               # 全局异常处理器
│   ├── models/                         # SQLAlchemy ORM 模型
│   │   ├── base.py                     # DeclarativeBase + TimestampMixin
│   │   ├── user.py                     # 用户表
│   │   ├── audit_session.py            # 审核会话表               (规划中)
│   │   └── merchant.py                 # 商户底表                 (规划中)
│   ├── repositories/
│   │   └── base.py                     # 仓储基类
│   ├── agents/                         # 流水线智能体             (规划中)
│   │   ├── media_preprocessor.py       # 媒体预处理
│   │   ├── vision_parser.py            # Vision Agent
│   │   ├── form_checker.py             # 形式完备性校验
│   │   ├── tin_validator.py            # TIN 校验引擎
│   │   ├── indicia_reasoner.py         # 跨源冲突研判
│   │   ├── verdict_resolver.py         # 三态裁决器
│   │   └── audit_trail.py              # 审计留痕
│   ├── engine/                         # 规则引擎                 (规划中)
│   │   ├── rule_engine.py              # 规则引擎 + 热重载
│   │   └── models.py                   # CRSFormData / AuditIssue 等
│   └── utils/                          # 文件哈希等工具           (规划中)
├── alembic/                            # 数据库迁移
│   ├── env.py                          # 已对接异步引擎
│   ├── script.py.mako
│   └── versions/                       # 暂无迁移脚本             (规划中)
├── tests/
│   ├── conftest.py
│   ├── backend/
│   │   ├── test_config.py              # 配置与 ADR-010 连接池断言
│   │   ├── test_health.py              # 探针测试
│   │   ├── test_tin_validator.py       # (规划中)
│   │   ├── test_verdict_resolver.py    # (规划中)
│   │   ├── test_indicia_reasoner.py    # (规划中)
│   │   └── test_e2e_pipeline.py        # (规划中)
│   ├── fixtures/                       # (空)
│   └── frontend/                       # 前端测试                 (规划中)
├── frontend/                           # React 18 + TS + Vite (npm) (规划中，尚未创建)
│   └── src/
│       ├── main.tsx / App.tsx
│       ├── api/                        # Axios 客户端封装
│       ├── components/                 # PipelineStatus / VerdictBanner /
│       │                               # RemediationCard / ConflictEvidence /
│       │                               # AuditTrail / RuleReload
│       ├── pages/                      # AuditPage / CasesPage
│       ├── hooks/                      # useAuditStream 等
│       ├── stores/                     # Zustand
│       ├── types/                      # TS 类型定义
│       └── styles/                     # 主题 token + 全局样式
├── assets/
│   ├── crs-templates/                  # IRD 官方 CRS 取证资产（实有）：4 份官方 PDF（个人/实体/控权人/总则）+ 2 份示例请求 JSON + README.md + API_INTEGRATION.md
│   ├── mock-data/                      # 商户底表 + 5 个 CRS 样本 (规划中，仅占位)
│   └── templates/                      # Jinja2 审计报告模板      (规划中，仅占位)
├── rules/                              # CRS 规则配置（后端消费）  (规划中，目录为空)
│   ├── rules_v1_base.json              # 基准规则
│   └── rules_v2_patch.json             # 增量补丁（热重载演示）
├── fixtures/                           # (规划中，目录为空)
├── docker/                             # (规划中，目录为空；编排见 docker-compose.yml)
├── design/
│   ├── architecture.md                 # 本文档
│   ├── ui-spec.md                      # UI 设计规范
│   ├── diagrams/
│   │   └── architecture-overview.html  # 架构蓝图
│   └── prototypes/
│       └── react-ui-wireframe.html     # 可交互原型
├── specs/
│   ├── prd.md                          # PRD
│   ├── data-spec.md                    # 数据模型规格
│   └── adr/                            # 架构决策记录（10 个独立文件）
├── docs/
│   └── proposal/                       # 原始提案归档
├── .specify/                           # spec-kit 特性工件（features/001-crs-contract/：spec + plan + 契约 + 映射矩阵）
├── pyproject.toml                      # 依赖 + ruff/mypy/pytest/coverage 配置
├── uv.lock                             # uv 依赖锁文件
├── alembic.ini                         # Alembic 配置
├── Makefile                            # 命令入口（dev/test/lint/mypy/migrate/build/up/down）
├── Dockerfile                          # uv 多阶段后端镜像（前端阶段待接入）
├── docker-compose.yml                  # backend + postgres:16 + redis:7
├── .env.example                        # 环境变量模板
├── .gitignore                          # 忽略规则
├── .dockerignore                       # 镜像构建排除清单
├── .pre-commit-config.yaml             # 提交前钩子
├── AGENTS.md                           # AI 编码助手规范
└── README.md                           # 项目说明 + 文档导航
```

> 原稿将文档索引与路线图放在 `docs/README.md`、`docs/roadmap.md`，现已分别迁移至仓库根目录的 `README.md` 与 `ROADMAP.md`，`docs/` 仅保留 `proposal/` 原始提案归档。
>
> **2026-11-05 追加**：根目录 `ROADMAP.md`（183 行 / 97 条勾选项）已全文并入 `.specify/features/001-crs-contract/plan.md` 的 §实现现状 与 §项目级待办 后删除，仓库根目录不再保留独立路线图，上述目录树已同步。上一条记录中「迁移至 `ROADMAP.md`」的部分已被此次变更取代——原文保留不改写，以维持决策历史可追溯。

---

## 6. 待确认事项

| # | 事项 | 影响 | 建议决策 | 状态 |
|---|------|------|----------|------|
| 1 | Vision API 供应商选型 | 抽取准确率、成本、延迟 | 阿里云神机百炼 Qwen-VL-Max | **已确认** |
| 2 | 数据库方案 | 开发效率、生产兼容性 | 混合方案：本地 SQLite + 阿里云 PG 16 生产 | **已确认（2026-10-23）** |
| 3 | ~~是否需要后端 API 层~~ | ~~前后端分离 vs Streamlit 内嵌~~ | ~~暂不需要，Streamlit 直连引擎~~ | **已确认：采用 FastAPI 前后端分离** |
| 4 | 5 个 Case 的具体数据 | 演示效果、测试覆盖 | 需与合规专家共同设计 | 待确认 |
| 5 | 阿里云 ECS 规格 | 成本、性能 | 2C4G 起步，按需扩容 | 待确认 |
| 6 | React UI 组件库选型 | 开发效率、视觉一致性 | Ant Design 5.x（企业级组件丰富） | 待确认 |
| 7 | 前后端实时通信方案 | 流水线状态推送体验 | WebSocket 优先，SSE 备选 | 待确认 |
| 8 | pgvector 向量检索 | 名称模糊匹配准确率 | 竞赛阶段暂不启用，规则 + LLM fallback | **已确认：竞赛阶段豁免** |
| 9 | LLM 推理模型选型 | 冲突研判质量、成本 | 神机百炼 Qwen-Max（主力）/ GLM / DeepSeek | **已确认** |
| 10 | 神机百炼调用方式 | 依赖体积、异步兼容性 | ADR-007 写 `dashscope` SDK，本文档 §2.4 写「外部 HTTP 调用」，且 `dashscope` 未入 `pyproject.toml`（现有 `httpx`）。需统一 | **待裁定** |
| 11 | Redis 用途与部署形态 | 是否引入额外云资源 | 依赖与 compose 编排已就位，但业务尚未使用；需明确用途（缓存 / 流水线状态 / WebSocket 广播）后再决定云上形态 | **待确认** |

---

## 7. 参考文档

- [PRD](../specs/prd.md) — 完整需求规格
- [数据模型规格](../specs/data-spec.md) — 前后端共享数据契约
- [架构决策记录](../specs/adr/) — 10 个 ADR
- [架构蓝图](./diagrams/architecture-overview.html) — 可视化架构图
- [业务流程](../docs/proposal/business-workflow-design.md) — 业务专家流程设计
- [方案原始需求](../docs/proposal/crosstax-ai-solution%20(from%20ppt).md) — PPT 摘要
