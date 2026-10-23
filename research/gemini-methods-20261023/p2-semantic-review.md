# P2：全部输出独立语义审阅

2026-10-24。审阅者不是P2案例起草者。本报告是AI语义审阅，**不是作者终审**。读取已完成且冻结核验通过的84条总日志中的全部36条P2记录；不修改标签、原始输出或提示，不追加模型调用。

**按预登记条件不晋升追加NF审计。** 6次实际审计全部返回空recoveries，相对base恢复0个目标；也没有新增错误候选。四种离线策略均仅覆盖5/6个固定事实目标。关键限定是：实际触发审计的6例里，预设事实漏提数为0，因此恢复召回分母为0、尚未测得，不能说NF审计的一般召回率为0。

唯一未能计分的事实目标在pilot-a1：base和fresh都因文字记账失败而无有效输出。审计按base_invalid跳过，没有伪造成功。其余5个事实目标的主体、条件、量词及法语记录归属都完整保留。

## 固定分母比较

| 离线策略 | 有效事实目标/6 | 明确错误目标（语义去重） | 边界未决目标 | 含技术未知的样本/12 | 全链正确纯NF/6 |
|---|---:|---:|---:|---:|---:|
| base | 5/6 | 6 | 0 | 2/12 | 1/6 |
| fresh替换 | 5/6 | 4 | 1 | 1/12 | 3/6 |
| base+audit | 5/6 | 6 | 0 | 2/12 | 1/6 |
| base+fresh离线并集 | 5/6 | 7 | 1 | 2/12 | 1/6 |

base有效10/12，fresh有效11/12。base+fresh有至少一个有效提取的样本为11/12，但两个样本仍含失败组件；不能把部分可读输出冒充整链完成。固定事实分母始终6，纯NF分母始终6，总例数始终12。

错误目标指按本任务不应作为核查对象的提取，**不等于断言在外部世界必定为假**。base中6项明确错误含能力推断、建议当claim及假设范围丢失；fresh中4项明确错误加1项边界输出。pilot-d1/fresh保留“在想象练习中”，不像base那样凭空断言现实容器状态；但按预设纯NF口径不获正确分，独立语义评估保留uncertain。

base+fresh的10次明确错误输出包含3次语义重复，去重后7个不同错误目标；另有1个边界输出。建议、能力、模态、假设范围不同的命题保持分别计数，未按相同跨度合并。无任何运行时语义合并；这里只对预设目标ID和审阅后的错误命题作离线记分。

扣除明确不同错误目标后的诊断数分别为−1、+1、−1、−2；若边界输出也按预设纯NF口径算非目标，则fresh为0、base+fresh为−3。该算式只辅助检查PLAN的优于控制条件，不是新准确率指标。无论采取哪个保守口径，base+audit均没有新恢复，也不优于fresh。

## 审计触发与可观测局限

- 6次实际调用全部结构有效、全部空列表；没有正确冗余恢复，也没有错误或边界恢复。
- 6次跳过：2次base_invalid（a1、d2），4次没有NF跨度（a2、b2、c2、c3）。这些跳过都不是模型成功审计。
- c3整条建议被放进claims且NF为空，所以审计不触发；a3、b3、d1等已有错误claim即使触发审计，追加式机制也不会删除错误。
- 本轮缺少“base有效、NF内确实遗漏预设事实”的实际正例，故未测到恢复能力；只能观察这批请求中的新增候选行为及成本。不能通过事后挑选case或重跑制造恢复收益。

## 逐案例、逐输出审阅

每个原始引用指向不可变responses.jsonl的行号；下列raw_output逐字字段来自模型返回，错误输出仅用于诊断、不计有效目标。完整结构化映射见同目录p2-semantic-review.json。

### pilot-a1 · causal_capability_in_advice · en

原回答：Consider misting the ceramic tray before use, because misting lowers the tray’s surface temperature.

预设目标：pilot-a1-f1。

**base：error**，原始日志第52行。

