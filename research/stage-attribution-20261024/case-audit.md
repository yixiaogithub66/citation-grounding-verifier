# Case audit — pre-inference independent AI review

2026-10-24 Asia/Shanghai. Reviewed every answer, all 45 target texts/labels, all evidence quotations and source/NF spans in the current draft. No old benchmark inputs or inference outputs were read, and no model/network calls were made by this reviewer. This is independent AI review of AI-authored references, not author gold.

Current draft SHA256: `18aebc2fcb4d0beac3d964d14f0aca3fb34f75a857d72b67f41e0db0616d6455`.

## Outcome

After the recorded pre-freeze corrections, all 45 proposed S/C/U reference labels are defensible under the task contract. The five NF-only answers contain requests, preferences, proposals and open questions rather than objective factual premises. The cases are suitable for this bounded diagnostic pilot, not a natural-distribution accuracy estimate.

## Corrections requested and verified

- Removed the unasserted `must` strengthening in sa02/t2.
- Restored J4 scope in sa07/t2.
- Made the missing signature explicit in sa09 source instead of deriving negation only from an empty field; final M1 essentials require the original “before signature” condition, not an extra standalone current-status assertion.
- Removed context-only proof premises from M1 essentials in sa15/t2, sa17/t2 and sa19/t1.
- Removed the answer-absent Farrow proper name from sa18 targets/essentials.
- Verified explicit answer-side antecedents/conditions in revised sa03/t2 and sa19/t2.

These revisions correct source/annotation consistency before any model output. They do not adjust cases according to expected arm performance. Counts and reference verdicts stayed fixed.

## Target-by-target semantic check

| Case / target | Review |
| --- | --- |
| sa01/t1 | S：K6 的乙级归属与回收流程相容；保留每次、先后次序。 |
| sa01/t2 | C：相同干燥流程的装帽时点被明确反转。 |
| sa01/t3 | S：红灯校准模式及非故障的通常同义转述；可拆成两条保真事实。 |
| sa02/t1 | U：增益四与续航的关系没有来源前提；祈使动作自身不算事实。 |
| sa02/t2 | S：保留八个月与从安装起算，不把 interval 强化为 must。 |
| sa02/t3 | C：程序要求带电清洁与明确禁止相反。 |
| sa03/t1 | C：同一 T9、夜班、岸上供电与外壳关闭条件下 38/42 冲突。 |
| sa03/t2 | U：记录时长分类没有给出测距误差比较。 |
| sa03/t3 | U：纪要未记该人物的长记录主张，不等于该人物明确反对。 |
| sa04 / NF-only | All answer wording is advice, preference, question or participation choice; no source fact needs to be copied into M1. |
| sa05/t1 | C：2011 属于照片，O17 录音明确为 2013。 |
| sa05/t2 | U：实体磁带位置不证明云端完整数字副本。 |
| sa05/t3 | S：保留 Leah 的回忆归属，不把回忆升格为客观村史。 |
| sa06/t1 | S：公共阅听室内所有播放录音访客适用，研究许可者没有豁免。 |
| sa06/t2 | S：展示副本有许可，许可版本可预约；不推出母带也可。 |
| sa06/t3 | U：去标识化不具备材料提供的任何听众零识别保证。 |
| sa07/t1 | U：阅听室许可不蕴含在家远程访问，也不直接禁止远程访问。 |
| sa07/t2 | C：同一 J4 索引提议归 Opal，Marin 明确反对。 |
| sa07/t3 | C：签署后才可发布，直接否定签署前发布。 |
| sa08 / NF-only | All answer wording is advice, preference, question or participation choice; no source fact needs to be copied into M1. |
| sa09/t1 | U：会员时段表没有三人团体折扣规则。 |
| sa09/t2 | S：已完成检查与签字前不能开放同时保留；修订后的来源明确尚未签字。 |
| sa09/t3 | U：材料没有未满十六岁会员自动获得较易路线规则。 |
| sa10/t1 | C：同一预约、十四岁以下条件，1:4 比例被明确排除。 |
| sa10/t2 | S：蓝卡、预约时段、头盔、免费范围一致。 |
| sa10/t3 | C：周末午间检查期间仍开放，与每日该时段封闭相反。 |
| sa11/t1 | S：黄卡资格、周三晚间与十八点以后合用，仅为预约资格。 |
| sa11/t2 | C：余安明确反对封闭时任何会员越绳，黄卡仍属会员。 |
| sa11/t3 | U：面积翻倍与焦虑减半的因果数量关系没有材料支撑。 |
| sa12 / NF-only | All answer wording is advice, preference, question or participation choice; no source fact needs to be copied into M1. |
| sa13/t1 | S：18 属于材料定义的不高于 20，定义分类无外部知识。 |
| sa13/t2 | U：未提供十二次洗涤保色证据，不能用常识判反证。 |
| sa13/t3 | C：同一 B7 晾板放置阶段，上向与明确要求下向冲突。 |
| sa14/t1 | C：相同 D4 第二阶段检查，湿润与必须全干相反。 |
| sa14/t2 | C：L 缓冲液禁止加入与必须加入相反。 |
| sa14/t3 | S：浸泡期间盖盖；不扩展到晾布阶段。 |
| sa15/t1 | U：密封纸套一个月零色变保证没有材料证明。 |
| sa15/t2 | S：M3 的亚麻属性和完成末次冲洗满足来源资格；M1 不需从 context 补这些证明前提。 |
| sa15/t3 | U：Dara 的架标提议不证明其收纳袋偏好。 |
| sa16 / NF-only | All answer wording is advice, preference, question or participation choice; no source fact needs to be copied into M1. |
| sa17/t1 | C：同一 Q5 模板十通道与十二且禁止十直接冲突。 |
| sa17/t2 | S：R8 的源状态满足给定台内背景记录定义；M1 不需补源状态。 |
| sa17/t3 | U：两机相关分析消除全部本地干扰的保证没有来源前提。 |
| sa18/t1 | U：双次扫描使可靠性翻倍的关系未给出；M1 不要求来源独有站名。 |
| sa18/t2 | C：午夜后 N 参考通道许可，与明确禁止冲突。 |
| sa18/t3 | S：风值恰为二十被给定定义包括；不要求补来源独有站名。 |
| sa19/t1 | S：P2 满足给定联合展示资格；不推导已被接纳或科学真实性。 |
| sa19/t2 | U：校时与原轨迹保存的展示条件不推出任何夜间记录零误报。 |
| sa19/t3 | C：桑宁明确反对全部峰值直接天体标签，支持者是陶然。 |
| sa20 / NF-only | All answer wording is advice, preference, question or participation choice; no source fact needs to be copied into M1. |

