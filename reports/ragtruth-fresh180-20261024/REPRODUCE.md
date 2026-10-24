# Fresh RAGTruth 180：归档与复现说明

本文件只描述证据归档与复算方法，不参与抽样、推理或评分。实际完成数、错误数、费用和性能以最终 `progress.json`、`result-integrity.json` 与评分报告为准。`preselection.code_files_sha256` 实际包含65个冻结文件，执行时Python版本为3.12.5。

## 推荐归档目录

```text
archive-root/
  FILES-SHA256.json
  dataset/ragtruth-fresh180-20261024/
    inputs.jsonl、manifest.jsonl、native_gold.jsonl、preparation.json
    README.md、UPSTREAM_LICENSE
  research/ragtruth-fresh180-20261024/
    计划、指标协议、曝光审计及辅助审阅材料
  results/ragtruth-fresh180-freeze-20261024/
    preselection.json、sampling-preselection.json、binding.json及SHA256 sidecar
    source/                完整65文件冻结源码树，保持相对目录与原始字节
  results/ragtruth-fresh180-20261024/
    config.json
    preselection.json、binding.json  与freeze对应文件字节相同，供scorer读取
    planned-pairs.json
    reservations/          每个(case,backend)验证前写入的持久预留
    records/               完整结果与全部可用telemetry，含错误和partial
    operations/            初次启动及任何resume记录
    predictions.jsonl      最终540个配对记录；未知预留项显式UNKNOWN
    result-integrity.json、progress.json
    exposure-reservation.json  与binding中的初始SHA一致，不改写
    exposure-final.json        如已更新canonical ledger，保留其最终副本
  reports/ragtruth-fresh180-20261024/
    scored/report.json、scored/report.md
    operational-audit.json、operational-audit.md、operational-audit.py
    REPRODUCE.md
    其他来源去重审计、独立评分核对及Gemini意见与主代理处置
```

归档根目录保留工作区相对路径，不再另建source/run/data映射。归档必须保留全部失败、partial、未知结果和内部调用记录，不能只保留成功样本或筛选后的摘要。完整保留 `results/ragtruth-fresh180-freeze-20261024/source/`；不能用日后工作区的源码替代。`config.json` 和 `preselection.json` 中的 `code_files_sha256` 应能在该冻结源码根目录下逐项核验。目录树是最小建议清单；新增审计和最终报告依实际路径一并归档。

不归档 `.env`、认证令牌或 API 密钥。冻结源码按manifest内65个文件归档；运行期间生成的 `__pycache__`、`.pyc` 和临时文件不属于冻结证据。上游许可证与数据说明应随数据切片保留。无需复制整份上游原始数据来复算这次180条的结果；若要审计机械抽样本身，可按预注册的上游版本与原始文件哈希另行取得原始数据。

## 无模型调用的离线复算

在解压后的归档根目录，用本次记录的 Python 版本运行：

```powershell
python -X utf8 results/ragtruth-fresh180-freeze-20261024/source/research/ragtruth-fresh180-20261024/summarize.py --run-dir results/ragtruth-fresh180-20261024 --data-dir dataset/ragtruth-fresh180-20261024 --output-dir rescored
```

`rescored` 必须是一个尚不存在的新目录。冻结 scorer 会核对源码、数据、冻结清单、全部预留/结果哈希和最终 journal，然后重新计算指标与固定种子的来源簇 bootstrap。此过程不需要 API 密钥，也不会发送模型请求。

正式出包前应在一个新目录中实际解压并完成这一步，将复算的关键数值与正式报告逐项比较。数值相同即可支持评分可复现；复算报告可能包含本机路径等环境字段，不能因此要求整份 JSON 的字节哈希必然相同。

冻结 scorer 的源码根目录由自身文件位置确定，因此上面的离线复算支持归档迁移，无须改写manifest。冻结推理 runner、抽样器和部分审计工具中，`preselection.source_root` 等字段保留原执行环境的绝对路径；这些工具迁移到另一台机器时，需要显式的本机路径重绑定。应另存路径映射或新复制实验清单，并保留原始freeze、binding及其哈希作为证据。追加可审计的路径重绑定不等于篡改原始manifest；直接覆盖原始清单中的路径并仍声称其原始哈希有效，则会破坏证据链。现有推理runner没有路径映射参数，不应声称它在任意解压目录均可原样运行。

## 推理重复与失败恢复的区别

这次实验只有一次外层验证机会：每个(case,backend)先写预留，再执行现有系统。v4已有的内部重试属于冻结系统行为，所有可用尝试均计入telemetry与费用；外层不会为提高得分重跑失败请求。

原执行环境下，`--resume` 仅可补做从未预留的配对。已有预留却没有持久结果的配对必须保留为 UNKNOWN；已保存错误或partial也不会重新调用。不要把这次已曝光的切片重新命名为新的未见评测。

若未来需要再次调用模型，应建立新的运行目录和单独的复制实验记录，保持此次原始归档不变，并标明同批已曝光输入上的重复实验。模型可能随服务端版本、随机采样或资源状态变化；离线评分复现与重新调用模型得到相同输出是不同要求。

## Exposure ledger 的收尾

本轮 `prepare.py` 在模型调用前创建 canonical exposure reservation，并把当时字节哈希记录为 `binding.exposure_record_initial_sha256`。本轮 `run.py` 不会自动将 canonical exposure ledger 更新为最终状态。

运行结束后，可根据最终运行证据更新 canonical ledger 的 `status`、`completed_at`、`completed_records`、`error_records`、`partial_records` 等运行元数据。保留 `run_id`、来源ID、回答ID、数据哈希与来源暴露身份；不能把失败来源改回未曝光。初始的 `exposure-reservation.json` 应保持原字节，并继续匹配 binding 的初始SHA。最终ledger另存 `exposure-final.json`，由归档文件清单记录其哈希；不要改写 binding 来替换初始哈希。

## 最后生成归档哈希

等待推理、评分、所有审计和说明文件完成后，再生成 `FILES-SHA256.json`，覆盖归档中每个普通文件的相对路径和SHA256。该清单不包含它自己及最终zip，避免自引用。保留 `result-integrity.json` 原样作为运行阶段的独立校验链。

生成zip后，在zip外另存其SHA256。检查zip条目中没有绝对路径、路径上跳、认证文件或临时输出，并验证解压后的文件哈希和离线复算。归档仅保存本次运行证据，不能把AI审核意见标为作者人工终审。
