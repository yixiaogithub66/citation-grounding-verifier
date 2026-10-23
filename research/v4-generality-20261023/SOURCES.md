# 来源目录与阅读范围

共30个一手来源：23篇学术论文，7条官方工业资料。不同版本已去重；Claimify博客仅为同源旁证，没有另计独立研究。各论文/博客的结论不直接作为本项目收益。

## 优先阅读

- 提取：Claimify（C01）、Decomposition Dilemmas（C07）、DnDScore（C08）。
- 证据与复核：MiniCheck（V02）、RT4CHART（V09，预印本）、GAVEL（E05）、MARCH（E04）。
- 工业接口：Citations（I02）、Structured outputs（I03）、Building effective agents（I01）。
- 泛化评测：CheckList（E01）、FaithBench（E02）；特别注意后者的标签语义和困难样本选择。

## 完整目录

### C01 · Towards Effective Extraction and Evaluation of Factual Claims

Dasha Metropolitansky; Jonathan Larson (2025). [Towards Effective Extraction and Evaluation of Factual Claims](https://aclanthology.org/2025.acl-long.348/).

DOI：10.18653/v1/2025.acl-long.348

读取范围：Targeted full-text reading: §§2.1–2.3, 3.1–3.4, 4.1–4.2, 5.2–5.3, 6; §9 scope/annotator/hyperparameter limitations. Not all 50 pages or appendices.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C02 · FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation

Sewon Min; Kalpesh Krishna; Xinxi Lyu; Mike Lewis; Wen-tau Yih; Pang Wei Koh; Mohit Iyyer; Luke Zettlemoyer; Hannaneh Hajishirzi (2023). [FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation](https://aclanthology.org/2023.emnlp-main.741/).

DOI：10.18653/v1/2023.emnlp-main.741

读取范围：Targeted PDF reading: §3.1 definition/assumptions, §4.2 estimator evaluation, limitations pp.12084–12085, Appendix B.2 segment-vs-system metrics. Other sections not fully read.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C03 · VeriScore: Evaluating the factuality of verifiable claims in long-form text generation

Yixiao Song; Yekyung Kim; Mohit Iyyer (2024). [VeriScore: Evaluating the factuality of verifiable claims in long-form text generation](https://aclanthology.org/2024.findings-emnlp.552/).

DOI：10.18653/v1/2024.findings-emnlp.552

读取范围：Targeted PDF reading: §§2.1.1–2.1.2, §3.1 human extraction evaluation; full limitations. Did not fully read fine-tuning or all verification experiments.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C04 · Long-form factuality in large language models

Jerry Wei; Chengrun Yang; Xinying Song; Yifeng Lu; Nathan Hu; Jie Huang; Dustin Tran; Daiyi Peng; Ruibo Liu; Da Huang; Cosmo Du; Quoc V. Le (2024). [Long-form factuality in large language models](https://arxiv.org/abs/2403.18802).

DOI：10.48550/arXiv.2403.18802

读取范围：NeurIPS PDF §§2–4, §8; Appendix A.3, C.4–C.8 and beginning C.10. Not all 72 pages. Metadata cross-checked with arXiv v4 and DeepMind publication page.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C05 · Decontextualization: Making Sentences Stand-Alone

Eunsol Choi; Jennimaria Palomaki; Matthew Lamm; Tom Kwiatkowski; Dipanjan Das; Michael Collins (2021). [Decontextualization: Making Sentences Stand-Alone](https://aclanthology.org/2021.tacl-1.27/).

DOI：10.1162/tacl_a_00377

读取范围：Targeted PDF reading: §2 truth-conditional definition; §3.4 scope/sampling; §5.2 and Tables 4–5 automatic evaluation. Did not fully read human evaluation/downstream studies.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C06 · A Closer Look at Claim Decomposition

Miriam Wanner; Seth Ebner; Zhengping Jiang; Mark Dredze; Benjamin Van Durme (2024). [A Closer Look at Claim Decomposition](https://aclanthology.org/2024.starsem-1.13/).

DOI：10.18653/v1/2024.starsem-1.13

读取范围：Targeted PDF reading: §§3.1–3.2; conclusion/limitations; Appendix Tables 3–6. Did not fully read every decomposition prompt.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C07 · Decomposition Dilemmas: Does Claim Decomposition Boost or Burden Fact-Checking Performance?

Qisheng Hu; Quanyu Long; Wenya Wang (2025). [Decomposition Dilemmas: Does Claim Decomposition Boost or Burden Fact-Checking Performance?](https://aclanthology.org/2025.naacl-long.320/).

DOI：10.18653/v1/2025.naacl-long.320

读取范围：Targeted full-text reading: §3.2 pipeline/settings; §4 and Tables 1–3; §5 error taxonomy; §6 trade-off/complexity experiments; §8 limitations. Not all appendix material.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C08 · DnDScore: Decontextualization and Decomposition for Factuality Verification in Long-Form Text Generation

Miriam Wanner; Benjamin Van Durme; Mark Dredze (2025). [DnDScore: Decontextualization and Decomposition for Factuality Verification in Long-Form Text Generation](https://aclanthology.org/2025.emnlp-main.1205/).

DOI：10.18653/v1/2025.emnlp-main.1205

读取范围：Targeted full-text reading: §§3.3–4.2, 5.2–5.3, 6.1–6.2, end §6 duplicate analysis, limitations, Appendix C.3 human evaluation and related Tables 8–9. Not all prompts/appendices.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### C09 · Harmful Factuality: LLMs Correcting What They Shouldn't

Mingchen Li; Hanzhi Zhang; Heng Fan; Junhua Ding; Yunhe Feng (2026). [Harmful Factuality: LLMs Correcting What They Shouldn't](https://aclanthology.org/2026.findings-eacl.46/).

DOI：10.18653/v1/2026.findings-eacl.46

读取范围：Publisher metadata; PDF pp.896–904 including §3 perturbation methods, §4.4 outcome definitions, §5 selected results, §6 mitigation, §8 limitations. Shell PDF extraction used after web find errors; middle of p.900 output truncated, not claimed fully read.

机制、结果适用范围和限制：[详细来源记录](phase2_claims_sources.json)。

### E01 · Beyond Accuracy: Behavioral Testing of NLP Models with CheckList

Marco Tulio Ribeiro; Tongshuang Wu; Carlos Guestrin; Sameer Singh (2020). [Beyond Accuracy: Behavioral Testing of NLP Models with CheckList](https://aclanthology.org/2020.acl-main.442/).

DOI：10.18653/v1/2020.acl-main.442

读取范围：Abstract, introduction and Section 2; PDF pp.1–3. User-study results only as summarized in the introduction; no independent full analysis of Section 3.

机制、结果适用范围和限制：[详细来源记录](phase2_evaluation_sources.json)。

### E02 · FaithBench: A Diverse Hallucination Benchmark for Summarization by Modern LLMs

Forrest Sheng Bao; Miaoran Li; Renyi Qu; Ge Luo; Erana Wan; Yujia Tang; Weisi Fan; Manveer Singh Tamber; Suleman Kazi; Vivek Sourabh; Mike Qi; Ruixuan Tu; Chenyu Xu; Matthew Gonzales; Ofer Mendelevitch; Amin Ahmad (2025). [FaithBench: A Diverse Hallucination Benchmark for Summarization by Modern LLMs](https://aclanthology.org/2025.naacl-short.38/).

DOI：10.18653/v1/2025.naacl-short.38

读取范围：Sections 2.2–2.4, selected Section 3 results/Table 2 discussion, Limitations and Appendix C composition; no dataset records.

机制、结果适用范围和限制：[详细来源记录](phase2_evaluation_sources.json)。

### E03 · Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards

Manveer Singh Tamber; Forrest Sheng Bao; Chenyu Xu; Ge Luo; Suleman Kazi; Minseok Bae; Miaoran Li; Ofer Mendelevitch; Renyi Qu; Jimmy Lin (2025). [Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards](https://aclanthology.org/2025.emnlp-industry.54/).

DOI：10.18653/v1/2025.emnlp-industry.54

读取范围：Sections 4–5, Section 6.1 and Table 1, conclusion; no prompt-example appendix or dataset records.

机制、结果适用范围和限制：[详细来源记录](phase2_evaluation_sources.json)。

### E04 · MARCH: Multi-Agent Reinforced Check for Hallucination

Zhuo Li; Yupeng Zhang; Pengyu Cheng; Jiajun Song; Mengyu Zhou; Hao Li; Shujie Hu; Yu Qin; Erchao Zhao; Xiaoxi Jiang; Guanjun Jiang (2026). [MARCH: Multi-Agent Reinforced Check for Hallucination](https://aclanthology.org/2026.acl-long.1828/).

DOI：10.18653/v1/2026.acl-long.1828

读取范围：Sections 2.1–2.3 architecture and reward introduction, Section 3.1 setup, Section 3.4 selected ablations, Section 6 Limitations; no training/demo appendices.

机制、结果适用范围和限制：[详细来源记录](phase2_evaluation_sources.json)。

### E05 · GAVEL: Evidence-Contract Debate with Mechanized Scrutiny for Provenance-Grounded Fact-Checking

Ruoyu Xu; Gaoxiang Li; Victor S. Sheng (2026). [GAVEL: Evidence-Contract Debate with Mechanized Scrutiny for Provenance-Grounded Fact-Checking](https://aclanthology.org/2026.findings-acl.1789/).

DOI：10.18653/v1/2026.findings-acl.1789

读取范围：Sections 3–5.5 and Limitations; PDF pp.3–8; no Appendix B case data.

机制、结果适用范围和限制：[详细来源记录](phase2_evaluation_sources.json)。

### I01 · Building effective agents

Erik S.; Barry Zhang (2024). [Building effective agents](https://www.anthropic.com/research/building-effective-agents).

读取范围：sections；What are agents?、When (and when not) to use agents、When and how to use frameworks、Building blocks, workflows, and agents、Combining and customizing these patterns、Appendix 2: Prompt engineering your tools、Authors & Acknowledgments；Observed web lines 48–185, 208–226; external linked implementations not read.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I02 · Citations

Anthropic (未注明首发年). [Citations](https://platform.claude.com/docs/en/build-with-claude/citations).

读取范围：sections；Introduction、Comparison with prompt-based approaches、How citations work、Automatic chunking vs custom content、Citable versus non-citable content、Citation indices、Token costs、Feature compatibility、Document types table；Observed web lines 79–191 and 237–245; SDK examples not executed.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I03 · Structured outputs

Google AI for Developers (2026). [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

读取范围：sections；Introduction、JSON schema support、Type-specific properties、Structured outputs versus function calling、Best practices、Limitations、Last updated footer；Observed web lines 88–98 and 1521–1586; long SDK example bodies not assessed or executed.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I04 · Effective context engineering for AI agents

Prithvi Rajasekaran; Ethan Dixon; Carly Ryan; Jeremy Hadfield (2025). [Effective context engineering for AI agents](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents).

读取范围：full_main_text；Context engineering vs. prompt engineering、Why context engineering is important、The anatomy of effective context、Context retrieval and agentic search、Context engineering for long-horizon tasks、Conclusion、Authors & Acknowledgments；Observed web lines 43–135; linked external studies not counted as read.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I05 · Demystifying evals for AI agents

Mikaela Grace; Jeremy Hadfield; Rodrigo Olivares; Jiri De Jonghe (2026). [Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).

读取范围：sections；The structure of an evaluation、Types of graders for agents、Capability vs. regression evals、Research agents、How to think about non-determinism、Roadmap to great evals、Holistic evaluation methods、Authors & Acknowledgments；Observed web lines 52–177, 262–264, 271–425, 447–450; framework appendix and linked benchmark papers not assessed.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I06 · Use contextual grounding check to filter hallucinations in responses

Amazon Web Services (未注明首发年). [Use contextual grounding check to filter hallucinations in responses](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html).

读取范围：sections；Definition and supported cases、Grounding versus relevance、Multiple sources note、Character limits、Confidence scores and thresholds、Required components；Observed web lines 5–28 and official search content; API configuration examples not executed.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### I07 · From extraction to action: Using grounding and confidence to build reliable document workflows

Joe Filcik; Colin Murphy (2026). [From extraction to action: Using grounding and confidence to build reliable document workflows](https://devblogs.microsoft.com/foundry/content-understanding-confidence-grounding-hitl/).

读取范围：full_main_text；Grounding、Confidence、A real workflow、Steps 1–3、The results、Try it yourself、Lessons for reliable automation、Authors；Observed web lines 19–163; videos and linked calibration notebook not executed/read.

机制、结果适用范围和限制：[详细来源记录](phase2_industry_sources.json)。

### V01 · Knowledge-Centric Hallucination Detection

Xiangkun Hu; Dongyu Ru; Lin Qiu; Qipeng Guo; Tianhang Zhang; Yang Xu; Yun Luo; Pengfei Liu; Yue Zhang; Zheng Zhang (2024). [Knowledge-Centric Hallucination Detection](https://aclanthology.org/2024.emnlp-main.395/).

DOI：10.18653/v1/2024.emnlp-main.395

读取范围：sections；3 Preliminaries、4 The REFCHECKER framework、5 The KNOWHALBENCH dataset、6 Experiments、Limitations；4-9；True；All appendices and released artifact code not audited

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V02 · MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents

Liyan Tang; Philippe Laban; Greg Durrett (2024). [MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents](https://aclanthology.org/2024.emnlp-main.499/).

DOI：10.18653/v1/2024.emnlp-main.499

读取范围：sections；2 Background and Motivation、3 Methodology: Training Data Synthesis、4 LLM-AGGREFACT Benchmark、5 Experimental Setup、6 Results、7 Rethinking LLM Fact-Checking、Limitations、A.2、A.3、B.1-B.2 relevant tables；2-10,15-17；True；All remaining appendix prompts/training details not audited

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V03 · AlignScore: Evaluating Factual Consistency with A Unified Alignment Function

Yuheng Zha; Yichi Yang; Ruichen Li; Zhiting Hu (2023). [AlignScore: Evaluating Factual Consistency with A Unified Alignment Function](https://aclanthology.org/2023.acl-long.634/).

DOI：10.18653/v1/2023.acl-long.634

读取范围：sections；3 Methods、4.1 Implementation、4.2 Benchmarks、beginning of main results table；2-6；False；Full remaining results, limitations and appendices

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V04 · QAFactEval: Improved QA-Based Factual Consistency Evaluation for Summarization

Alexander Fabbri; Chien-Sheng Wu; Wenhao Liu; Caiming Xiong (2022). [QAFactEval: Improved QA-Based Factual Consistency Evaluation for Summarization](https://aclanthology.org/2022.naacl-main.187/).

DOI：10.18653/v1/2022.naacl-main.187

读取范围：abstract_only；Official metadata、Abstract；False；Paper body, appendix, implementation

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V05 · Chain-of-Verification Reduces Hallucination in Large Language Models

Shehzaad Dhuliawala; Mojtaba Komeili; Jing Xu; Roberta Raileanu; Xian Li; Asli Celikyilmaz; Jason Weston (2024). [Chain-of-Verification Reduces Hallucination in Large Language Models](https://aclanthology.org/2024.findings-acl.212/).

DOI：10.18653/v1/2024.findings-acl.212

读取范围：sections；3 Chain-of-Verification、4.1 Tasks、4.2 Baselines、Tables 1-2；2-6；True；Rest of results and all appendix demonstrations

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V06 · Large Language Models Cannot Self-Correct Reasoning Yet

Jie Huang; Xinyun Chen; Swaroop Mishra; Huaixiu Steven Zheng; Adams Yu; Xinying Song; Denny Zhou (2024). [Large Language Models Cannot Self-Correct Reasoning Yet](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8b4add8b0aa8749d80a34ca5d941c355-Abstract-Conference.html).

读取范围：sections；2 Background and Related Work、3 Intrinsic Self-Correction、4 Debate vs Self-Consistency、5 Prompt Design、6 beginning；2-8；True；All appendix prompts and remaining discussion

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V07 · Sufficient Context: A New Lens on Retrieval Augmented Generation Systems

Hailey Joren; Jianyi Zhang; Chun-Sung Ferng; Da-Cheng Juan; Ankur Taly; Cyrus Rashtchian (2025). [Sufficient Context: A New Lens on Retrieval Augmented Generation Systems](https://arxiv.org/html/2411.06037v3).

读取范围：sections；3 Sufficient Context、4 A New Lens on RAG Performance、5 Techniques to Reduce Hallucinations、6 Conclusion and Limitations；True；All appendices and released source code

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V08 · FactCG: Enhancing Fact Checkers with Graph-Based Multi-Hop Data

Deren Lei; Yaxi Li; Siyao Li; Mengya Hu; Rui Xu; Ken Archer; Mingyu Wang; Emily Ching; Alex Deng (2025). [FactCG: Enhancing Fact Checkers with Graph-Based Multi-Hop Data](https://aclanthology.org/2025.naacl-long.258/).

DOI：10.18653/v1/2025.naacl-long.258

读取范围：sections；3 Problem Formulation、4 Multi-Hop Analysis、5 CG2C、6 Experiments、7 Connected Reasoning；3-8；True；Later limitations and all appendix results/code

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。

### V09 · Retromorphic Testing with Hierarchical Verification for Hallucination Detection in RAG

Boxi Yu; Yuzhong Zhang; Liting Lin; Lionel Briand; Emir Muñoz (2026). [Retromorphic Testing with Hierarchical Verification for Hallucination Detection in RAG](https://arxiv.org/html/2603.27752v1).

读取范围：sections；2 Preliminaries、3 Approach、4.1-4.6 Experiments、5 Limitations and Threats；True；Web extraction expanded into first three examples in §4.7; exposure recorded separately；Released toolkit, annotation files and sample files

机制、结果适用范围和限制：[详细来源记录](phase2_verification_sources.json)。
