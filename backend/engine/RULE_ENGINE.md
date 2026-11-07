# CrossTax AI 规则引擎详细设计

## 1. 范围

输入为上游提供的结构化 CRSFormData 和跨源问题列表；输出为规则版本、问题列表和三态裁决。
实现规则注册、验证、数据库版本发布、内存快照、TIN 算子、表单完备性和裁决。
不负责上传、OCR、PDF/HTML 正文提取、AI 字段抽取、跨源 AI 推理和前端；目前另提供规则校验 HTTP API；Python 内部归档服务为可选能力，HTTP 不调用它，不替代主 AuditSession。
此前的资料导入器独立保留，不在审核执行时调用，不是本引擎启动依赖。

## 2. 模块职责

| 模块 | 职责 |
| --- | --- |
| contracts.py | CRSFormData、AuditIssue、ValidationPolicy、ValidationResult |
| rule_loader.py | 数据库活动版本校验与不可变快照 |
| publication.py | 规则候选注册、显式批准、激活和回滚 |
| tin_validator.py | 清洗、正则、校验位算子、未知法域兜底 |
| completeness.py | 签名、签署日期、无 TIN 豁免理由 |
| verdict.py | 纯严重级别汇总 |
| validation.py | 统一审核入口，持有单一规则快照 |
| ../cli/rule_engine.py | 运维和本地联调命令 |
| ../repositories/rules.py | 统一 SQLAlchemy 读写，不自行提交 |

全部复用现有 Base 和异步 session_factory，不创建新连接池，不修改现有路由。

## 3. 输入输出

CRSFormData 沿用 specs/data-spec.md，严格拒绝字符串冒充布尔值、未知字段和非法法域代码。
签署日期保持字符串，以便缺失、格式错误、未来日期返回 INVALID_DATE，而非仅返回请求结构错误。
不存在的 Reason 枚举属于结构错误；合法枚举缺失或解释不足属于业务问题。
个人 holder_dob 缺失或非法产生业务阻断；实体 holder_dob 为兼容旧请求的可选成立日期别名，推荐使用可选 incorporation_date。实体无需补造日期；不发明年龄或成立年限规则。

ValidationPolicy.today 必须由调用方传入业务日期，避免服务主机时区影响重放。
earliest_signing_date 为可选的团队确认阈值；未提供时仅检查日期有效性和不晚于业务日期。
该历史阈值尚未在项目规格中定量定义，不默认采用一年或其他自行推定的期限。

ValidationResult 包含 rule_version_id、rule_revision、form_issues、indicia_issues、verdict。
问题序列使用 tuple，JSON 序列化后为数组；问题字段与共享 AuditIssue 一致。

## 4. 规则契约与发布

schema_version=1 保留法域键 → regex/algorithm 的旧契约。schema_version=2 为已获用户同意的新结构，根对象包含 schema_version 和 jurisdictions；每个法域对应 TypedRule 列表，增加 rule_id、holder_type、tin_type、source_url、source_section、verification_level。
算法白名单为 MOD11_2、HKID_WEIGHT、NRIC_WEIGHT、REGEX_ONLY。
规则来自上游或团队提供的配置，执行代码不内置国家正则。

版本哈希：对规则 JSON 固定 sort_keys=True、separators=(',', ':')、ensure_ascii=False、allow_nan=False，UTF-8 编码后计算 SHA-256。
规则发布前检查非空、字段类型、算法白名单、两位大写法域代码和正则可编译。
结构检查不等于税法正确性、国家代码有效性、正则复杂度审核或算法适用性确认。
批准由调用方确认，report 作为审核记录保存；不会仅凭模型置信度或 report 内容自动批准。

数据库使用 devdb/crosstax，原六张规则表及两张追加记录表见 ../infrastructure/db/README.md。
register 在短事务中保存完整候选并验证，失败回滚，不留下无效候选。
approve 仅处理 CANDIDATE；activate 只允许 APPROVED，并再次校验规则内容。
激活使用 expected_revision 乐观锁；冲突抛出 ConflictException，调用方重新读取后决定重试。
回滚也是一次新的激活，revision 递增，规则内容和原版本号不变。

## 5. 加载与并发

每次 validate 通过单个 JOIN 查询读取活动版本及 revision，验证完成后替换内存引用。
快照由 frozen dataclass、只读 MappingProxyType、不可变编译规则组成。
每次审核固定一个快照；热更新不影响旧审核，结果绑定实际执行版本。
并发刷新只接受更大 revision，迟到的旧查询不能覆盖新版本。
相同 revision 出现不同 version_id 视为数据异常。

数据库不可达、无活动版本、哈希不匹配、非法规则均抛出系统错误，不输出 AUTO_PASS。
加载失败保留旧快照供诊断或显式调用 current()；validate 默认不偷偷使用旧版本继续审核。当前每次查询仍验证状态、schema 和内容哈希；相同版本复用编译快照，避免重复解析和正则编译，不因缓存跳过内容完整性检查。
不在抓取或 AI 调用期间持有数据库连接。

## 6. 执行顺序

1. 上游构造并验证 CRSFormData。
2. 加载规则快照。
3. 签名及日期完备性检查。
4. has_no_tin 为真时检查 Reason；为假时执行 TIN 校验。
5. 合并上游提供的 indicia_issues。
6. 存在任意 BLOCKER → NEED_USER_FIX；只有 WARNING → MANUAL_TRIAGE；无问题 → AUTO_PASS。
7. 上游流水线负责将结果和输入持久化到 AuditSession。