```json
{"claims": [{"claim_text": "Misting the ceramic tray before use lowers the tray’s surface temperature.", "source_span": "misting lowers the tray’s surface temperature"}], "non_factual_spans": [{"text": "Consider misting the ceramic tray before use", "reason": "recommendation/advice rather than a factual assertion"}]}
```

技术错误：Extraction left answer text unaccounted for near: 'because misting lowers the tray’s surface temperature.'
raw尝试提取了因果关系，但加入before use限定，并且because未被完整记账导致结构失败。不得从raw候选获得目标命中或假称NF审计修复。

**repeat：error**，原始日志第55行。

```json
{"claims": [{"claim_text": "Misting the ceramic tray lowers the tray’s surface temperature.", "source_span": "misting lowers the tray’s surface temperature"}], "non_factual_spans": [{"text": "Consider misting the ceramic tray before use", "reason": "advice/recommendation, not itself a factual assertion"}]}
```

技术错误：Extraction left answer text unaccounted for near: 'because misting lowers the tray’s surface temperature.'
raw因果内容基本对应预设目标，但because记账失败使整次提取无有效输出；只作故障诊断，不计恢复。

**nf_audit：skipped**，原始日志第56行。

跳过原因：base_invalid。基础失败，恢复与语义正确性均不给分。

### pilot-a2 · causal_capability_in_advice · en

原回答：Misting the ceramic tray lowers the tray’s surface temperature.

预设目标：pilot-a2-f1。

**base：valid**，原始日志第15行。

```json
{"claims": [{"claim_text": "Misting the ceramic tray lowers the tray’s surface temperature.", "source_span": "Misting the ceramic tray lowers the tray’s surface temperature."}], "non_factual_spans": []}
```

- 输出1：**target_hit**。因果主体、对象和温度变化均保留，没有添加已执行动作。 命中固定目标 `pilot-a2-f1`。

**repeat：valid**，原始日志第18行。

```json
{"claims": [{"claim_text": "Misting the ceramic tray lowers the tray’s surface temperature.", "source_span": "Misting the ceramic tray lowers the tray’s surface temperature."}], "non_factual_spans": []}
```

- 输出1：**target_hit**。因果主体、对象和温度变化均保留，没有添加已执行动作。 命中固定目标 `pilot-a2-f1`。

**nf_audit：skipped**，原始日志第19行。

跳过原因：no_non_factual_spans。未调用审计，不等于审计通过。

### pilot-a3 · causal_capability_in_advice · en

原回答：Try misting the ceramic tray and check whether its surface cools.

预设目标：无；纯NF。

**base：valid**，原始日志第43行。

```json
{"claims": [{"claim_text": "Misting the ceramic tray may cool its surface.", "source_span": "Try misting the ceramic tray and check whether its surface cools."}], "non_factual_spans": [{"text": "Try misting the ceramic tray and check whether its surface cools.", "reason": "This is an instruction/suggestion to perform an action and verify an outcome, not an assertion that the action was performed or that the surface cools."}]}
```

- 输出1：**incorrect**。原文要求尝试并观察是否降温，并未断言降温能力；may保留不确定性仍把待测试关系升为事实目标。

纯NF严格正确：否。

**repeat：valid**，原始日志第46行。

```json
{"claims": [], "non_factual_spans": [{"text": "Try misting the ceramic tray and check whether its surface cools.", "reason": "An instruction/suggestion to perform an action, not a factual assertion"}]}
```

claims为空，整段按NF处理；此例预设纯NF，未捏造色彩、动作或结果事实。

纯NF严格正确：是。

**nf_audit：valid**，原始日志第50行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

### pilot-b1 · numeric_condition_and_quantifier · zh

原回答：环境温度低于18 °C时，蓝色保温盒至少保温40分钟。满足这一条件时，建议用它暂存样品。

预设目标：pilot-b1-f1。

**base：valid**，原始日志第74行。

```json
{"claims": [{"claim_text": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。", "source_span": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。"}, {"claim_text": "满足环境温度低于18 °C这一条件时，建议用蓝色保温盒暂存样品。", "source_span": "满足这一条件时，建议用它暂存样品。"}], "non_factual_spans": [{"text": "建议用它暂存样品", "reason": "advice/recommendation"}]}
```

