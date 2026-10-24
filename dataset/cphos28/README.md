# CPHOS28 来源忠实度评测数据集

本文保留数据准备阶段的说明。全部命令在仓库根目录运行。完整服务与三方案对比的入口见根目录 README；旧 `evaluate_llm.py` 仍可用于单模型诊断。

将用户提供的第 28 届 CPHOS 理论试题及参考答案转换为 Citation Grounding & Faithfulness Verifier 的评测数据。现有 **46 条样例、58 条标准声明、48 个规范化来源片段**，覆盖全部 7 道大题。测试模型、地址及密钥由使用者配置。

这里测试的是模型能否依据给定材料拆分声明、分类并给出引用。题目和解答的选录片段进入 `context_passages`；正确改写或有意修改的回答进入 `generated_answer`；`expected` 保存标准判断和证据。即使答案在物理学中成立，只要输入材料不足以支持，仍标为 `UNSUPPORTED`。这不是让模型独立解整张试卷的题库。

## 文件

| 文件 | 用途 |
| --- | --- |
| `dataset/cphos28/inputs.jsonl` | 可逐行直接发送到 `POST /verify` 的请求，每行只有两个输入字段，无标准标签 |
| `dataset/cphos28/gold.jsonl` | 按样例 ID 保存标准声明、标签、理由和引用 |
| `dataset/cphos28/manifest.jsonl` | 输入行号、ID、主题、类别、划分；与输入和 gold 一一对应 |
| `dataset/cphos28/cases.jsonl` | 完整评测主文件，包含 input、expected、来源 ID、构造说明 |
| `dataset/cphos28/sources.json` | 原 PDF 路径及 SHA-256，片段文字、PDF 页码、公式定位、转录方式 |
| `dataset/cphos28/problem_catalog.json` | 7 道大题的问题摘要及原题/解答页码 |
| `dataset/cphos28/SOURCE_REVIEW.md` | 转录规则、原解答疑点和排除记录 |
| `dataset/cphos28/validation_report.json` | 数据结构、引用和本地 PDF 哈希校验结果；不是 LLM 性能报告 |

`question` 是人工查看时使用的问题摘要元数据，依据原作业接口不发送给 `/verify`。输入自身包含判断所需条件。`sources.json` 还保留少量未用于当前案例的已选录片段，供追溯及后续扩展。

## 数据组成与划分

| 类别 | 核心案例数 | 内容 |
| --- | ---: | --- |
| `supported` | 7 | 完全有依据的回答 |
| `subtle_distortion` | 14 | 符号、指数、系数、数字及条件的细微错误 |
| `extrinsic_hallucination` | 7 | 未给出的材料、微观参数或数值 |
| `multi_passage_synthesis` | 7 | 数值代入、时长求和、变量替换、关系综合 |
| `mixed` | 7 | 同一回答各有一条支持、反驳和无依据声明 |

另有 4 条诊断样例：空上下文、空回答、纯感谢用语、选择性移除证据。核心集有 21 条 `SUPPORTED`、21 条 `CONTRADICTED`、14 条 `UNSUPPORTED`；加上边界集后，三类数量为 21、21、16。

按完整题号分组，避免同一道题的正确版本和错误版本跨越开发集与测试集：

| 划分 | 题目 | 案例数 |
| --- | --- | ---: |
| `dev` | 一：光学；三：绝热活塞；四：直线感应电机 | 18 |
| `test` | 二：悬链线；五：飞盘；六：弦球链；七：加速坐标与盎鲁效应 | 24 |
| `edge` | 独立边界诊断 | 4 |

先在 `dev` 调整提示词，冻结方案后再运行 `test`，`edge` 单列报告。主题划分也会带来难度差异，18/24 条不足以代表广泛领域性能；若要完成原作业的通用 benchmark，可继续加入技术/系统问答。

## 本地校验

需要 Python 3.11 或更新版本，仅用标准库，无需安装第三方包。在本目录运行：

```powershell
python scripts/validate_dataset.py --export --output-report dataset/cphos28/validation_report.json
```

`--export` 从主文件重新导出 inputs、manifest、gold。额外加上 `--check-local-sources` 会读取 `sources.json` 中记录的本地 PDF 路径，核对 SHA-256。常规校验和模型测试不需要原 PDF 在本机存在。

程序检查声明枚举、引用数量、整数下标（拒绝布尔值）、精确非空子串、答案片段、来源一致性、页码、ID、按题分组的划分以及多段证据标注。可选引用偏移须成对提供 `start_char`、`end_char`，使用 Unicode 字符位置及左闭右开区间 `[start_char, end_char)`。这些检查不替代对语义和物理公式的复核。

脚本的异常输入回归测试可用 `python -m unittest discover -s tests -v` 运行，不调用外部模型。

## 配置并测试 LLM

下面已填好 DeepSeek 官方接口和 `deepseek-flash` 模型，只需替换密钥。在 PowerShell 中设置当前会话的环境变量；`.env.example` 已同步这些值，但仅作配置示例，脚本不会自动加载 `.env`。

```powershell
$env:LLM_BASE_URL = "https://api.deepseek.com"
$env:LLM_MODEL = "deepseek-flash"
$env:LLM_API_KEY = "在这里填你的DeepSeek_API_Key"

python scripts/evaluate_llm.py --split dev --limit 2 --json-mode --max-output-tokens 16384 --timeout 180
```