Reason A/C 要求提供代码；B 还要求去除两端空白后解释长度至少 5。
A/C 的额外法域适用条件尚未实现，因此所有无 TIN 豁免声明均要求人工复核；TIN 与无 TIN 声明矛盾会返回 BLOCKER。
缺签和日期错误可同时返回，不在首个问题处中止。

## 7. TIN 算子

先限制 TIN 原始输入最长 256 字符，移除空白、连字符和圆括号，再转大写。
配置法域执行 fullmatch，然后计算校验位；旧版 schema=1 未知法域仅检查清洗后长度 4-30；schema=2 返回未覆盖 WARNING。
上述长度上限为执行保护，不代表每个法域 TIN 的业务长度。
原始表单不被修改，错误信息不回显敏感号码。

| 算子 | 范围 |
| --- | --- |
| MOD11_2 | 中国 18 位居民身份证校验位，不含企业 USCC |
| HKID_WEIGHT | 单/双字母前缀 HKID，不含企业 BR |
| NRIC_WEIGHT | 新加坡 S/T NRIC，不含 F/G/M FIN、UEN |
| REGEX_ONLY | 仅校验配置正则 |

通过只表示格式/校验位通过，不证明真实签发、主体身份或税籍。
新版契约通过主体和标识类型精确选择规则；已覆盖法域缺少匹配类型时返回 UNSUPPORTED_TIN_TYPE WARNING，而非套用其他主体算法。CRSFormData 新字段可选，以兼容旧调用；新版规则下应明确提供。
Python re 没有执行超时，输入长度限制不能完全避免恶意回溯；仅使用经审核的可信规则，复杂度隔离留待后续。

## 8. 队友接入

在现有 run_audit_pipeline() 中调用，不新增或绕过流水线：

```python
from backend.engine.contracts import AuditIssue, CRSFormData, ValidationPolicy
from backend.engine.rule_loader import RuleLoader
from backend.engine.validation import ValidationEngine
from backend.infrastructure.database import async_session_factory

# 每个服务进程创建一次，复用现有连接池。
validation_engine = ValidationEngine(RuleLoader(async_session_factory))

# 下列代码放入现有异步审核流水线；business_date 由调用方确定。
# form = CRSFormData.model_validate(frontend_json)
# conflicts = [AuditIssue.model_validate(item) for item in upstream_issues]
# result = await validation_engine.validate(
#     form, ValidationPolicy(today=business_date), conflicts
# )
# payload = result.model_dump(mode='json')
```

ValidationError 是输入/规则结构错误；ConflictException 是并发发布或状态冲突；
NotFoundException 是活动版本缺失；数据库异常由现有错误层处理。
这些异常不应转成空问题列表。

## 9. CLI

在项目根目录运行，规则文件由上游提供，不内置或自动发布未经确认的真实规则。

```bash
uv run python -m backend.cli.rule_engine register /path/to/rules.json
uv run python -m backend.cli.rule_engine approve VERSION_ID --report /path/to/review.json
uv run python -m backend.cli.rule_engine activate VERSION_ID --revision 0
uv run python -m backend.cli.rule_engine current
uv run python -m backend.cli.rule_engine validate /path/to/form.json --today 2026-11-02
```

注册可以重复传 --document-id 绑定已存在资料。activate 的 revision 必须是当前数据库修订号。
回滚使用 activate 历史批准版本，并传当前 revision。
可使用 python -m backend.cli.demo_cases --install 安装仓库竞赛规则基线；当前本地已激活最新版。详见 rules/README.md。

## 10. 验证与限制

常规测试为 127 项通过、3 项 PostgreSQL 用例按环境跳过；启用隔离 PostgreSQL 测试后共 130 项通过：校验位和边界、输入类型、Reason A/B/C、日期、三态优先级、
数据库发布、无效候选回滚、热更新快照隔离及历史版本回滚等。
仓库 Case A-E JSON 已按 PRD 和用户确认的 E 热重载定义落地，并通过本地 PostgreSQL 活动规则执行。全部数据为虚构演示，D 的跨源问题由测试上游提供，不替代真实 AI 研判验收。
SQLite 验证使用 schema_translate_map；此前已确认本地 PostgreSQL 六表连通，
完整测试集在隔离 SQLite 上运行；另已在本地 PostgreSQL 导入并激活来源支持的两版规则，并只读运行全部五 Case，不持久化审核输入。
历史阶段未提供 AI 调用；2026-11-04 新增可选补正 Agent，仍不承担字段提取或税收居民身份认定。
新增模块通过 mypy；全项目已有日志模块两处 dict 泛型类型错误仍待队友处理。


## 全球规则集更新

已接入 22 法域 62 条规则，配置和逐国来源见 rules/rules_global_v3.json 与 rules/GLOBAL_COVERAGE.md。
输出新增 tin_check，披露命中规则、官方来源、验证等级和覆盖状态；结构规则不代表号码真实性验证。
Case E 更新前因未覆盖 SG 返回 MANUAL_TRIAGE，更新后识别格式错误返回 NEED_USER_FIX。
本次只核对规则资料，无新增真实税号或客户数据。


## 官方算法增强版本