## Scoring boundaries that must survive freezing

- The 45 targets are content-coverage targets, not a mandatory count of extracted atomic rows. For sa01/t1/t3 and sa09/t2 in particular, multiple faithful atomic rows may jointly cover one target; a preserved compound row can pass content retention without automatically passing strict atomicity.
- In sa09/t2, retaining “inspection complete; reopening is forbidden until the supervisor signs” is sufficient. Do not force an extra standalone assertion of current signature status when the original temporal wording is already preserved.
- M1 sees only the answer. Do not require it to append context-only antecedents, prove an eligibility conclusion, change an incorrect assertion, or expand a local definition from the source.
- Evidence quotations were checked as exact substrings with their indexed passage context. Some short reference snippets depend on the surrounding passage to identify the entity or antecedent. They are illustrative admissible anchors, not an exclusive expected citation string or a proof that any similarly short model quote is sufficient. Audit each returned S/C quote for its actual claim and required premises.
- Broad claims marked U remain U when material is silent, even where outside expertise might make them implausible. Attributed opinions remain factual claims about what a speaker said.
- Five domains, bilingual wording and balanced labels are deliberate experimental construction. Most source conflicts and omissions are explicit; a ceiling outcome would limit diagnostic power and must not lead to post-output hardening or replacement of cases.

## Mechanical checks

20 unique cases; 15 three-target answers plus five NF-only answers; 45 targets with S/C/U = {'SUPPORTED': 15, 'CONTRADICTED': 15, 'UNSUPPORTED': 15}; all source spans and NF spans are exact answer substrings, all evidence quotes exact substrings of their indexed passages, U evidence empty and S/C evidence nonempty. The synthetic label status remains `AI-draft-not-author-approved`.
