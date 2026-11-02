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

规则集沿用法域键 → regex/algorithm 的 JSON 对象；禁止额外规则字段。
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
加载失败保留旧快照供诊断或显式调用 current()；validate 默认不偷偷使用旧版本继续审核。
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
当前不推定 A/C 的额外法域适用条件，也不自行判定 has_no_tin 与已有 tin 同时出现的业务语义。
缺签和日期错误可同时返回，不在首个问题处中止。

## 7. TIN 算子

先限制原始输入最长 256 字符，移除空白、连字符和圆括号，再转大写。
配置法域执行 fullmatch，然后计算校验位；未知法域仅检查清洗后长度 4-30。
上述长度上限为执行保护，不代表每个法域 TIN 的业务长度。
原始表单不被修改，错误信息不回显敏感号码。

| 算子 | 范围 |
| --- | --- |
| MOD11_2 | 中国 18 位居民身份证校验位，不含企业 USCC |
| HKID_WEIGHT | 单/双字母前缀 HKID，不含企业 BR |
| NRIC_WEIGHT | 新加坡 S/T NRIC，不含 F/G/M FIN、UEN |
| REGEX_ONLY | 仅校验配置正则 |

通过只表示格式/校验位通过，不证明真实签发、主体身份或税籍。
现有单法域单规则契约不能完整表达同国个人/实体多种 TIN，不能把上述个人算子套用于所有主体。
扩大范围前须团队扩展契约，并由规则提供方确认规则。
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
未生成或激活生产规则，本次不写入演示规则到你的数据库。

## 10. 验证与限制

现有测试总计 32 项：校验位和边界、输入类型、Reason A/B/C、日期、三态优先级、
数据库发布、无效候选回滚、热更新快照隔离及历史版本回滚等。
五条集成路径为合成测试，仓库尚无正式 Case A-E 数据，不能宣称已通过正式五 Case 验收。
SQLite 验证使用 schema_translate_map；此前已确认本地 PostgreSQL 六表连通，
完整执行测试在隔离 SQLite 上运行，未向 PostgreSQL 写入规则或业务测试数据。
没有提供 AI 调用，因为语义推理和提取不在本轮规则引擎范围。
新增模块通过 mypy；全项目已有日志模块两处 dict 泛型类型错误仍待队友处理。
