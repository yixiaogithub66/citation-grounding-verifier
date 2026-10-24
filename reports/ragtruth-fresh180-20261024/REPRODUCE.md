# fresh180 离线复算

使用本目录的 `evidence.zip`；它是 `bd51922` 中实验包的原样副本，未因发布目录整理重新打包。原始说明也在包内和[固定历史提交](https://github.com/yixiaogithub66/citation-grounding-verifier/blob/bd51922/reports/ragtruth-fresh180-20261024/REPRODUCE.md)中保留。本页仅提供当前仓库可直接找到的复算入口。

## 1. 校验与解压

从仓库根目录运行。需要Python 3.11+；原实验及打包复算使用Python 3.12.5。`results/ragtruth-replay` 应为新的、尚不存在的目录。

```sh
python -c "import hashlib,pathlib; p=pathlib.Path('reports/ragtruth-fresh180-20261024/evidence.zip'); assert hashlib.sha256(p.read_bytes()).hexdigest() == '6432ceb6cef99e357a12814cb2c9f73390601e6088b3c105f64171be3c6f341e'; print('ZIP SHA256 verified')"
python -m zipfile -e reports/ragtruth-fresh180-20261024/evidence.zip results/ragtruth-replay
cd results/ragtruth-replay
```

归档根目录含 `FILES-SHA256.json`，以及原工作区相对路径下的dataset、research、reports、results。使用包内冻结源码，不要用当前工作区日后修改的评分器代替。

## 2. 不调用模型重新计分

在上一步解压后的归档根目录执行：

```sh
python -X utf8 results/ragtruth-fresh180-freeze-20261024/source/research/ragtruth-fresh180-20261024/summarize.py --run-dir results/ragtruth-fresh180-20261024 --data-dir dataset/ragtruth-fresh180-20261024 --output-dir rescored
```

`rescored` 必须尚不存在。脚本校验65个冻结文件、输入/金标、配置绑定以及所有结果和预留的哈希，重算180条×3后端与固定种子的来源簇bootstrap。它不读取API密钥，也不发送模型请求。

比较 `rescored/report.json` 与包内 `reports/ragtruth-fresh180-20261024/scored/report.json`。出包时已经实际解压并复算，完整JSON的语义与字节一致。发布目录保留的 [scored/report.json](scored/report.json) 是原始报告副本。

## 边界

- 复算是对已经保存的预测重新打分，不是再次调用模型。再次推理可能受模型版本、随机性和服务状态影响，不能承诺输出逐字相同。
- 包内历史manifest含原执行机器的绝对路径作为溯源记录。冻结scorer按自身位置定位源码，可在新解压目录执行；推理runner和抽样器迁移时则需要显式的新环境路径绑定，不能覆盖原清单后仍声称原哈希有效。
- 已预留的失败、partial或孤立请求不得为改善成绩自动重发。新的重复实验应使用新目录，保留这次归档，且不能再称这批来源为未见。
- 原生标签、作者裁定和AI意见分开保存；结构哈希和离线复算不能证明语义金标无误。
