# ADR-007: 阿里云神机百炼 LLM 平台

## 状态
已采纳 (2026-10-23)

## 背景
跨源冲突研判需要 LLM 推理能力，需选择 LLM 服务平台。

## 决策
采用阿里云神机百炼平台，使用 Qwen-Max（主力推理）/ GLM / DeepSeek 等多模型。

## 否决方案
- **自建 LLM 网关**：竞赛时间紧张，无必要
- **直接调用 OpenAI**：竞赛要求 + 阿里云生态集成

## 理由
- 竞赛方提供统一 LLM 服务
- 内含 Qwen/GLM/DeepSeek 等多模型及 Embedding 模型
- 与阿里云 ECS、PG 等基础设施同生态，网络延迟低

## 后果
- API Key 通过环境变量 `DASHSCOPE_API_KEY` 注入
- Vision API 使用 `qwen-vl-max` 模型
- LLM 推理使用 `qwen-max` 模型（主力）
- 通过 `dashscope` Python SDK 调用