- 输出1：**target_hit**。严格低于18度、至少40分钟、蓝色盒及条件能力均保留。 命中固定目标 `pilot-b1-f1`。

- 输出2：**incorrect**。完整温度条件虽保留，第二条仍只是建议暂存操作，不是另一个应核查事实。

**repeat：valid**，原始日志第79行。

```json
{"claims": [{"claim_text": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。", "source_span": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。"}, {"claim_text": "满足环境温度低于18 °C这一条件时，建议用蓝色保温盒暂存样品。", "source_span": "满足这一条件时，建议用它暂存样品。"}], "non_factual_spans": [{"text": "建议", "reason": "建议/推荐性措辞，本身不是事实断言"}]}
```

- 输出1：**target_hit**。严格低于18度、至少40分钟、蓝色盒及条件能力均保留。 命中固定目标 `pilot-b1-f1`。

- 输出2：**incorrect**。与base相同的建议被再次放入claims；与第一条保温能力事实不同。

**nf_audit：valid**，原始日志第82行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

### pilot-b2 · numeric_condition_and_quantifier · zh

原回答：环境温度低于18 °C时，蓝色保温盒至少保温40分钟。

预设目标：pilot-b2-f1。

**base：valid**，原始日志第1行。

```json
{"claims": [{"claim_text": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。", "source_span": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。"}], "non_factual_spans": []}
```

- 输出1：**target_hit**。严格温度不等式、时长下界及盒体均完整。 命中固定目标 `pilot-b2-f1`。

**repeat：valid**，原始日志第5行。

```json
{"claims": [{"claim_text": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。", "source_span": "环境温度低于18 °C时，蓝色保温盒至少保温40分钟。"}], "non_factual_spans": []}
```

- 输出1：**target_hit**。严格温度不等式、时长下界及盒体均完整。 命中固定目标 `pilot-b2-f1`。

**nf_audit：skipped**，原始日志第6行。

跳过原因：no_non_factual_spans。未调用审计，不等于审计通过。

### pilot-b3 · numeric_condition_and_quantifier · zh

原回答：可以试着用蓝色保温盒暂存样品，再观察它在低于18 °C的环境中能保温多久。

预设目标：无；纯NF。

**base：valid**，原始日志第4行。

```json
{"claims": [{"claim_text": "蓝色保温盒可以用于暂存样品", "source_span": "可以试着用蓝色保温盒暂存样品"}, {"claim_text": "样品在低于18 °C的环境中能保温多久需要观察", "source_span": "再观察它在低于18 °C的环境中能保温多久"}], "non_factual_spans": [{"text": "可以试着用", "reason": "建议性措辞，非事实陈述"}, {"text": "再观察", "reason": "建议性行动步骤，非事实陈述"}]}
```

- 输出1：**incorrect**。可以试着是试验建议；改成可以用于暂存，把试验操作提为能力断言。

- 输出2：**incorrect**。原文再观察是操作要求，输出将其改成需要观察的claim。它的指代也被固定为样品，但原指代有一定歧义，不单独据此判主体错误。

纯NF严格正确：否。

**repeat：valid**，原始日志第9行。

```json
{"claims": [{"claim_text": "蓝色保温盒可以用于暂存样品", "source_span": "用蓝色保温盒暂存样品"}, {"claim_text": "在低于18 °C的环境中，可以观察样品能保温多久", "source_span": "观察它在低于18 °C的环境中能保温多久"}], "non_factual_spans": [{"text": "可以试着", "reason": "suggestion wording, not a factual assertion"}, {"text": "再", "reason": "sequencing connective in advice"}]}
```

- 输出1：**incorrect**。与base第一条同一错误能力命题，不能当作新事实恢复。

- 输出2：**incorrect**。把观察步骤改为可以观察的命题；不能据此构造时长事实。与base的需要观察并非同一模态，因此离线错误集合不按跨度合并。

纯NF严格正确：否。

**nf_audit：valid**，原始日志第11行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

