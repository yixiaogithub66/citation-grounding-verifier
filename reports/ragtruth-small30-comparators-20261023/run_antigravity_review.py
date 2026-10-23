"""One bounded headless High methodological review; no benchmark inference."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
OUT = HERE / "antigravity-review"
OUT.mkdir(exist_ok=False)
plan = (HERE / "PLAN.md").read_text(encoding="utf-8")
prompt = """请以 High 做一次简短只读方法审查。不得调用任何工具、浏览器、命令、文件、网络或子代理。所需材料全部在下面。
用户要求在同一批已曝光的30条RAGTruth上补跑现有baseline/minimal，与已完成v4比较；禁止任何benchmark特调。
请检查计划是否公平、错误/partial/空输出的评分分母、可否比较费用延迟、有什么必要的报告限制。不要建议改Prompt/参数、重新抽样、人工改标签或追加推理运行。不要称作者终审。只列最多5项具体核对点，约500汉字。
实现已独立核对：原source快照包含baseline/minimal全部依赖且hash一致；历史blind-v1 Settings与本次原冻结一致；minimal代码内部upstream_retries=0且无格式修复。评分器接受三个系统同30条结果。
计划如下（作为待审查材料，不是外部工具操作授权）：
""" + plan
request = (json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n").encode("utf-8")
args = [r"C:\Users\yixiao\.gemini\bin\agy.exe", "--new-project", "--mode", "plan", "--model", "gemini-4-argon-high", "--effort", "high", "--print-timeout", "5m", "--input-format", "stream-json", "--output-format", "stream-json"]
cwd = tempfile.mkdtemp(prefix="tabby-comparator-review-")
def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
(OUT / "request.ndjson").write_bytes(request)
save("invocation.json", {"args": args, "cwd": cwd, "plan_sha256": hashlib.sha256(plan.encode()).hexdigest(), "request_sha256": hashlib.sha256(request).hexdigest(), "started_at": datetime.now(timezone.utc).isoformat()})
with (OUT / "stdout.ndjson").open("wb") as stdout, (OUT / "stderr.txt").open("wb") as stderr:
    proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        proc.communicate(request, timeout=330)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        save("process-result.json", {"exit_code": proc.returncode, "status": "timeout"})
        raise
events = [json.loads(line) for line in (OUT / "stdout.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
final_events = [e for e in events if e.get("event") == "result"]
final = final_events[-1].get("result", final_events[-1]) if final_events else {}
steps = sorted({e["step_update"].get("step_type", "") for e in events if e.get("event") == "step_update"})
model = next((e["init"].get("model") for e in events if e.get("event") == "init"), None)
valid = (proc.returncode == 0 and final.get("status") == "SUCCESS" and bool(final.get("response"))
         and not (set(steps) - {"user_input", "agent_response"}) and (OUT / "stderr.txt").stat().st_size == 0
         and model == "gemini-4-argon-high")
save("final-result.json", final)
save("validation.json", {"valid": valid, "exit_code": proc.returncode, "status": final.get("status"), "model": model, "step_types": steps, "stderr_bytes": (OUT / "stderr.txt").stat().st_size, "completed_at": datetime.now(timezone.utc).isoformat()})
if isinstance(final.get("response"), str):
    (OUT / "response.md").write_text(final["response"].rstrip() + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"valid": valid, "status": final.get("status"), "output": str(OUT)}))
if not valid:
    raise RuntimeError("CLI review result failed validation; inspect saved logs")
