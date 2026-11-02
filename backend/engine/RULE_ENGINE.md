# CrossTax AI 规则引擎详细设计

## 1. 范围

输入为上游提供的结构化 CRSFormData 和跨源问题列表；输出为规则版本、问题列表和三态裁决。
实现规则注册、验证、数据库版本发布、内存快照、TIN 算子、表单完备性和裁决。
不负责上传、OCR、PDF/HTML 正文提取、AI 字段抽取、跨源 AI 推理、前端、HTTP 路由、审核会话持久化。
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
当前 holder_dob 仅按共享契约接收字符串，不额外发明年龄/成立日期判断规则。

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

数据库使用 devdb/crosstax，六张表关系见 ../infrastructure/db/README.md。
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
加载失败保留旧快照供诊断或显式调用 current()；validate 默认不偷偷使用旧版本继续审核。当前仍每次完整加载校验；轻量 revision 缓存优化留待版本不可变性保障完善后实施。
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

现有测试总计 105 项：校验位和边界、输入类型、Reason A/B/C、日期、三态优先级、
数据库发布、无效候选回滚、热更新快照隔离及历史版本回滚等。
仓库 Case A-E JSON 已按 PRD 和用户确认的 E 热重载定义落地，并通过本地 PostgreSQL 活动规则执行。全部数据为虚构演示，D 的跨源问题由测试上游提供，不替代真实 AI 研判验收。
SQLite 验证使用 schema_translate_map；此前已确认本地 PostgreSQL 六表连通，
完整测试集在隔离 SQLite 上运行；另已在本地 PostgreSQL 导入并激活来源支持的两版规则，并只读运行全部五 Case，不持久化审核输入。
没有提供 AI 调用，因为语义推理和提取不在本轮规则引擎范围。
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

本轮不新增数据库表、不修改 HTTP 路由、不修改活动规则版本。
新增策略与追踪字段要求主后端完整保存 JSON；双方联调前不要假定已有持久化自动包含这些字段。


## 逐规则回归与发布门禁

engine/corpus/rule_regressions.json 为打包随引擎交付的回归矩阵，不依赖仓库 assets 目录。
全球增强目录 66 个选择器均有正例、非法字符、空值和超长边界，共 264 条固定用例。
approve 实际运行门禁后才改变状态，调用方 report 中的 passed=true 不作为通过依据。
activate 也重新运行门禁，以防引擎升级导致历史版本行为变化。
自定义或旧 schema=1 规则必须在审批报告 regression_cases 中提供匹配每个选择器的正反例；
无覆盖或结果不符即拒绝。固定样例是回归依据，不证明官方规则本身绝对完整。
CLI 的 approve --report 输入仍保留，由调用方提供审阅说明及可选的自定义用例。
