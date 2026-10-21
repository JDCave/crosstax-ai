# CrossTax AI — Streamlit UI 设计规范

> **版本：** v1.0 | **日期：** 2026-10-22 | **作者：** PM + Designer  
> **关联线框图：** [streamlit-ui-wireframe.html](./streamlit-ui-wireframe.html)  
> **输入来源：** `specs/crosstax-ai-prd.md` §F8  
> **状态：** 草案，待团队评审

---

## 1. 设计概述

### 1.1 设计目标

为 CrossTax AI 合规审核引擎设计一套 Streamlit 演示界面，满足以下目标：

- **竞赛演示**：5 个典型 Case 一键切换，三态裁决完整展示
- **操作直觉**：上传即审核，结果一目了然
- **信息密度**：数据驱动，高 data-ink ratio，避免装饰
- **技术亮点**：规则热重载可视化，审计底稿可溯源

### 1.2 用户角色与界面映射

| 角色 | 界面区域 | 核心操作 |
|------|----------|----------|
| 商户 | 文件上传、修复卡片 | 上传 CRS 表单、查看整改建议 |
| 合规官 | 裁决横幅、冲突证据链、审计底稿 | 审核冲突、下载报告 |
| 管理员 | 规则版本、热重载按钮 | 加载规则补丁、验证生效 |
| 评审 | 全部区域 | 切换 Case、观察完整流程 |

---

## 2. 布局规范

### 2.1 整体结构

```
┌─────────────────────────────────────────────────┐
│  Streamlit App                                   │
│  ┌──────────┐  ┌──────────────────────────────┐ │
│  │ Sidebar   │  │ Main Content                 │ │
│  │ (260px)   │  │ (flex: 1)                    │ │
│  │           │  │                              │ │
│  │ • Logo    │  │ • Pipeline Status            │ │
│  │ • 样本选择 │  │ • Verdict Banner             │ │
│  │ • 文件上传 │  │ • Data Grid (2-col)          │ │
│  │ • 规则版本 │  │ • Audit Trail                │ │
│  │ • 热重载   │  │                              │ │
│  └──────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 2.2 Streamlit 实现

```python
import streamlit as st

st.set_page_config(
    page_title="CrossTax AI",
    page_icon="🌐",
    layout="wide",           # 宽屏模式
    initial_sidebar_state="expanded"
)

# Sidebar
with st.sidebar:
    st.title("CrossTax AI")
    st.caption("Global Compliance Audit Engine")
    
    case_selected = st.selectbox("样本选择", CASES)
    uploaded_file = st.file_uploader("文件上传", type=["pdf", "jpg", "png"])
    
    st.divider()
    st.caption("规则版本")
    st.code(rule_engine.current_version)
    
    if st.button("⟳ 加载 OECD 规则补丁"):
        with st.spinner("热重载中..."):
            rule_engine.load_rules(patch_path)
        st.success(f"已加载 → {rule_engine.current_version}")

# Main
col1, col2 = st.columns([2, 3])
```

### 2.3 尺寸与间距

| 属性 | 值 | 说明 |
|------|-----|------|
| 最小分辨率 | 1280 × 720 | 竞赛演示屏幕 |
| Sidebar 宽度 | 260px | Streamlit 默认 |
| Main 内边距 | 20px | 内容区呼吸感 |
| 组件间距 | 12px | 同区块内 |
| 区块间距 | 16px | 不同区块间 |
| Grid 列数 | 2 (等分) | st.columns(2) |

---

## 3. 页面状态设计

### 3.1 五种核心状态

| 状态 | 对应 Case | 裁决 | 关键展示 |
|------|-----------|------|----------|
| **初始态** | — | — | 空上传区 + 引导文案 |
| **审核中** | 任意 | — | Pipeline 逐步点亮 + Spinner |
| **AUTO_PASS** | Case A | 绿色横幅 | 全字段通过 + 校验结果表 |
| **NEED_USER_FIX** | Case B/C | 红色横幅 | 修复卡片（字段级提示） |
| **MANUAL_TRIAGE** | Case D | 琥珀色横幅 | 冲突证据链 + 置信度 |

### 3.2 状态流转

```
初始态 → [上传文件] → 审核中 → [Pipeline 完成] → AUTO_PASS / NEED_USER_FIX / MANUAL_TRIAGE
                                                              │
                                                              └→ [切换 Case] → 审核中 → ...