此配置于 2026-10-20 核对 [DeepSeek 官方接入说明](https://api-docs.deepseek.com/) 与 [思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode)。沿用服务端默认开启的思考模式，输出 token 上限设为 16384、单次请求超时 180 秒，并启用 JSON 输出；没有预填费用或调用真实 API。

脚本会在 base URL 后追加 `/chat/completions`，因此不要把完整 completion 路径填入 `LLM_BASE_URL`。这次完整请求地址为 `https://api.deepseek.com/chat/completions`。本地无鉴权接口可不设置密钥。不同厂商只要兼容该消息及响应结构即可接入；其他协议需要适配。

两种测试模式分别回答不同问题，报告应分开比较：

- `--mode end-to-end`（默认）：只发上下文和待验证回答，由模型拆分全部声明、判断并引用，符合原作业的验证流程。
- `--mode fixed-claims`：额外给出标准拆分后的声明文字，**不给标签、理由或证据**，要求逐条复制并分类。适合单独评估分类和证据选择，不能计作端到端拆分性能。

完成小规模连通测试后，例如运行：

```powershell
python scripts/evaluate_llm.py --split dev --mode end-to-end --json-mode --max-output-tokens 16384 --timeout 180 --output-dir results/dev-e2e
python scripts/evaluate_llm.py --split test --mode fixed-claims --json-mode --max-output-tokens 16384 --timeout 180 --output-dir results/test-fixed
python scripts/evaluate_llm.py --split edge --mode end-to-end --json-mode --max-output-tokens 16384 --timeout 180 --output-dir results/edge-e2e
```

每次输出目录必须不存在或为空，避免覆盖旧报告。`--split all` 会包含三种划分，仅用于整体诊断。模型要求输出限制字段为 `max_completion_tokens` 时加 `--token-limit-field max_completion_tokens`；支持 JSON 模式时可加 `--json-mode`；温度默认不发送，需要时指定 `--temperature 0`。请求逐条执行，不自动重试，以保留原始失败率和延迟。

如果已有验证服务，直接运行：

```powershell
python scripts/evaluate_llm.py --endpoint http://127.0.0.1:8000/verify --split test
```

此方式仅发送接口的两个字段；`fixed-claims` 不适用于该接口。可用 `--api-key-env YOUR_KEY_VARIABLE` 改用其他密钥变量名。

## 结果如何解读

每次运行保存 `config.json`（模型、提示词、参数、数据哈希）、`responses.jsonl`（原始响应、错误及逐条诊断）、`report.json`（总体及分类汇总）。未运行真实模型前，不存在可报告的模型分数。

- **结构与引用有效率**：JSON、枚举、下标和原文子串等确定性约束是否通过。原文中存在引用，不等于引用蕴含声明。
- **固定声明模式**：首先看是否按顺序保留给定声明，再看文本与标签联合指标、缺失/多余声明数及分类结果。只看“已匹配声明上的准确率”会忽略漏答。
- **端到端模式**：NFC/空白规范化后的文字匹配仅是诊断，等价改写或另一种合理拆分也可能不匹配；不得把它当语义级声明 F1。单声明标签准确率不验证预测声明与原声明的语义身份，需连同输出复核。
- **证据指标**：段落覆盖与精确标准引文匹配只作诊断。不同但充分的原文引用可能无法精确匹配标准片段，需要语义复核。
- **延迟/成本**：记录真实 HTTP 用时及上游返回的 token 数。只有提供 `--input-price-per-million` 和 `--output-price-per-million` 且 token 计数完整时，才估算费用；币种沿用输入价格，特殊缓存和推理计费未单独建模。

## 来源与标注过程

本数据由 AI 辅助选录、构造、对照页面和复核。2026-10-22，作者本人完成终审：裁决四个标出项，并报告抽查其余条目无问题；方法和结论见 [作者审阅记录](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922f30f5d1e105e8ebc5578d16fad9585342/reviews/cphos28/REVIEW.md)，不等同于独立领域专家逐条认证。历史 JSON 保留创建时的元数据和原标签，后续作者结论独立记录，原报告不回写。回答是静态构造的正确/错误变体，不是被测模型采样结果。没有执行 PDF 中的考试操作指令。

原试题 8 页，参考答案 24 页。选录片段的数学斜体、分式和上下标统一转成可读的线性公式，例如 `sqrt(T/mu)` 和 `u_i^2/(5*g)`；因此引用以**提供给模型的规范化上下文字符串**为逐字匹配基准。原题图像、整套长推导和有疑点公式未全部纳入，具体范围见来源审查记录。

若修改选录文字或案例，编辑 `scripts/build_dataset.py` 后运行：

```powershell
python scripts/build_dataset.py --pdf-root "D:/下载/CPHOS28/CPHOS28"
python scripts/validate_dataset.py --export --check-local-sources --output-report dataset/cphos28/validation_report.json
```

生成器保存了规范化选录内容；重新构建用于重建固定数据和来源哈希，并非重新自动 OCR。原文版权标记为 © 2025 CPHOS，本包保留出处，未附原始 PDF，也未为原内容附加开放许可。

完整 HTTP 服务、三种后端和统一 benchmark 现已补齐，使用方式与实测结果见根目录 README。本文件中的 `evaluate_llm.py` 命令保留用于单模型诊断。
