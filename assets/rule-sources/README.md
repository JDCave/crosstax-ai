# 官方规则资料导入

`oecd.json` 包含从 OECD TIN 官方入口核对的 CN/HK/SG 文档地址：
https://www.oecd.org/en/networks/global-forum-tax-transparency/resources/aeoi-implementation-portal/tax-identification-numbers.html

从项目根目录运行（先配置 `.env`，并使用已有六张表）：

```bash
uv run python -m backend.cli.rule_sources --manifest assets/rule-sources/oecd.json --sync
```

只登记来源可省略 `--sync`；重复登记不会覆盖已禁用来源。后续同步：

```bash
uv run python -m backend.cli.rule_sources --sync
```

每日执行可以由部署机器的 cron 配置，例如每日 02:00（采用部署机器时区）：

```cron
0 2 * * * cd /absolute/path/crosstax-ai && /absolute/path/crosstax-ai/.venv/bin/python -m backend.cli.rule_sources --sync --scheduled
```

此配置仅为示例，本次未安装系统定时任务。部署时应保证仅一个同步进程运行；如需使用多个调度器，后续增加任务租约。
命令返回同步任务 ID 和逐来源结果；全部成功退出 0，部分/全部失败退出 1。

## 行为与边界

- 仅允许 HTTPS 的 www.oecd.org，重定向逐次校验，最多跟随三次。
- 每次请求超时 20 秒，网络/超时失败重试一次，单份文档最多 10 MiB。
- 支持 PDF、HTML、纯文本。PDF 检查文件头；HTML/PDF 保存原始字节，纯文本同时写入 extracted_text。
- 使用 ETag/Last-Modified 条件请求，并使用 SHA-256 去重；304 必须能找到已有文档。
- 一个来源失败不撤销其他来源导入，汇总为 PARTIAL；所有来源失败为 FAILED。
- 网络请求期间不占用数据库事务；写入失败回滚当前来源，已有文档和活动规则保持不变。
- 源文件更新会保存新文档，不修改旧文档；固定 URL 失效时需更新来源配置，本版本不自动发现替代链接。
- 本阶段导入的是原始规则资料，不是可执行规则；PDF/HTML 正文提取、AI 规则生成和发布属于后续阶段。
- 同步中断可能留下 RUNNING 任务；不自动回收，以免误终止其他进程，需人工检查。
- 不修改现有 API、应用生命周期，不自动抓取或发布规则。
