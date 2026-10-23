# P1 全48次输出的语义审阅

2026-10-24。审阅者没有起草P1案例；本稿是AI逐条审阅，未调用评审模型，未经作者终审。审阅可见臂身份和草案期望，不是盲评。只核对冻结P1的12个context/claim与48次输出，没有改标签、输出、Prompt或模型配置。

**候选未达到预登记的扩大验证门槛。** 原始标签命中与语义判断两臂相同；严格成功从21/24变22/24，仅新增一次U空引文契约合规，未修正新的语义判决。

| 指标（每臂24次） | base | candidate |
| --- | ---: | ---: |
| 原始标签命中 | 23 | 23 |
| 原始标签及核心推导语义正确 | 23 | 23 |
| 当前校验器有效 | 22 | 23 |
| 有效且标签、证据/推导正确 | 21 | 22 |
| 有效但语义错误 | 1 | 1 |
| 技术/契约失败 | 2 | 1 |
| 语义待定 | 0 | 0 |
| 无缓存参考费 USD | 0.0106254 | 0.0116238 |

共同有效的22对上，两臂均21次严格正确。净增为+1，保守/宽松界均为+1；没有任何案例在两次重复都由错误转正确。无缓存参考费用增加约9.40%，虽在25%内，净增至少2次及重复反例改善两项均未通过。正常同义、正向一步蕴含、唯一证据删除未新增错误，但不能据这些通过项忽略不满足的主门槛。

## 关键语义与契约区分

- `j-condition-u`：两臂第0次均给正确U及正确缺证解释，却带非空公共引文，因此原样记无效。两臂第1次均给结构合法C，把“若蓝色且温度不超过−5 °C则允许”改读成“只有/才允许”，凭空添加必要性。原文还明确其他条件未知；没有直接反证。这是合法引文与conflict不能证明语义正确的实际例子。
- `j-entailment-u` 第0次：base已正确指出逆向蕴含不可用，但给U附上考察材料引用而失败；candidate保持正确解释且返回空引文。新增严格成功属于协议遵守，不是把错误的NLI判决改正。第1次双方原已正确。
- S归属目标正确引用指定署名记录，另一人的相反记录不改变“这份记录说了什么”；C归属目标则引用同一指定记录的明确否定。
- 方向C引用否定句，该句属于唯一编号段落中本次传输的语境，主体/接收者与事件一致；没有从正向发送单独推出反向不发生。
- 一步正向蕴含的四次S都同时引齐全称规则与实例，普通同义四次S也保留暂时停运范围；未见过严。逆向蕴含的“converse”措辞虽略松，完整理由都明确成员身份不足以推出可兑换，不据术语表面作错误扣分。

## 逐项记录

下表覆盖所有48输出。PASS = 原校验有效且语义正确；FAIL-protocol = 语义核心正确但不满足公开契约；FAIL-semantic = 合法输出但判决/反证逻辑错误。JSON同时保存引文、derivation、reasoning、conflict、错误、逐记录哈希和上下界。