```

### 3.3 审核中动画

```python
# Pipeline 逐步展示
steps = ["接收材料", "多模态提取", "税规推理校验", "跨源冲突研判", "决策与闭环"]

for i, step in enumerate(steps):
    with st.status(f"Step {i+1}: {step}", expanded=True) as status:
        st.write(f"正在执行 {step}...")
        # 模拟处理
        result = run_step(i, form_data)
        status.update(label=f"Step {i+1}: {step} ✓", state="complete", expanded=False)
```

---

## 4. 组件规范

### 4.1 裁决横幅 (Verdict Banner)

使用 Streamlit 原生组件，配合自定义 CSS：

```python
if verdict == "AUTO_PASS":
    st.success("✅ 审核通过 — 纳税声明自动生效", icon="✅")
elif verdict == "NEED_USER_FIX":
    st.error(f"❌ 表单存在阻断级错误，需修正后重新提交 ({blocker_count} BLOCKERS)", icon="❌")
elif verdict == "MANUAL_TRIAGE":
    st.warning(f"⚠️ 检测到税籍指示冲突，需合规官人工复核 ({warning_count} WARNINGS)", icon="⚠️")
```

### 4.2 修复卡片 (Remediation Card)

```python
for issue in form_issues:
    if issue.severity == "BLOCKER":
        with st.expander(f"🔴 {issue.code} — 字段: {issue.field}", expanded=True):
            st.markdown(f"**问题：** {issue.message}")
            st.info(f"💡 **修改建议：** {get_remediation_hint(issue.code)}")