### pilot-c1 · attributed_observation · fr

原回答：Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai ; vérifiez la signature avant de citer cette observation.

预设目标：pilot-c1-f1。

**base：valid**，原始日志第76行。

```json
{"claims": [{"claim_text": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai.", "source_span": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai"}], "non_factual_spans": [{"text": "vérifiez la signature avant de citer cette observation.", "reason": "Instruction/directive, not a factual assertion"}]}
```

- 输出1：**target_hit**。Selon le carnet de Maëlle归属、绿色指示器、始终熄灭、试验期间四要素保留。 命中固定目标 `pilot-c1-f1`。

**repeat：valid**，原始日志第77行。

```json
{"claims": [{"claim_text": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai.", "source_span": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai"}], "non_factual_spans": [{"text": "vérifiez la signature avant de citer cette observation.", "reason": "instruction"}]}
```

- 输出1：**target_hit**。Selon le carnet de Maëlle归属、绿色指示器、始终熄灭、试验期间四要素保留。 命中固定目标 `pilot-c1-f1`。

**nf_audit：valid**，原始日志第81行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

### pilot-c2 · attributed_observation · fr

原回答：Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai.

预设目标：pilot-c2-f1。

**base：valid**，原始日志第68行。

```json
{"claims": [{"claim_text": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai.", "source_span": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai."}], "non_factual_spans": []}
```

- 输出1：**target_hit**。同一记录归属与试验时间范围完整，未改成亲历或永久状态。 命中固定目标 `pilot-c2-f1`。

**repeat：valid**，原始日志第71行。

```json
{"claims": [{"claim_text": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai.", "source_span": "Selon le carnet de Maëlle, le témoin vert est resté éteint pendant l’essai."}], "non_factual_spans": []}
```

- 输出1：**target_hit**。同一记录归属与试验时间范围完整，未改成亲历或永久状态。 命中固定目标 `pilot-c2-f1`。

**nf_audit：skipped**，原始日志第72行。

跳过原因：no_non_factual_spans。未调用审计，不等于审计通过。

### pilot-c3 · attributed_observation · fr

原回答：Si vous lisez un carnet d’essai, vérifiez qui signe chaque observation avant de la citer.

预设目标：无；纯NF。

**base：valid**，原始日志第53行。

```json
{"claims": [{"claim_text": "Si vous lisez un carnet d’essai, vérifiez qui signe chaque observation avant de la citer.", "source_span": "Si vous lisez un carnet d’essai, vérifiez qui signe chaque observation avant de la citer."}], "non_factual_spans": []}
```

- 输出1：**incorrect**。整句仍是有条件的命令：阅读记录时请查签名；未断言已经阅读、签名真实或已检查，不能作为事实目标。

纯NF严格正确：否。

**repeat：valid**，原始日志第58行。

```json
{"claims": [{"claim_text": "Si vous lisez un carnet d’essai, vérifiez qui signe chaque observation avant de la citer.", "source_span": "Si vous lisez un carnet d’essai, vérifiez qui signe chaque observation avant de la citer."}], "non_factual_spans": []}
```

- 输出1：**incorrect**。与base完全相同的命令句，重复不是新事实或恢复。

纯NF严格正确：否。

**nf_audit：skipped**，原始日志第59行。

跳过原因：no_non_factual_spans。未调用审计，不等于审计通过。

### pilot-d1 · hypothetical_tentative_refusal_controls · es

原回答：Para un ejercicio imaginario, supón que el recipiente contiene seis fichas verdes y dibuja ese escenario.

预设目标：无；纯NF。

**base：valid**，原始日志第70行。

```json
{"claims": [{"claim_text": "El recipiente contiene seis fichas verdes.", "source_span": "el recipiente contiene seis fichas verdes"}], "non_factual_spans": [{"text": "Para un ejercicio imaginario, supón que", "reason": "Marco de instrucción hipotética"}, {"text": "y dibuja ese escenario.", "reason": "Instrucción"}]}
```

- 输出1：**incorrect**。原文仅让读者在想象练习中假设；输出删掉假设范围，成为容器确有六枚绿筹码的无条件断言。