rules_global_v4.json：22 法域、66 条规则，其中 13 条使用校验位，53 条仅格式。
新增 checksums.py 提供 AU_ABN、NL_MOD11、PL_NIP、PL_PESEL、NO_ORGNR、JP_CORPORATE、CA_SIN、ES_NIF_NIE。
PL_PESEL 还校验日期和世纪月份映射。美国号码段及德国企业 W-IdNr 结构条件已补充。
规则增加可选 algorithm_source_url；编译快照与 tin_check 均保留该字段。
来源依据、类型边界和待补范围详见 rules/GLOBAL_COVERAGE.md，不扩展为税籍或真实号码查询。
八种算子使用官方公开计算说明核对；测试覆盖官方示例、校验位错误、畸形输入和结构限制。
本地 PostgreSQL 已发布增强版本（revision=3），并验证从数据库加载后执行 ABN 算法及来源追踪。


## 审核完整性加固

ValidationPolicy.strict_coverage 默认 true：旧 schema=1 的未知法域在统一入口也转人工复核。
旧版长度兜底仅在显式设置 strict_coverage=false 时兼容；schema=2 始终保持未覆盖转复核。
has_no_tin 路径不再直接自动放行：Reason A/B/C 仅检查声明完整性，未实现法域适用规则，
统一返回 EXEMPTION_REVIEW_REQUIRED WARNING，避免将格式完整误认为豁免成立。
未知法域的豁免同时返回未覆盖 WARNING；缺理由或矛盾仍按 BLOCKER 优先。
新增 INCONSISTENT_TIN_DECLARATION、MISSING_FIELD 业务问题，检查 TIN/无 TIN/理由矛盾和纯空白必填字段。
出生或成立日期检查有效 YYYY-MM-DD 日期，不自行增加年龄或成立年限条件；输入增加合理长度边界。
这些新增问题码与策略属于本次已授权的完整性加固，API 层需保留原样展示。


## 单次执行与可解释追踪

TINValidatorEngine.evaluate 一次返回问题列表和 TINCheck，统一审核入口只执行一次。
validate/trace 保留为独立调用的兼容包装；不要在同一请求里连续调用两个包装。
checks_performed 记录实际执行的规则选择、清洗、格式和校验位；checks_not_performed 列出未执行检查。
格式失败时不会声称运行过校验位，verification_level 为本次实际执行深度。
reason_code 区分输入缺失、格式失败、校验位失败、未覆盖、历史长度兜底和豁免待复核。
无 TIN 的 NOT_APPLICABLE 仅表示未运行号码校验；豁免适用性仍未执行，并在裁决问题中体现。
追踪不回显 TIN 明文，仍返回来源和规则 ID。


## 历史审核复现

