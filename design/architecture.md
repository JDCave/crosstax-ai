# CrossTax AI — 架构设计文档

> **版本：** v1.2 | **日期：** 2026-10-23 | **作者：** PM + Tech Lead  
> **关联图表：** [architecture-overview.html](./architecture-overview.html)  
> **输入来源：** `specs/prd.md`、`docs/proposal/crosstax-ai-solution (from ppt).md`  
> **状态：** 草案，待团队评审  
> **变更记录：**  
> - v1.0 (2026-10-22): 初始草案  
> - v1.1 (2026-10-22): 技术选型确认 — 前端由 Streamlit 切换为 React 18 + TypeScript，后端新增 FastAPI API 层，详见 ADR-002
> - v1.2 (2026-10-23): 数据库方案确认 — 混合方案（本地 SQLite + 阿里云 PG 生产），LLM 平台确认神机百炼，pgvector 竞赛阶段豁免，详见 ADR-008/009/010

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

| 组件 | 技术选型 | 部署方式 | 说明 |
|------|----------|----------|------|
| 规则配置库 | JSON 文件 | 本地磁盘 + 内存缓存 | `assets/mock-data/rules/` |
| Vision API | 阿里云神机百炼（Qwen-VL-Max） | 外部 HTTP 调用 | API Key 通过环境变量注入 |
| LLM 推理 | 神机百炼（Qwen-Max / GLM / DeepSeek） | 外部 HTTP 调用 | 跨源冲突研判 + 名称模糊匹配 fallback |
| Embedding | 神机百炼 Embedding 模型 | 外部 HTTP 调用 | 竞赛阶段暂不启用向量检索，预留接口 |
| Mock 商户数据 | JSON 文件 | 本地磁盘 | `assets/mock-data/mock_merchants.json` |
| 数据库（本地开发） | SQLite | 本地文件 | Python 内置，零配置，`crosstax_dev.db` |
| 数据库（生产/测试） | PostgreSQL 16 + pgvector 0.8.0.2 | 阿里云 RDS（ECS 内网） | 连接池 ≤ 3/人，总连接上限 30 |
| 审计存储 | 数据库（SQLite / PG 按环境切换） | 本地文件 / 阿里云 RDS | 通过 `APP_ENV` 环境变量控制 |
| 运行时 | Python 3.11+ | 阿里云 ECS | 容器化部署 |

#### 2.4.1 数据库抽象层设计

采用 SQLAlchemy ORM 屏蔽 SQLite 与 PG 差异，通过环境变量 `APP_ENV` 切换后端。

```python
# backend/core/database.py
import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

APP_ENV = os.getenv("APP_ENV", "development")
DATABASE_URL = os.getenv("DATABASE_URL")

if APP_ENV in ("testing", "production") and DATABASE_URL:
    # 阿里云 PG 16（ECS 内网直连）
    engine = create_engine(
        DATABASE_URL,
        pool_size=int(os.getenv("DB_POOL_SIZE", "3")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "0")),
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    # 本地 SQLite（零配置，Python 内置）
    DB_PATH = os.getenv("SQLITE_PATH", "./crosstax_dev.db")
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    # SQLite 开启 WAL 模式提升并发读性能
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```

**兼容性约束：**
- 仅使用 SQLAlchemy 标准类型（String, Integer, Float, Boolean, DateTime, JSON, Text）
- 避免 PG 特有语法（如 `ILIKE`、`::` 类型转换）
- JSON 字段 SQLite ≥ 3.38 原生支持，PG 使用 `jsonb`
- 迁移工具：Alembic（双后端均可生成 migration script）

**环境切换：**
```bash
# 本地开发（默认 SQLite）
APP_ENV=development uvicorn backend.main:app --reload

# 集成测试（切换 PG）
APP_ENV=testing DATABASE_URL=postgresql://... pytest tests/integration/

# 生产部署（ECS 内网 PG）
APP_ENV=production DATABASE_URL=postgresql://... uvicorn backend.main:app
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

| 资源 | 规格 | 用途 |
|------|------|------|
| ECS 实例 | 2C4G（竞赛足够） | 应用运行 |
| 系统盘 | 40GB SSD | 操作系统 + 应用 |
| 数据盘 | 20GB | Mock 数据 + 审计存储 |
| 安全组 | 开放 80/443/8000 | HTTP/HTTPS/FastAPI |
| 域名 | 可选 | 演示用 |

### 4.2 容器化方案

采用多阶段构建，前端编译产物由 FastAPI 静态托管，实现单容器部署。

```dockerfile
# Stage 1: 构建 React 前端
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 后端 + 静态前端
FROM python:3.11-slim

WORKDIR /app

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./backend/

# 复制前端构建产物到静态目录
COPY --from=frontend-builder /app/frontend/dist ./static/

# 复制规则与 Mock 数据
COPY assets/ ./assets/
COPY rules/ ./rules/

EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3 环境变量

```bash
# 应用环境
APP_ENV=development                    # development / testing / production

# 后端服务
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:3000,https://crosstax.example.com

# 数据库（混合方案）
# development 环境：不设置 DATABASE_URL，自动使用 SQLite
# testing/production 环境：设置 DATABASE_URL 连接阿里云 PG
DATABASE_URL=postgresql://user:pass@rm-xxx.pg.rds.aliyuncs.com:5432/crosstax_dev
DB_POOL_SIZE=3                         # 每人连接池上限（总连接上限 30）
DB_MAX_OVERFLOW=0                      # 禁止溢出

# Vision API（阿里云神机百炼）
VISION_API_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxx
VISION_API_MODEL=qwen-vl-max

# LLM 推理（神机百炼）
LLM_API_PROVIDER=dashscope
LLM_API_MODEL=qwen-max                 # qwen-max / glm-4 / deepseek-v3

# 规则引擎
RULES_BASE_PATH=./rules/rules_v1_base.json
RULES_PATCH_PATH=./rules/rules_v2_patch.json

# 审计存储
AUDIT_STORAGE_PATH=./data/audit/

# 前端 (构建时注入)
VITE_API_BASE_URL=http://localhost:8000/api/v1

# 安全
SECRET_KEY=xxx
```

