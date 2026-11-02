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
算法标识校验不等于算法已执行，TIN 算子和裁决执行层后续实现。
Python 正则没有执行超时保障；批准规则前还需校验复杂度及限制审核输入长度。