输出增加 execution：engine_build_id、input_fingerprint、policy。
engine_build_id 对当前部署的 engine/*.py 源文件内容、Python/Pydantic/SQLAlchemy 版本计算哈希并在进程内缓存；
不依赖本地 Git 是否存在，不把文档提交误判成执行逻辑变更。部署文件必须不可变，升级时重启进程并保留旧构建。
input_fingerprint 对验证后的表单、完整策略（业务日期、最早签署日期、覆盖策略）、有序上游问题计算规范化 JSON SHA-256。
哈希用于完整性核对，不是加密或数字签名，不能单独抵抗具有数据库写权限的攻击。

主后端需保存原始结构化输入、上游问题及完整 ValidationResult；只保存裁决和规则版本不足以重放。
结果不附带敏感表单明文，表单仍由主后端按既有持久化与访问控制处理。
replay(form, original_result, upstream_issues) 使用历史 rule_version_id 和当时的 policy/revision，
不会调用当前活动规则，也不会替换进程内活动快照。
引擎构建不一致、输入/上游问题不一致、历史规则缺失、规则哈希错误或重放结果不一致都会明确失败。
旧结果缺少 execution 也明确拒绝自动重放；不补造历史元数据。
升级算子后必须在原构建环境重放旧审核，不能用新算法冒充原审核逻辑。
规则版本及历史构建均须保留；当前未自动归档构建镜像，需部署负责人配合。

```python
# 当前流程
result = await validation_engine.validate(form, policy, upstream_issues)
# 主后端保存 form、upstream_issues、result.model_dump(mode="json")。
# 历史重放，先通过模型加载保存的 JSON。
# original = ValidationResult.model_validate(saved_result)
# replayed = await validation_engine.replay(form, original, upstream_issues)
```

历史复现阶段没有修改活动规则版本；后续已通过独立 API 和追加归档表提供接入。
新增策略与追踪字段要求主后端完整保存 JSON；双方联调前不要假定已有持久化自动包含这些字段。


## 逐规则回归与发布门禁

engine/corpus/rule_regressions.json 为打包随引擎交付的回归矩阵，不依赖仓库 assets 目录。
全球增强目录 66 个选择器均有正例、非法字符、空值和超长边界，共 264 条固定用例。
approve 实际运行门禁后才改变状态，调用方 report 中的 passed=true 不作为通过依据。
activate 也重新运行门禁，以防引擎升级导致历史版本行为变化。
自定义或旧 schema=1 规则必须在审批报告 regression_cases 中提供匹配每个选择器的正反例；
无覆盖或结果不符即拒绝。固定样例是回归依据，不证明官方规则本身绝对完整。
CLI 的 approve --report 输入仍保留，由调用方提供审阅说明及可选的自定义用例。


## 发布历史与可选内部归档服务

新增 rule_publications，记录每次成功激活的 revision、目标和前一版本、actor、reason、时间。
历史事件与活动指针更新处于同一事务；并发 CAS 失败不写入事件，回滚也是一条新事件。
actor 是调用方提供的标识，不是身份认证证明；应由主后端从认证上下文提供。
迁移前发生的三次本地发布未伪造补录，历史表从迁移后首次激活开始记录。

新增 rule_audit_records，以主后端 session_id 为幂等键保存输入、上游问题、完整结果与输入指纹。
AuditValidationService.validate_and_store 返回前完成短事务存储；存储失败不会返回成功结果。
相同 session_id 和输入重试返回原提交结果，即使当前规则已更新；同 ID 不同输入返回 ConflictException。
并发重复请求通过主键和冲突后查询统一到一条结果，不覆盖历史。
服务拥有独立事务，和主后端 AuditSession 的事务不是跨表原子事务；主后端需按 session_id 重试或对账。
本表是引擎执行信封，不替代队友的主审核表、权限与留存政策。

```python
from backend.engine.audit_service import AuditValidationService
service = AuditValidationService(validation_engine)
# 在队友现有 run_audit_pipeline() 内调用：
# result = await service.validate_and_store(session_id, form, policy, upstream_issues)
# replayed = await service.replay_stored(session_id)
```

已新增结构化规则校验 HTTP 路由，但当前骨架没有完整文件审核业务流水线，不能声称完成真实上传/前端端到端联调。
服务的持久化、幂等、历史重放、发布变更后重试已通过真实 PostgreSQL 测试。

## 历史不可变性与信任边界

支持的 SQLAlchemy Session 写入路径禁止修改/删除审核与发布历史，禁止修改已审批规则。
ORM bulk update/delete 同样受保护，仅候选审批状态转换使用内部标识放行。
底层 Core 连接、原生数据库连接、数据库管理员不在此应用层保护范围，不能宣称数据库级不可篡改。
未新增数据库触发器或变更数据库账号权限，避免破坏 SQLite 兼容和队友连接行为。
普通 User/BaseRepository CRUD 回归测试通过，保护仅针对规则引擎历史模型。
并发注册同内容规则遇到唯一冲突时重新开启事务读取已有版本，不产生重复版本。

## 执行保护与加载复用

规则包最大 1 MiB、最多 1000 个 typed variants；正则最多 512 字符、分组深度最多 12。
采用保守语法检查，拒绝回溯引用、未知分组、重复的含分支/重复子组、无上限计数区间及过多模糊分支。
有限重复上限 64，分支和可变重复采用有限歧义预算；单个无界字符重复受 256 字符输入限制。
该检查器是受限标识正则的防护，不是任意正则的数学时间上界证明或独立进程沙箱。
新格式需满足受限语法；不要为加载任意第三方表达式而关闭保护。
发布套件最多 5000 个用例且 case_id 唯一；CLI JSON 文件最大 1 MiB。

validate 日志仅输出版本、revision、裁决、问题数和耗时；规则加载失败仅记录异常类型。
不写入 TIN、主体名称或完整表单；主后端仍需避免在错误日志回显 Pydantic 原始输入。
相同版本复用编译对象，但每次数据库读取依然验证哈希，内容被篡改不会被缓存掩盖。

## 数据库迁移与集成测试

alembic/versions/20261103_rule_history.py 为通过 autogenerate 生成的扩展迁移，只新增两表，
前提是原六张表已经按 setup SQL 创建。原始 User 模型和业务表不在这次迁移中改变。
迁移已在本地 devdb 应用，使用 func.now() 保持 SQLite/PostgreSQL 默认时间表达式兼容。
新环境先执行原 schema SQL，再运行 uv run alembic upgrade head。

测试参数 CROSSTAX_TEST_DATABASE_URL 指向允许创建临时 schema 的 PostgreSQL 测试数据库。
PostgreSQL 测试创建随机 crosstax_test_ 前缀 schema，先创建原六表，再执行实际 Alembic upgrade，
最后清理且仅清理该测试 schema。测试不重置 crosstax，不覆盖当前规则或业务数据。
覆盖真实并发发布、并发重复注册、错误审批报告、历史修改拒绝、审核归档和重放。
无测试 URL 时仅跳过三个 PostgreSQL 参数化用例；SQLite 路径仍执行同一迁移和生命周期。
回归矩阵随 wheel 打包，已验证离线构建包含全部 264 条用例。

## 交付边界

本轮不扩国家数量、不新增 AI 提取。官方规则仍是 22 法域 66 个选择器，验证深度见覆盖清单。
发布回归检验代码行为和用例覆盖，不自动证明税法完整性、官方来源真实性或新法规已经适用。
仍需队友接入真实 API 并提供认证身份、主会话对账和部署构建归档；当前没有这些实现，未擅自发明接口。


## HTTP 服务接入（单接口）

仅公开 POST /api/v1/rule-engine/validate，详细契约见 backend/api/RULE_ENGINE_API.md。
输入为 form_data、policy、可选 indicia_issues 与 include_guidance，无 session_id。
RuleAPIService 先获取一次固定快照，由 document_validation.validate_document 逐项调用 ValidationEngine.validate_snapshot，并在裁决完成后可选调用补正 Agent。保持原扁平响应字段，并追加逐项结果、范围、来源和建议。
本接口不调用 AuditValidationService，不写规则审核归档表，也不建立或查询会话。
队友在自己的 run_audit_pipeline() 中调用一次并保存自己的请求和响应即可。
原有 validations、结果查询、重放、current/coverage HTTP 路由已移除，不保留隐藏调用步骤。
内部发布 CLI、覆盖查询 CLI、Python 归档/重放服务保留，属于可选内部能力。
保持 1 MiB 请求限制、脱敏错误和现有健康检查；未新增认证体系。
每次请求读取当前活动规则，重复调用可能因规则更新而变化，不提供会话幂等或固定历史结果语义。
HTTP 响应是精简适配契约，不等同于内部 ValidationResult；不要直接将其传入内部 replay 方法。


### 对外文档收敛

OpenAPI 和 Swagger 仅展示 POST /api/v1/rule-engine/validate。健康与就绪探针保持原地址和行为，但不列入契约。关闭重复的 /redoc 文档入口和未使用的 Swagger OAuth2 回调；/docs 与 /openapi.json 保留。隐藏文档不等同于网络访问控制。


## 2026-11-04：多税籍文档校验与补正 Agent

### 模块与职责

- document_contracts.py：多税籍输入、逐项 TIN 结果、公共检查项、问题来源和审核范围。
- document_validation.py：同一文档使用一份不可变快照，逐项校验、定位问题、去除公共重复问题并汇总裁决。
- ../agents/remediation.py：可选工具调用编排、固定补正提示、提示词版本及输出指纹；不调用 DB，不写表，不改裁决。
- API 仍为一个 POST /api/v1/rule-engine/validate。队友在自己的主审核流水线中调用，不新增文件或 OCR 流程。

### 输入与兼容

form_data 支持原 CRSFormData 或 MultiResidenceForm。
API 用可调用 Discriminator 根据 tax_residencies 是否存在选择单／多税籍契约，避免返回两个分支的混杂错误。
多税籍列表要求 1–20 项、地区不能重复；不支持同时传旧版顶层税籍字段和列表。
共同字段为主体姓名、地址、类型、签名、签署日期；多税籍要求明确主体类型。
每个税籍包含 jurisdiction_code、tin_type、tin、has_no_tin、tin_reason_code、tin_reason_explanation。

个人缺失出生日期属于 INVALID_DATE 业务问题，返回 HTTP 200 + NEED_USER_FIX。
实体无需出生／成立日期；incorporation_date 提供时检查格式。
旧实体 holder_dob 继续接受，两种日期同时提供必须一致；个人填写 incorporation_date 产生 UNEXPECTED_FIELD。
原实体请求样例已删除人为补充的成立日期，新增多税籍＋include_guidance 样例。

### 文档执行与可解释结果

一次 loader.refresh 获取快照，在所有税籍完成和 AI 工具读取结束前固定使用该对象。
原有 ValidationEngine 单项入口继续用于 CLI、发布回归和旧内部归档服务。
公共姓名、地址、出生／成立日期、签名和签署日期问题只保留一次；税籍问题路径为 tax_residencies.N.field。
所有 issues 按引擎问题在前、上游问题在后排序，issue_origins 明确 RULE_ENGINE／UPSTREAM。
每个税籍返回 TINCheck 和 issue_indexes，公共 check_items 也引用同一 issues 数组。
多税籍 checks=null，单税籍保持旧 checks 行为；统一使用 residence_results 展示逐地区验证深度。
汇总继续遵循任意 BLOCKER 优先，其次 WARNING，无问题才 AUTO_PASS。

review_scope 明确未核实税籍认定、号码签发与归属、签名真伪、实体分类、控权人、税籍申报是否遗漏及无 TIN 豁免适用性。
AUTO_PASS 表示当前检查无异常，不能展示为整张表格所有法律条件已经满足。
个人／实体日期不是税籍认定依据。

execution.input_fingerprint 哈希整个已验证表单、完整 policy 及有序上游问题；不包含 include_guidance 和模型文案。
修改表单或任意税籍将改变指纹；AI 是否启用不改变确定性输入身份。
主后端保存完整 HTTP 请求和响应；现有内部单税籍 replay/归档接口不能直接重放 HTTP 文档结果。
历史构建重现仍需保留原构建，不能用新代码逐字复现旧结果。

### Agent 流程与证据约束

include_guidance 默认 false，不增加基础校验的模型依赖和调用耗时。
true 时以 Chat Completions 兼容 API 发起工具调用，使用现有 httpx，不增加依赖、队列、向量库或外部 API 路由。

1. get_validation_evidence(issue_index)：只读本次问题代码、严重级别、固定字段路径和来源；上游自由文本不发送模型。
2. get_rule_details(issue_index)：只读本次快照中与该问题关联的规则 ID、正则、校验深度、来源、章节、限制和实际检查轨迹。
3. get_source_excerpt(issue_index)：当前明确返回 available=false，因为未安装核实过的官方正文片段；不实时抓取、不把 URL 当作原文，不生成引文。

模型必须先读取对应问题工具才能为该问题生成动作；只有读取相关规则工具后才能引用其 rule:N。
每个现有问题恰好对应一个 action，issue_index 不得重复或越界，field 必须匹配原问题，且必须引用 issue:N。
rule:N 引用 residence_results[N]，issue:N 引用顶层 issues[N]。
服务端使用 Pydantic 校验输出，并检查引用白名单、字段归属、动作完整性、已读取证据。
额外阻断文案中的 URL、连续六位及以上数字和显式裁决枚举，减少编造链接、标识号码和替代裁决的风险。
这不是对自然语言真实性的形式证明；AI 文案仅辅助补正，不能据此确认税法适用性。
未传原始姓名、完整地址、TIN、自由文本解释或上游 message/code/field 给模型。
上游 field 仅在输出校验完成后由服务端附回，不来自模型。
模型提示词和工具数据不是发布规则的权限，Agent 没有写工具或任意网络抓取工具。

### 调用预算、失败降级与配置

百炼专用接入后 RULE_AI_ENABLED 默认 true，但 include_guidance 默认 false；模型默认 qwen-plus，需填入 RULE_AI_API_KEY 或 DASHSCOPE_API_KEY。
密钥使用 SecretStr，来自环境或 .env，不进入日志、响应或版本库。
接口 include_guidance=true 但配置缺失时返回 FALLBACK/AI_NOT_CONFIGURED。
百炼默认关闭思考、非流式，证据工具调用与最终 JSON Object 输出分阶段；模型不支持时固定提示降级。
进程内最多并发 2 个 Agent，最多 4 轮模型调用、12 次工具调用、每轮最多 8 个工具调用。
默认总预算 8 秒，包含并发排队、工具编排和网络；可配置 0–20 秒范围内的正值。
每次最多输出 2500 tokens、模型响应上限 256 KiB（在接收后检查）；超预算或输出不完整则降级。
模型拒绝、截断、网络错误、格式错误、工具越界和不可信引用不改变核心裁决。
NOT_REQUESTED／GENERATED／FALLBACK 区分未请求、生成成功和固定提示降级。
失败仅记录异常类型，不记录模型响应、个人信息、API Key 或数据库连接信息。

响应记录配置模型标识、prompt_version、提示词哈希、耗时和 summary/actions 输出哈希。
主后端应保存实际 guidance 输出；temperature=0 也不保证重新调用逐字相同。
目前不保存供应商内部模型构建版本，不宣称可以精确重放模型推理。
对未知地区、规则未覆盖和豁免适用性只提示人工复核，不由模型自动放行。
大批问题可能超过工具预算，此时整体补正降级为完整固定提示列表，确定性结果仍正常返回。

### 接口错误与验收

422 新增 details，含安全字段路径、错误类型和固定说明；最多 20 项，不返回 input、ctx、原始异常或任意未知字段名。
未知字段路径用 <unknown> 替代；413、503 和共享异常响应保持现有行为。
请求体仍限制 1 MiB，不新增认证或对外管理接口。

本轮新增测试覆盖实体缺日期、多税籍定位／汇总／公共问题去重／单快照读取、重复与空列表、旧 Case A–E、
缺失个人日期、日期别名冲突、上游来源、AI 工具读取和规则引用、个人信息不外发、
无效引用／字段／输出、不完整建议、超时、服务错误、截断、恶意工具、循环预算和并发限制。
常规测试目前 150 通过、3 个 PostgreSQL 用例未配置时跳过；Ruff 和本次模块 Mypy 校验通过。
尝试开启本地 PostgreSQL 集成测试，但 localhost:5432 拒绝连接，3 个 PG fixture 设置失败，未能完成本轮 PG 复验。
未修改数据库表结构；SQLite 路径与现有持久化测试继续通过。
真实组委会模型未配置／联调，当前 Agent 工具协议通过 MockTransport 测试，不把模拟结果当作模型供应商验收。
仓库没有 frontend/，无法运行 npm test。本轮不修改前端、PM 所有的 specs/、design/、docs/。


## 2026-11-04：百炼专用接入

用户确认供应商为阿里云百炼，后续自行填 Key。本轮将兼容 HTTP 调用抽取为专用客户端，不增加依赖或对外路由。

- ../core/bailian.py：BailianSettings，统一环境配置、HTTPS base URL 校验、默认 qwen-plus；GuidanceSettings 保留别名兼容。
- ../infrastructure/bailian.py：BailianClient，使用现有 httpx 发送百炼 Chat Completions 请求，处理脱敏错误分类。
- ../agents/BAILIAN.md：本地 Key 填充、地域／业务空间地址、curl 联调及降级排查手册。

默认 RULE_AI_ENABLED=true，只有 include_guidance=true 且 Key 非空才发起模型调用。
Key 优先使用非空 RULE_AI_API_KEY，否则使用 DASHSCOPE_API_KEY；本地空占位不会覆盖环境中的标准 Key。
RULE_AI_MODEL 未设置或空白时使用 qwen-plus；密钥仍为 SecretStr，不输出到日志或响应。
本地 .env 仅补充缺失配置，不覆盖原有配置、密钥或数据库连接，不提交 Git。
base URL 必须完整 HTTPS，不允许查询参数、凭据、片段、未替换占位符或尾部 /chat/completions。
北京默认入口仍为 dashscope.aliyuncs.com/compatible-mode/v1；其他地域或业务空间采用控制台完整 base URL。
地区 Key、域名和模型权限必须匹配，参考 [官方地域信息](https://help.aliyun.com/zh/model-studio/regions)。

每次请求明确 stream=false、enable_thinking=false。
证据阶段发送 tools、tool_choice=auto、parallel_tool_calls=true，不同时强制 JSON 输出。
相关问题和匹配规则读取完成后，最终请求去掉 tools，启用 response_format=json_object。
应用端仍校验结构、问题归属、引用和完整性；不能用“模型输出合法 JSON”替代业务检查。
协议依据 [百炼 Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)
与 [非思考模式结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。
提示词版本升级 remediation-v2，并更新 OpenAPI 快照。

401/403/404/429/400 分别映射 AI_AUTHENTICATION_FAILED、AI_PERMISSION_DENIED、
AI_MODEL_OR_ENDPOINT_NOT_FOUND、AI_RATE_LIMITED、AI_REQUEST_REJECTED，其他供应商错误返回 AI_PROVIDER_UNAVAILABLE。
这些均为 guidance.FALLBACK 原因，不改变确定性 verdict、issues 或业务 HTTP 200。
不回传供应商原始错误正文，不自动重试；沿用 8 秒总预算、并发和工具轮数限制。

自动测试增加配置 Key 优先级、空 .env 占位、默认模型、非法 URL、业务空间入口、
两阶段请求参数、供应商错误分类及 Agent 裁决隔离。
真实 Key 尚未填入，因此未发起真实付费调用，也未声称验证真实模型输出质量或延迟。

百炼接入完成后常规测试为 170 项通过、3 项 PostgreSQL 按环境跳过；本轮未修改持久化模型。


## 2026-11-04：通用模型配置与供应商无关错误分类

默认模型使用 DEFAULT_MODEL=qwen-plus，由 RULE_AI_MODEL 覆盖，空白沿用默认值；不硬编码模型白名单，不自动切换其他模型。
部署可显式指定已开通的具体模型版本，减少别名更新对回放和联调的影响。
这是一种配置策略，不宣称所有主流项目拥有统一的默认模型。

../core/ai_errors.py 定义统一 AIErrorCategory、公开 AIErrorInfo(category,retryable)、reason_code 和重试建议。
BailianClient 将 HTTP 状态及已知百炼错误代码映射到通用分类；Agent 补充连接、超时、输出校验、内部及未配置错误。
外部 guidance.error 在成功或未请求时为 null，失败时返回供应商无关类别；保留 reason_code 便于现有队友使用。
内部日志仅记录已知白名单代码、状态和分类，不记录原始消息、任意未知供应商代码或请求值。

分类为 configuration、authentication、permission、quota、rate_limit、timeout、connection、invalid_request、
invalid_response、service_unavailable、internal。
限流、超时、连接和服务不可用标记可重试；其他类别需要先修正配置、资料或程序，不自动重试。
HTTP 408/504 映射 timeout，5xx 映射 service_unavailable，401 映射 authentication，
其余优先识别已知供应商代码，再按 HTTP 状态回退。
Arrearage、BudgetLimitExceeded、insufficient_quota 等识别为额度／账单错误，避免一律按限流处理。
Throttling.AllocationQuota 按官方 token 速率限制处理；供应商同类代码也可能存在套餐差异，重试建议不保证实际恢复。
映射参考 [百炼官方错误码](https://help.aliyun.com/en/model-studio/error-code)。

404 不再单独创造供应商端点错误类型，统一到 invalid_request / AI_REQUEST_REJECTED。
原 AI_OUTPUT_OR_SERVICE_ERROR 拆分为 AI_CONNECTION_ERROR、AI_INVALID_RESPONSE、AI_INTERNAL_ERROR。
此调整仅影响可选 guidance 错误，不改变核心规则 issues、verdict 或 HTTP 200。
测试增加 HTTP／供应商代码矩阵、额度与限流区分、模型环境覆盖、网络与程序错误隔离及敏感诊断不外泄。

通用错误分类完成后：186 项测试通过、3 项 PostgreSQL 按环境跳过，Ruff 与本轮模块 Mypy 通过；真实百炼调用仍待填 Key 联调。


## 后续优化：有限重试、响应限额和调用统计

保持对外单接口、固定规则快照和确定性裁决不变，优化可选模型调用的瞬时故障恢复与观测。
新增 ../core/ai_metrics.py 的 AICallMetrics，每次 generate 单独创建并显式传入客户端，不使用共享计数器。
guidance.metrics 返回 HTTP attempts、全局 retries、排队和网络耗时、已报告 token 和 usage_complete。
整体 duration_ms 仍从请求进入 Agent 开始计算；并发排队、模型轮次及重试等待均计入原有预算。
正常／降级结果均携带统计，不把失败、缺失或非法用量默认为完整零消耗。
Token 数据来自响应的 usage，不是账单预测；任何尝试缺少有效 usage 时总量只表示已知部分。

RULE_AI_MAX_RETRIES 默认 1，范围 0–2；同一个 Agent 内所有模型轮次共享次数，而非每轮分别获得配额。
默认 4 轮模型调用最多产生 5 次 HTTP 尝试。每次客户端调用也根据同一绝对截止时间约束，不能重置预算。
仅自动重试明确可恢复的 HTTP 429 与 500/502/503，且统一分类 retryable 必须为 true。
鉴权、权限、额度、无效请求／输出和内部异常不自动重试；网络异常、读超时及 408/504 不自动重发，减少执行状态不明时的重复调用。
公开 retryable 是一般恢复提示，服务端自动重试采用更保守的范围，不能将两者混同。

Retry-After 支持整数秒及 HTTP 日期。未提供时采用带随机抖动的指数退避。
若要求等待时间加最小发送余量超出剩余预算，则保留原错误直接降级，不截短要求、不等待至超时。
重试遵循 [百炼错误恢复建议](https://help.aliyun.com/en/model-studio/error-code)，同时限制总次数与总时间。

客户端改为应用层流式读取 HTTP 响应，仍请求模型 stream=false，不新增流式产品接口。
接收时累计解码字节超过 256 KiB 即拒绝、关闭连接、不继续累积正文；不再等完整读取后才检查。
已解码响应重建时移除 Content-Encoding、旧 Content-Length 和 Transfer-Encoding，防止重复解压。
输出限制、取消或网络异常将 usage_complete 标记 false，仍按既有分类降级。

测试新增限流后成功、跨轮重试预算、永久／未知执行错误不重试、超预算 Retry-After、HTTP 日期、
显式关闭重试、总截止时间取消、排队超时统计、并发统计隔离、压缩响应和超大响应提前关闭。
旧版说明“不自动重试”由本节更严格的有限策略替代；可设置 RULE_AI_MAX_RETRIES=0 恢复原行为。

本轮验证：203 项测试通过、3 项 PostgreSQL 按环境跳过；Ruff 与本轮模块 Mypy 通过，OpenAPI 快照与运行时契约一致。真实百炼调用仍待填 Key 验证。

## 后台定时规则更新（开发设计）

详细方案见 [后台规则更新与发布设计](RULE_UPDATES.md)。
新增能力将按文档、影响分析、后台编排、定时运行分别交付并 commit；不增加业务 API 或管理 UI。
官方资料抓取与规则启用分离，只消费上游结构化规则候选。已审批版本还需可信策略精确批准影响报告才能自动激活。
文档、影响分析、后台编排和调度包装已分阶段实现；验证记录见 RULE_UPDATES.md。未安装实际 cron，未执行真实规则发布。


## 后台更新交付完成

- impact.py：单／多税籍离线升级影响、规则执行与资料差异、裁决和校验深度退化、被其他问题掩盖的阻断移除。
- ../services/rule_updates.py：资料同步、上游完整候选包、回归和影响门禁、独立审批策略、证据指纹与 CAS 发布。
- ../infrastructure/job_lock.py：Linux/macOS 单机非阻塞锁；../cli/rule_updates.py：impact / run、业务日期、脱敏状态和原子报告。
- scheduling/：每日 cron 与空白可信策略模板；rule-bundle.schema.json / publication-policy.schema.json 为上游契约快照。

没有新增 UI、HTTP API、数据表、顶层依赖或资料提取功能，也没有让 AI Agent 审批规则。
人工 approve 与自动发布授权分离；可信策略绑定版本、影响报告和原文引用四个指纹。
source importer 仍只处理已允许的 OECD 来源，当前 manifest 为 CN/HK/SG，自动更新范围与静态全球目录覆盖不同。
保留旧活动版本，源抓取或门禁失败不会触发自动切换；后置报告失败不撤销已提交发布，需按发布历史核查。
完整命令、状态和部署限制见 [后台规则更新手册](RULE_UPDATES.md)。

本次后台更新交付的最终全套验证为 227 项通过、3 项 PostgreSQL 跳过；无真实官网任务、生产发布或 crontab 安装操作。


## 同步后对外流程适配（2026-11-08）

用户确认按上游黑盒 API 边界审查，存储方式保留。审查见 [职责与差距矩阵](ARCHITECTURE_REVIEW.md)。
新增 structured_contracts.py 与 structured_validation.py，接收 D3 全部字段和三类主体，保持旧请求。
执行字段／声明／香港派生等值检查，日期规范后绑定输入指纹；外部项目策略绑定 form_policy_id。
上游事实缺失不伪造通过。双路抽取、实际跨文档、持股依据、KYC 双值及机构 Ref. No. 的依赖见审查矩阵。
新样例及调用接口见 [结构化接入文档](../api/STRUCTURED_CRS_API.md)。
Docker 补入规则及默认合成 Case，供非 root 用户使用的工作与输出路径准备就绪；未实际构建镜像。


## 持久化异步验证（2026-11-08）

按用户确认的两阶段调用，新增 POST tasks 与 GET tasks/{task_id}，公开 OpenAPI 只展示这两条。
旧同步 validate 保留兼容。主会话 session_id 与规则 task_id 分开，主流程轮询 API 后合并完整结果。
输入、冻结规则／策略与结果认证加密保存，HMAC 幂等，默认保留 24 小时；到期 410 并清理密文。
独立 Worker 使用租约、心跳与 claim token，结果与 SUCCEEDED 原子写入；业务 NEED_USER_FIX 仍是执行成功。
固定截止预算包含排队与执行，不借异步绕过主链路 30 秒要求。
本次增加 cryptography 依赖及两张 ORM 表，SQLite Alembic 升降级已验证；与前述后台规则更新任务独立。
详细设计以 [异步任务设计](ASYNC_TASKS.md)为准，调用／启动见 [任务 API](../api/RULE_TASKS_API.md)。
需要实际配置密钥、升级目标数据库和启动 Worker 才能使用，未代替主系统全量加密／鉴权／抽取。
