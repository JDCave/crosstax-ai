# 规则引擎：数据库规则加载

本模块只消费规则配置，不负责官方资料采集、正文提取或 AI 抽取。
规则 JSON 遵循现有 specs/data-spec.md：法域代码为键，值包含 regex 和 algorithm。
不在本模块内置未经确认的国家规则。

```python
from backend.engine.rule_loader import RuleLoader
from backend.infrastructure.database import async_session_factory

loader = RuleLoader(async_session_factory)
# 审核开始时调用；数据库未配置活动版本时明确报错。
snapshot = await loader.refresh()
# 本次审核始终持有 snapshot，并把 snapshot.version_id 写入审核结果。
```

加载时检查：APPROVED 状态、schema_version=1、规范化规则内容 SHA-256、
非空规则集、两位大写法域代码、算法白名单、正则可编译。
候选规则完整验证后才替换内存快照，旧审核不会被热更新影响。
并发刷新使用发布 revision 防止旧请求覆盖新结果；回滚也必须通过发布流程递增 revision。
失败会抛出异常，旧快照仍可通过 current() 获取；调用方必须明确处理失败，不能宣称已加载新版本。

目前未向应用启动流程或队友路由自动注入 loader；由审核流水线调用。
TIN 算子、形式完备性、裁决、规则发布及 CLI 已实现。完整设计与接入方式见 [RULE_ENGINE.md](RULE_ENGINE.md)。
Python 正则没有执行超时保障；批准规则前还需校验复杂度及限制审核输入长度。


## TIN 执行

```python
from backend.engine.tin_validator import TINValidatorEngine

# snapshot 由 loader.refresh() 获取，并在本次审核期间固定。
issues = TINValidatorEngine().validate(tin, jurisdiction_code, snapshot)
```

返回符合 AuditIssue 契约的问题列表；空列表表示本次检查通过，不表示号码真实存在或税籍得到确认。
先移除空白、连字符和括号并转大写，再全匹配配置正则，最后执行算法。
未知法域按现有架构规格仅检查清洗后长度 4-30，不宣称完成国家算法验证。
输入原文超过 256 字符直接返回 INVALID_TIN，避免对超长输入运行正则；不会覆盖原始表单值。
无 TIN 豁免由后续完整性模块决定是否跳过 TIN 检查，本接口直接收到缺失 TIN 会报错。

算子适用范围：
- MOD11_2：18 位中国居民身份证校验位，不适用于企业统一社会信用代码。
- HKID_WEIGHT：一个或两个字母前缀的 HKID，不适用于香港企业 BR 号码。
- NRIC_WEIGHT：S/T 系列 NRIC，不包含 FIN F/G/M、UEN 或其他新加坡标识。
- REGEX_ONLY：仅执行数据库中配置的正则。

算法常量属于算子实现；国家正则和算法选取仍来自数据库，代码没有内置国家规则。
规则发布者必须区分个人/实体及标识类型。当前共享契约每个法域只有一条规则，
若需覆盖同一国家多种主体，必须先由团队扩展规则和输入契约，不能将个人算法套用于所有 TIN。

参考资料：
- 中国居民身份证标准 GB 11643-1999：https://zjw.beijing.gov.cn/Portals/0/zhuanti/fazhan/身份证GB11643-1999.pdf
- HKID 算法作者实现：https://github.com/shermanfcm/HKID
- OECD 香港、新加坡 TIN 文档见 assets/rule-sources/oecd.json，仅作为标识类型/格式依据。

测试覆盖算法校验位、清洗、格式失败、缺失/超长、未知法域兜底及快照隔离。
HKID/NRIC 测试向量不代表官方认证；上线前应由规则提供方确认适用范围和算法依据。


2026-11-02 更新：已接入带来源的 schema v2 个人/实体规则与仓库 Case A-E，旧规则继续兼容。范围、命令及例外见 [规则基线说明](../../rules/README.md)。
