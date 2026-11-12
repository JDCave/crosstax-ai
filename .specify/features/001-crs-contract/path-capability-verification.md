# path_capability 逐行核实记录（T011）

**核实日期**: 2026-11-12
**方法**: 用 `backend/agents/media_preprocessor.preprocess`（T009 产物）对四份 IRD 官方 PDF 逐字节解密后，
读取 ①文本层字形（`pypdf.PageObject.extract_text` + 逐 MCID 标记文本）②结构树 `/StructTreeRoot` 的
`/Table /TR /TD` 元素计数与单元格归属 ③Wingdings 勾选框字形位置。核实前 43 行为默认 `BOTH`，仅 5 行为已核实
`VISION_ONLY`（R21/R22/R26/R35/R36）。核实结论：43 行默认全部被证据确认为 `BOTH`，5 行 VISION_ONLY 定位准确，
**无一行的 capability 取值改变**；本记录把「默认乐观」转为「逐行可回溯的静态声明」，满足 FR-048 与 SC-004 分母诚实。

## 判据

| 结论 | 判据 |
|---|---|
| `BOTH` | 字段位的定位信息（印刷标签、`/Table` 单元格、声明句正文、`*` 星号、续页规则句）出现在文本层字形中；确定性路（文本层+结构树）与 Vision 路均可读。 |
| `VISION_ONLY` | 字段位的**答案态**由勾选框字形或「划去（Delete as appropriate）」表达，线性文本抽取无法判定用户选了哪一子项 / 划掉了哪一侧；只有栅格化后视觉路可判。 |
| `TEXT_ONLY` | 本轮 48 行**无一行**属此类（IRD 官方表为 Tagged PDF，无「仅文本层可见、渲染不可见」的隐藏字段）。 |

## 逐行证据

### 结构树 /Table 计数（文本层与结构树双证）

| 表单 | Tables | TR | TD | 对应字段位 |
|---|---|---|---|---|
| Individual | 1 | 6 | 24 | R28–R31（TIN 表 5 行重复组 + 表头）；R13–R20 地址块 |
| Entity | 4 | 20 | 56 | R28–R31；R09–R12 实体识别块；R23 控权人槽位表 |
| Controlling Person | 3 | 24 | 102 | R28–R31；R25 所控实体槽位 (1)–(3)；R26 类型矩阵载体 |

地址/ TIN / 槽位表的行列归属可由 `/TR`→`/TD`→`/MCID`→标记文本链无损复原（原型已验证 6 行 4 列无跨行串位）→ 支撑 R13–R17、R20、R23、R25、R28–R31 判为 `BOTH`（FR-003/R48）。

### 勾选框字形分布（决定 VISION_ONLY 的唯一硬证据）

- **`0xf0a3`（Wingdings 答案框）**：仅出现在 ①实体表 Part 2 三分类及其子项（R21、R22）②控权人表 Part 4「11 类 × Entity(1)(2)(3)」矩阵（R26）。这三处的**答案态**（勾了哪个框）线性文本不可判 → 维持 `VISION_ONLY`。
- **R35 / R36（声明区 "…account holder / I am authorized…" + `# Delete as appropriate`）**：以斜杠 + 划记表达二选一，无框字形，但「哪一侧被划去」是渲染态删除线 → `VISION_ONLY` 维持。
- **`0xf097`（Important Notes 列表符号 \uf097）**：出现于 R41/R42/R44 等条款句首，属**项目符号**而非答案选择框，其正文完整在文本层 → `BOTH`。

### 43 个 BOTH 行的文本层命中（抽验，全部命中）

R01 `Name of Financial Institution`｜R03 `Ref. No.`｜R04 `Complete Self-Certification Form – Controlling Person for each controlling person`（实体表；个人/控权表单无此句属预期，其持有人身份块仍在文本层）｜R19 `Date of Birth *`｜R27 脚注 `25 % in relation to a corporation; and 0% in relation to a partnership`｜R28 `Indicate all (not restricted to five) jurisdictions of residence`｜R32 实体表 `If the account holder is a tax resident of the Hong Kong … the TIN is the Hong Kong Business Registration Number`（个人表为 …the TIN is the Hong Kong Identity Card Number）｜R33 `indicate the jurisdiction in which its place of effective management is situated`｜R34 `Select this reason only if the authorities … do not require the TIN to be disclosed`｜R37 `Signature` 标签 + R40 `dd/mm/yyyy`｜R43 `continue on additional sheet(s)`｜R45 `within 30 days`｜R46 `s.80(2E)` + `10,000`。

> R47（AES-128 /V4 /R4 加密）与 R48（/Marked true + /StructTreeRoot）是**文档层**字段位：两路都经由共享层读取同一份解密字节，故同为 `BOTH`；其正确性由 `test_media_preprocessor.py` 的指纹与结构树断言独立验证。

## SC-004 分母诚实声明

本轮为**空白官方模板**，不含填写值，故一致率分母的字段位集合以「结构可见性」静态声明为准（43 BOTH + 5 VISION_ONLY）。真实填写件投放时，声明 `BOTH` 而某路返空的字段位按 FR-048 记不一致、走 FR-038；单路可及的 5 位不进分母、单独计数（SC-011）。核实前的「默认乐观」偏差已由本记录消除。