---

## 5. 模块目录结构

```
crosstax-ai/
├── assets/
│   ├── mock-data/
│   │   ├── mock_merchants.json        # Mock 商户底表
│   │   └── samples/                   # 5 个 CRS 样本文件
│   └── templates/
│       └── audit_report.html.j2       # Jinja2 审计报告模板
├── backend/                            # Python 后端服务 (uv-managed)
│   ├── main.py                         # FastAPI 入口
│   ├── core/
│   │   ├── database.py                 # 数据库抽象层（SQLite/PG 切换）
│   │   └── config.py                   # 环境变量配置（pydantic-settings）
│   ├── api/
│   │   ├── routes/                     # REST 路由
│   │   │   ├── audit.py                # /api/v1/audit
│   │   │   ├── rules.py                # /api/v1/rules
│   │   │   └── cases.py                # /api/v1/cases
│   │   ├── schemas/                    # Pydantic 请求/响应模型
│   │   └── websocket.py                # WebSocket 实时推送
│   ├── agents/
│   │   ├── media_preprocessor.py       # 媒体预处理
│   │   ├── vision_parser.py            # Vision Agent
│   │   ├── form_checker.py             # 形式完备性校验
│   │   ├── tin_validator.py            # TIN 校验引擎
│   │   ├── indicia_reasoner.py         # 跨源冲突研判
│   │   ├── verdict_resolver.py         # 三态裁决器
│   │   └── audit_trail.py              # 审计留痕
│   ├── engine/
│   │   ├── rule_engine.py              # 规则引擎 + 热重载
│   │   └── models.py                   # 数据模型 (CRSFormData, AuditIssue, etc.)
│   ├── models/                         # SQLAlchemy ORM 模型
│   │   ├── audit_session.py            # 审核会话表
│   │   └── merchant.py                 # 商户底表
│   └── utils/
│       ├── file_hash.py                # 文件哈希计算
│       └── logger.py                   # 日志
├── frontend/                           # React 前端应用 (npm-managed)
│   ├── public/
│   ├── src/
│   │   ├── main.tsx                    # React 入口
│   │   ├── App.tsx                     # 根组件
│   │   ├── api/                        # API 客户端封装
│   │   ├── components/
│   │   │   ├── PipelineStatus/         # 流水线状态组件
│   │   │   ├── VerdictBanner/          # 裁决横幅
│   │   │   ├── RemediationCard/        # 修复卡片
│   │   │   ├── ConflictEvidence/       # 冲突证据链
│   │   │   ├── AuditTrail/             # 审计底稿
│   │   │   └── RuleReload/             # 规则热重载
│   │   ├── pages/
│   │   │   ├── AuditPage.tsx           # 主审核页
│   │   │   └── CasesPage.tsx           # 样本切换页
│   │   ├── hooks/                      # 自定义 Hooks
│   │   ├── types/                      # TypeScript 类型定义
│   │   └── styles/                     # 样式文件
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── rules/                              # CRS 规则配置（后端消费）
│   ├── rules_v1_base.json              # 基准规则
│   └── rules_v2_patch.json             # 增量补丁（热重载演示）
├── design/
│   ├── architecture.md                 # 本文档
│   ├── ui-spec.md                      # UI 设计规范
│   ├── diagrams/                       # 说明性图表
│   │   └── architecture-overview.html  # 架构蓝图
│   └── prototypes/                     # 可交互原型
│       └── react-ui-wireframe.html
├── docs/
│   ├── README.md                       # 文档索引
│   ├── proposal/                       # 原始提案归档
│   └── roadmap.md                      # 项目路线图
├── specs/
│   ├── prd.md                          # PRD
│   ├── data-spec.md                    # 数据模型规格
│   └── adr/                            # 架构决策记录（10 个独立文件）
├── tests/
│   ├── backend/                        # 后端测试
│   │   ├── test_tin_validator.py
│   │   ├── test_verdict_resolver.py
│   │   ├── test_indicia_reasoner.py
│   │   ├── test_api_routes.py
│   │   └── test_e2e_pipeline.py
│   └── frontend/                       # 前端测试
│       ├── components/
│       └── pages/
├── alembic/                            # 数据库迁移
├── pyproject.toml                      # Python 项目配置 + uv 依赖管理
├── uv.lock                             # uv 依赖锁文件
├── Dockerfile                          # 多阶段构建（前端编译 → 后端托管）
├── docker-compose.yml                  # 开发环境编排
├── .env.example                        # 环境变量模板
├── AGENTS.md                           # AI 编码助手规范
└── README.md
```

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

---

## 7. 参考文档

- [PRD](../specs/prd.md) — 完整需求规格
- [数据模型规格](../specs/data-spec.md) — 前后端共享数据契约
- [架构决策记录](../specs/adr/) — 10 个 ADR
- [架构蓝图](./diagrams/architecture-overview.html) — 可视化架构图
- [业务流程](../docs/proposal/business-workflow-design.md) — 业务专家流程设计
- [方案原始需求](../docs/proposal/crosstax-ai-solution%20(from%20ppt).md) — PPT 摘要
