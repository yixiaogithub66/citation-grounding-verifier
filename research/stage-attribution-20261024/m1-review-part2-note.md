# M1 blinded semantic audit — part 2

AI semantic review, 2026-10-24. Only the assigned m1-part2 packet, PLAN and case-audit were read in this task. No private key, arm mapping, prompt attribution, costs, other model outputs or aggregate scores were accessed. Forty raw outputs were individually inspected, including their NF arrays. All forty were readable. This is not author adjudication.

The JSON preserves per-target mapping and explicit reasons. Whole-answer coreference is used to determine whether content survives; standalone separately asks whether an individual claim supplies the available antecedent. Thus intact “该组/这套设备/场馆/then/That value” can preserve content while failing standalone. The source-span criterion allows a short exact span plus a shared antecedent explicitly present in the answer; no evidence-context facts were imported. The answer's own unnamed observatory is accepted as its information ceiling.

The common issues are not merged into one omission category: advice/preferences entering claims; conditional antecedents promoted into actual observations or obligations; intact facts also excluded by whole-sentence NF spans; and unresolved scope/antecedents. In this packet all reference content can still be found in the raw claims under the whole-answer reading; that does not imply strict success, sound extra claims, or protocol validity.

Notable review IDs:

- m-c8d0aab352ccb4125d2a: all three D4 fact-bearing sentences also occur in NF; cover-through-claims does not excuse factual exclusion. The third claim also omits D4's locally explicit scope.
- m-5872b2a62fe2d55e1b5e: “Please bring” becomes an unsupported `required` assertion. The original permission remains as `Flint Loft permits that ratio`, which is not standalone.
- m-4184036b2a564aacd403: `When ... twenty` becomes a factual observation of twenty, while the actual definition target remains present with `That value`; `then` also remains unresolved.
- m-a65a72fc58d40f07d052: a complete qualified T9 claim coexists with an extra unqualified fan-threshold claim. The latter is not harmless repetition because its scope is broader. There is also an extra preference claim.
- m-26cc05b3c63a95169ff7 and m-e87826a95f8f82d41827: the cap claim preserves its statement but retains “这个干燥流程”; scored as failing standalone. The ordered maintenance flow remains atomic by the registered convention, and the red-light contrast is treated as one indicator-meaning assertion.

Pure NF outputs that contain speaker/response self-reports of preferences are marked false inclusion: relabeling the current speaker's preference as “the speaker prefers” is not the same task as extracting a reported third party's historical opinion. Genuine third-party claims about Leah, Dara, Marin, 林越, 余安 and 桑宁 are retained when present.

No target label or frozen material was changed. There are no null judgments in this part: the packets are readable and the identified errors follow the fixed task distinctions. The sa02 connected-port ambiguity discussed by the coordinator does not occur in this packet. Claims-only semantic review does not reconstruct missing structural coverage; protocol validity must remain separately joined by the coordinator.