纯NF严格正确：否。

**repeat：valid**，原始日志第75行。

```json
{"claims": [{"claim_text": "El recipiente contiene seis fichas verdes en un ejercicio imaginario.", "source_span": "supón que el recipiente contiene seis fichas verdes"}], "non_factual_spans": [{"text": "Para un ejercicio imaginario", "reason": "encuadre hipotético sin afirmación verificable"}, {"text": "y dibuja ese escenario.", "reason": "instrucción"}]}
```

- 输出1：**uncertain**。保留en un ejercicio imaginario，不能像base一样断言虚构现实事实；但仍把被指示设想的情境内容列为claim，按预登记纯NF目标不计正确。其作为忠实元描述是否允许存在语义边界，独立审阅标uncertain，不强判现实事实虚构。

纯NF严格正确：否。

**nf_audit：valid**，原始日志第78行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

### pilot-d2 · hypothetical_tentative_refusal_controls · es

原回答：Prueba a girar la palanca azul y observa si se reduce la vibración.

预设目标：无；纯NF。

**base：error**，原始日志第2行。

```json
{"claims": [{"claim_text": "Girar la palanca azul puede reducir la vibración.", "source_span": "gira la palanca azul y observa si se reduce la vibración"}], "non_factual_spans": [{"text": "Prueba a", "reason": "suggestion/instruction wording, not a factual assertion"}, {"text": "y observa si", "reason": "instruction to observe, not a factual assertion"}]}
```

技术错误：Extraction source spans must be exact answer substrings in answer order.
raw把尝试转杠杆观察是否减振改成may reduce能力，并把原文girar改成gira导致非精确跨度。此条技术未知；raw语义错误另列，不纳入有效输出错误数。

**repeat：valid**，原始日志第7行。

```json
{"claims": [], "non_factual_spans": [{"text": "Prueba a girar la palanca azul y observa si se reduce la vibración.", "reason": "It is an instruction/suggestion to try an action and observe a result, not an assertion of fact."}]}
```

claims为空，整段按NF处理；此例预设纯NF，未捏造色彩、动作或结果事实。

纯NF严格正确：是。

**nf_audit：skipped**，原始日志第8行。

跳过原因：base_invalid。基础失败，恢复与语义正确性均不给分。

### pilot-d3 · hypothetical_tentative_refusal_controls · es

原回答：No puedo determinar el color de la caja con la información proporcionada.

预设目标：无；纯NF。

**base：valid**，原始日志第57行。

```json
{"claims": [], "non_factual_spans": [{"text": "No puedo determinar el color de la caja con la información proporcionada.", "reason": "Expresses an inability to determine a fact given the available information; it is not an assertion of a factual claim about the box's color."}]}
```

claims为空，整段按NF处理；此例预设纯NF，未捏造色彩、动作或结果事实。

纯NF严格正确：是。

**repeat：valid**，原始日志第62行。

```json
{"claims": [], "non_factual_spans": [{"text": "No puedo determinar el color de la caja con la información proporcionada.", "reason": "First-person statement of inability rather than an asserted factual proposition about the world"}]}
```

claims为空，整段按NF处理；此例预设纯NF，未捏造色彩、动作或结果事实。

纯NF严格正确：是。

**nf_audit：valid**，原始日志第64行。

```json
{"recoveries": []}
```

未提出任何恢复候选；不能撤销base中已有的错误提取，也不能把空恢复当作完整事实覆盖证明。

## 审阅边界与哈希

只做提取语义审阅，不是M3标签准确性实验；没有证明恢复候选最终核查会正确。四语言与四家族混杂，一次自然提取不能估计跨语言泛化或模型波动。所有期望来自冻结AI草稿，没有进入作者裁定文件。

responses SHA-256：`870a78e883a3caf66c6d2806d314534e39ad2a8e24b60b2f94ebdf650bb68d39`。

数据和PLAN的冻结文件哈希见JSON。所有21个有效claims输出、0个恢复候选、3个技术失败raw输出及6个skip均已覆盖。
