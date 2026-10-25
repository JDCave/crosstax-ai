# ADR-001: Python 作为主语言

## 状态
已采纳 (2026-10-22)

## 背景
CrossTax AI 需要快速集成 LLM、OCR 等 AI 能力，竞赛周期紧张。

## 决策
采用 Python 3.11+ 作为项目主语言，后端使用 FastAPI 框架。

## 否决方案
- **Java / Go**：团队技术栈统一优先，AI 生态（LangChain、DashScope SDK）Python 最成熟

## 理由
- 团队全员熟悉 Python，无学习成本
- LLM/OCR 生态成熟，第三方 SDK 首选 Python
- FastAPI 原生 async 支持，性能满足竞赛需求

## 后果
- 后端依赖通过 `pyproject.toml` + `uv` 管理
- 需确保 Python 3.11+ 环境一致性