```

### 4.3 冲突证据链 (Conflict Evidence)

```python
for conflict in indicia_issues:
    with st.expander(f"🟡 {conflict.scenario} — 置信度: {conflict.confidence:.0%}", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**申报值：** {conflict.declared_value}")
        with col_b:
            st.markdown(f"**底表值：** {conflict.source_value}")
        st.caption(f"冲突说明：{conflict.description}")
```

### 4.4 数据表格 (CRSFormData)

```python
extracted_data = {
    "字段": ["holder_name", "jurisdiction_code", "tin", "has_signature", "signing_date"],
    "值": ["ACME Trading Ltd", "HK", "A123456(7)", "True", "2026-09-01"],
    "置信度": ["95%", "92%", "60% ⚠️", "45% ⚠️", "88%"]
}
st.dataframe(pd.DataFrame(extracted_data), use_container_width=True, hide_index=True)
```

### 4.5 审计底稿 (Audit Trail)

```python
with st.expander("📋 审计底稿 · Audit Trail", expanded=False):
    st.code(f"""
Session ID:    {session.session_id}
Merchant ID:   {session.merchant_id}
File Hash:     {session.file_hash}
Rule Version:  {session.rule_version_id}
Verdict:       {session.verdict}
Timestamp:     {session.timestamp.isoformat()}
    """, language="text")
    
    st.download_button(
        label="↓ 下载 HTML 审计报告",
        data=generate_audit_report(session),
        file_name=f"audit_{session.session_id}.html",
        mime="text/html"
    )
```

### 4.6 规则热重载 (Hot Reload)

```python
st.subheader("规则版本管理")
col_curr, col_patch = st.columns(2)

with col_curr:
    st.markdown("**当前规则**")
    st.code(rule_engine.get_summary(), language="json")

with col_patch:
    st.markdown("**补丁规则**")
    if st.button("⟳ 加载 OECD 规则补丁"):
        with st.spinner("热重载中..."):
            rule_engine.load_rules(patch_path)
        st.success(f"✓ 已加载 → {rule_engine.current_version}")
        st.code(rule_engine.get_patch_summary(), language="json")
```

---

## 5. 色彩规范

### 5.1 语义色彩

| 语义 | 色值 | 用途 | Streamlit 映射 |
|------|------|------|----------------|
| PASS / 成功 | `#16a34a` | AUTO_PASS、校验通过 | `st.success()` |
| FIX / 错误 | `#dc2626` | NEED_USER_FIX、BLOCKER | `st.error()` |
| TRIAGE / 警告 | `#d97706` | MANUAL_TRIAGE、WARNING | `st.warning()` |
| INFO / 信息 | `#2563eb` | 链接、下载按钮 | `st.info()` |

### 5.2 中性色

| 元素 | 色值 | 说明 |
|------|------|------|
| 背景 | `#f8fafc` | Streamlit 默认 |
| 画布 | `#ffffff` | 内容区 |
| 边框 | `#cbd5e1` | 分割线 |
| 主文字 | `#0f172a` | 标题、正文 |
| 副文字 | `#64748b` | 标签、说明 |

---

## 6. 字体规范

| 类型 | 字体栈 | 用途 |
|------|--------|------|
| UI 字体 | `system-ui, -apple-system, 'Segoe UI', sans-serif` | 标题、正文、按钮 |
| 数据字体 | `'SF Mono', Monaco, Consolas, monospace` | 字段名、值、代码、版本号 |

### 字号层级

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| H1 | 22px | 700 | 页面标题 |
| H2 | 15px | 600 | 区块标题 |
| Body | 12-13px | 400 | 正文内容 |
| Label | 10-11px | 500 | 标签、大写 |
| Data | 11px | 500 | 数据值、mono |
| Badge | 9-10px | 600 | 徽章、大写 |

---

## 7. 交互规范

### 7.1 状态反馈

| 操作 | 反馈方式 | 时长 |
|------|----------|------|
| 文件上传 | `st.spinner("处理中...")` | 直到完成 |
| Pipeline 执行 | 逐步 `st.status()` 点亮 | 每步 1-3s |
| 热重载 | `st.spinner("热重载中...")` → `st.success()` | ≤ 3s |
| 报告下载 | 浏览器原生下载 | 即时 |

### 7.2 错误处理

| 场景 | 处理方式 |
|------|----------|
| 文件格式不支持 | `st.error("仅支持 PDF / JPG / PNG / WEBP")` |
| Vision API 超时 | `st.warning("Vision API 响应超时，已切换为手动输入模式")` |
| 规则加载失败 | `st.error("规则文件解析失败，保持当前版本")` |
| 文件过大 (>50MB) | `st.warning("文件过大，请压缩后重试")` |

### 7.3 可访问性

- 所有颜色对比度 ≥ 4.5:1（WCAG AA）
- 图标配合文字说明，不单独依赖颜色传达信息
- 键盘可导航（Streamlit 原生支持）

---

## 8. 实现清单

### 8.1 文件结构

```
src/
├── app.py                    # Streamlit 主入口
├── ui/
│   ├── components/
│   │   ├── verdict_banner.py # 裁决横幅组件
│   │   ├── remediation_card.py # 修复卡片组件
│   │   ├── conflict_evidence.py # 冲突证据链组件
│   │   ├── data_table.py     # 数据表格组件
│   │   └── audit_trail.py    # 审计底稿组件
│   └── pages/
│       ├── main_page.py      # 主审核页面
│       └── hot_reload_page.py # 热重载演示页面（可选）
```

### 8.2 开发优先级

| 优先级 | 组件 | 估时 |
|--------|------|------|
| P0 | 主布局 + Sidebar | 0.5d |
| P0 | Pipeline 状态展示 | 0.5d |
| P0 | 裁决横幅 | 0.5d |
| P0 | 数据表格 | 0.5d |
| P1 | 修复卡片 | 1d |
| P1 | 冲突证据链 | 1d |
| P1 | 审计底稿 + 下载 | 0.5d |
| P1 | 热重载演示 | 0.5d |
| **合计** | | **5d** |

### 8.3 验收标准

- [ ] 5 个 Case 可一键切换，主区域自动刷新
- [ ] 三态裁决横幅颜色正确（绿/红/琥珀）
- [ ] BLOCKER 修复卡片字段级提示准确
- [ ] WARNING 冲突证据链高亮显示
- [ ] 热重载按钮点击后 ≤ 3s 显示新版本
- [ ] 审计报告 HTML 可下载，含完整溯源信息
- [ ] 1280×720 分辨率下布局无错位

---

## 9. 参考文档

- [PRD §F8](../specs/crosstax-ai-prd.md) — Streamlit 演示 UI 功能定义
- [架构设计 §2.1](./architecture-overview.md) — 展现层设计
- [线框图](./streamlit-ui-wireframe.html) — 可视化原型
- [Streamlit 文档](https://docs.streamlit.io/) — 组件 API 参考