| case | arm | rep（0/1） | 判决 | 结果 | 逐条审阅理由 |
| --- | --- | ---: | --- | --- | --- |
| j-attribution-c | base | 0 | CONTRADICTED | PASS | 引文来自目标指定的 Dovren 完整署名记录，其中明确写 not sealed；conflict 对同一记录内容的肯定/否定作比较，未用 Ivara 的不同记录代替。直接反证与归属范围相同。 |
| j-attribution-c | base | 1 | CONTRADICTED | PASS | 引文来自目标指定的 Dovren 完整署名记录，其中明确写 not sealed；conflict 对同一记录内容的肯定/否定作比较，未用 Ivara 的不同记录代替。直接反证与归属范围相同。 |
| j-attribution-c | candidate | 0 | CONTRADICTED | PASS | 引文来自目标指定的 Dovren 完整署名记录，其中明确写 not sealed；conflict 对同一记录内容的肯定/否定作比较，未用 Ivara 的不同记录代替。直接反证与归属范围相同。 |
| j-attribution-c | candidate | 1 | CONTRADICTED | PASS | 引文来自目标指定的 Dovren 完整署名记录，其中明确写 not sealed；conflict 对同一记录内容的肯定/否定作比较，未用 Ivara 的不同记录代替。直接反证与归属范围相同。 |
| j-attribution-s | base | 0 | SUPPORTED | PASS | 引文来自明确指定的 Ivara 完整署名记录，内容为 sealed；derivation 核对的是该记录所说内容，未把另一署名者 Dovren 的相反记录误当此归属命题的反证。完整归属、主体与状态均保留。 |
| j-attribution-s | base | 1 | SUPPORTED | PASS | 引文来自明确指定的 Ivara 完整署名记录，内容为 sealed；derivation 核对的是该记录所说内容，未把另一署名者 Dovren 的相反记录误当此归属命题的反证。完整归属、主体与状态均保留。 |
| j-attribution-s | candidate | 0 | SUPPORTED | PASS | 引文来自明确指定的 Ivara 完整署名记录，内容为 sealed；derivation 核对的是该记录所说内容，未把另一署名者 Dovren 的相反记录误当此归属命题的反证。完整归属、主体与状态均保留。 |
| j-attribution-s | candidate | 1 | SUPPORTED | PASS | 引文来自明确指定的 Ivara 完整署名记录，内容为 sealed；derivation 核对的是该记录所说内容，未把另一署名者 Dovren 的相反记录误当此归属命题的反证。完整归属、主体与状态均保留。 |
| j-condition-s | base | 0 | SUPPORTED | PASS | 引用保留薄霭盒、面板蓝色、温度不超过负五摄氏度的合取及允许启动关系；derivation 将完整条件和结论对应，没有删去温度、负号或扩大适用范围。 |
| j-condition-s | base | 1 | SUPPORTED | PASS | 引用保留薄霭盒、面板蓝色、温度不超过负五摄氏度的合取及允许启动关系；derivation 将完整条件和结论对应，没有删去温度、负号或扩大适用范围。 |
| j-condition-s | candidate | 0 | SUPPORTED | PASS | 引用保留薄霭盒、面板蓝色、温度不超过负五摄氏度的合取及允许启动关系；derivation 将完整条件和结论对应，没有删去温度、负号或扩大适用范围。 |
| j-condition-s | candidate | 1 | SUPPORTED | PASS | 引用保留薄霭盒、面板蓝色、温度不超过负五摄氏度的合取及允许启动关系；derivation 将完整条件和结论对应，没有删去温度、负号或扩大适用范围。 |
| j-condition-u | base | 0 | UNSUPPORTED | FAIL-protocol | 标签U与理由的主要推断正确：只获知蓝色且不超过−5 °C时的许可，不能支持蓝色时任意温度均许可。引用确为原文，但公共citations非空违反U契约，因此不是有效输出，也不能计严格成功；本审阅不删除引用救回分数。 |
| j-condition-u | base | 1 | CONTRADICTED | FAIL-semantic | 模型将原文“若蓝色且温度不超过−5 °C，则允许”改读为“才允许”，以此声称任意温度允许与原文矛盾。原文还明确未说明其他条件；没有高于该阈值禁止启动的反证。真实引用与结构化conflict均合法，但反证语义不成立，应为U，当前C及理由均错误。 |
| j-condition-u | candidate | 0 | UNSUPPORTED | FAIL-protocol | 标签U与理由的主要推断正确：只获知蓝色且不超过−5 °C时的许可，不能支持蓝色时任意温度均许可。引用确为原文，但公共citations非空违反U契约，因此不是有效输出，也不能计严格成功；本审阅不删除引用救回分数。 |
| j-condition-u | candidate | 1 | CONTRADICTED | FAIL-semantic | derivation、reasoning与conflict将原文充分适用条件说成“需同时满足”“必要条件”“才允许”，继而判C。原文未否定其他温度下启动，且明示其他条件未知；没有直接不相容事实。引用锚点合法不能补足必要性，当前C及反证理由均错误，应为U。 |
| j-deletion-s | base | 0 | SUPPORTED | PASS | 引文直接给出同一青铃柜的额定容积 3.5 L，完整匹配数量、单位和对象；理由没有从位置描述推算容积。 |
| j-deletion-s | base | 1 | SUPPORTED | PASS | 引文直接给出同一青铃柜的额定容积 3.5 L，完整匹配数量、单位和对象；理由没有从位置描述推算容积。 |
| j-deletion-s | candidate | 0 | SUPPORTED | PASS | 引文直接给出同一青铃柜的额定容积 3.5 L，完整匹配数量、单位和对象；理由没有从位置描述推算容积。 |
| j-deletion-s | candidate | 1 | SUPPORTED | PASS | 引文直接给出同一青铃柜的额定容积 3.5 L，完整匹配数量、单位和对象；理由没有从位置描述推算容积。 |
| j-deletion-u | base | 0 | UNSUPPORTED | PASS | 剩余材料仅描述同一青铃柜位于西侧走廊，derivation 正确指出缺少额定容积而非其他无关前提；既无 3.5 L 的支持也无反证，空公共引文与 U 一致。 |
| j-deletion-u | base | 1 | UNSUPPORTED | PASS | 剩余材料仅描述同一青铃柜位于西侧走廊，derivation 正确指出缺少额定容积而非其他无关前提；既无 3.5 L 的支持也无反证，空公共引文与 U 一致。 |
| j-deletion-u | candidate | 0 | UNSUPPORTED | PASS | 剩余材料仅描述同一青铃柜位于西侧走廊，derivation 正确指出缺少额定容积而非其他无关前提；既无 3.5 L 的支持也无反证，空公共引文与 U 一致。 |
| j-deletion-u | candidate | 1 | UNSUPPORTED | PASS | 剩余材料仅描述同一青铃柜位于西侧走廊，derivation 正确指出缺少额定容积而非其他无关前提；既无 3.5 L 的支持也无反证，空公共引文与 U 一致。 |
| j-direction-c | base | 0 | CONTRADICTED | PASS | 引文明确否定弥朔向绛禾发送校验片，所在同一段落为本次传输语境；理由与 conflict 都针对该反向发送，而非从正向发送凭空推断反向不发生。 |
| j-direction-c | base | 1 | CONTRADICTED | PASS | 引文明确否定弥朔向绛禾发送校验片，所在同一段落为本次传输语境；理由与 conflict 都针对该反向发送，而非从正向发送凭空推断反向不发生。 |
| j-direction-c | candidate | 0 | CONTRADICTED | PASS | 引文明确否定弥朔向绛禾发送校验片，所在同一段落为本次传输语境；理由与 conflict 都针对该反向发送，而非从正向发送凭空推断反向不发生。 |
| j-direction-c | candidate | 1 | CONTRADICTED | PASS | 引文明确否定弥朔向绛禾发送校验片，所在同一段落为本次传输语境；理由与 conflict 都针对该反向发送，而非从正向发送凭空推断反向不发生。 |
| j-direction-s | base | 0 | SUPPORTED | PASS | 引文完整给出雾岫站、本次传输、绛禾为发送者、弥朔为接收者及校验片；理由为直接陈述，没有把方向或主体交换。 |
| j-direction-s | base | 1 | SUPPORTED | PASS | 引文完整给出雾岫站、本次传输、绛禾为发送者、弥朔为接收者及校验片；理由为直接陈述，没有把方向或主体交换。 |
| j-direction-s | candidate | 0 | SUPPORTED | PASS | 引文完整给出雾岫站、本次传输、绛禾为发送者、弥朔为接收者及校验片；理由为直接陈述，没有把方向或主体交换。 |
| j-direction-s | candidate | 1 | SUPPORTED | PASS | 引文完整给出雾岫站、本次传输、绛禾为发送者、弥朔为接收者及校验片；理由为直接陈述，没有把方向或主体交换。 |
| j-entailment-s | base | 0 | SUPPORTED | PASS | 两条引用同时保留全称规则 Lethric→Kavo可兑换和 Pex-47 属于 Lethric 的实例；derivation 正向实例化规则，没有逆用蕴含或省略任一必要前提。 |
| j-entailment-s | base | 1 | SUPPORTED | PASS | 两条引用同时保留全称规则 Lethric→Kavo可兑换和 Pex-47 属于 Lethric 的实例；derivation 正向实例化规则，没有逆用蕴含或省略任一必要前提。 |
| j-entailment-s | candidate | 0 | SUPPORTED | PASS | 两条引用同时保留全称规则 Lethric→Kavo可兑换和 Pex-47 属于 Lethric 的实例；derivation 正向实例化规则，没有逆用蕴含或省略任一必要前提。 |
| j-entailment-s | candidate | 1 | SUPPORTED | PASS | 两条引用同时保留全称规则 Lethric→Kavo可兑换和 Pex-47 属于 Lethric 的实例；derivation 正向实例化规则，没有逆用蕴含或省略任一必要前提。 |
| j-entailment-u | base | 0 | UNSUPPORTED | FAIL-protocol | 原始标签U及推断正确：可兑换→Lethric不能由Lethric成员身份逆推可兑换，明确缺少所需方向的支持。但将两条考察材料放进U的公共citations，违反既定契约；不能因标签/解释正确静默删引文计成功。 |
| j-entailment-u | base | 1 | UNSUPPORTED | PASS | 原文仅有 Kavo可兑换→Lethric 与 Pex-47 属于 Lethric，不能反向推出可兑换。derivation/解释识别该逆向推理缺口，未将缺证当反证；空公共引文符合 U。 |
| j-entailment-u | candidate | 0 | UNSUPPORTED | PASS | 原文仅有 Kavo可兑换→Lethric 与 Pex-47 属于 Lethric，不能反向推出可兑换。derivation/解释识别该逆向推理缺口，未将缺证当反证；空公共引文符合 U。 “affirms the converse”术语略松，但同句及reasoning明确说明成员身份不足以证明可兑换，核心推导无歧义；不因术语不够规范而强行扣成错误。 |
| j-entailment-u | candidate | 1 | UNSUPPORTED | PASS | 原文仅有 Kavo可兑换→Lethric 与 Pex-47 属于 Lethric，不能反向推出可兑换。derivation/解释识别该逆向推理缺口，未将缺证当反证；空公共引文符合 U。 |
| j-paraphrase-s | base | 0 | SUPPORTED | PASS | 同一 Vespor 渡轮服务、temporarily 范围均保留，halted/suspended 在该停运语境是正常同义；理由没有要求逐字相同或引入未陈述的原因。 |
| j-paraphrase-s | base | 1 | SUPPORTED | PASS | 同一 Vespor 渡轮服务、temporarily 范围均保留，halted/suspended 在该停运语境是正常同义；理由没有要求逐字相同或引入未陈述的原因。 |
| j-paraphrase-s | candidate | 0 | SUPPORTED | PASS | 同一 Vespor 渡轮服务、temporarily 范围均保留，halted/suspended 在该停运语境是正常同义；理由没有要求逐字相同或引入未陈述的原因。 |
| j-paraphrase-s | candidate | 1 | SUPPORTED | PASS | 同一 Vespor 渡轮服务、temporarily 范围均保留，halted/suspended 在该停运语境是正常同义；理由没有要求逐字相同或引入未陈述的原因。 |
| j-paraphrase-u | base | 0 | UNSUPPORTED | PASS | 材料只说明暂时停运，没有 crew strike 或停运原因；derivation 明确指出所缺为罢工因果关系，而不是把已经支持的停运状态也说成不存在。U 无公共引文正确。 |
| j-paraphrase-u | base | 1 | UNSUPPORTED | PASS | 材料只说明暂时停运，没有 crew strike 或停运原因；derivation 明确指出所缺为罢工因果关系，而不是把已经支持的停运状态也说成不存在。U 无公共引文正确。 |
| j-paraphrase-u | candidate | 0 | UNSUPPORTED | PASS | 材料只说明暂时停运，没有 crew strike 或停运原因；derivation 明确指出所缺为罢工因果关系，而不是把已经支持的停运状态也说成不存在。U 无公共引文正确。 |
| j-paraphrase-u | candidate | 1 | UNSUPPORTED | PASS | 材料只说明暂时停运，没有 crew strike 或停运原因；derivation 明确指出所缺为罢工因果关系，而不是把已经支持的停运状态也说成不存在。U 无公共引文正确。 |

## 文件绑定与限制

- 原始日志 SHA-256：`870a78e883a3caf66c6d2806d314534e39ad2a8e24b60b2f94ebdf650bb68d39`。
- 冻结P1案例 SHA-256：`53198ba7ffb12e0313ad4a1eb1a4dd0f82dc80e22ca0f437592d600560cd78dc`。
- 本审阅 JSON SHA-256：`f4fdbf5d32ff0f032bce53235ca52f693c02c47994764b81eb694caaaa529eae`。
- 没有待定项，故本轮上下界相同；这不是说AI语义审阅没有误差。
- 这是12个短合成案例的两次初判，不是24个独立来源；不含生产复核、格式重试、M1或端到端评测。该候选不晋升；阴性结果不否定所有结构化核查方法。
