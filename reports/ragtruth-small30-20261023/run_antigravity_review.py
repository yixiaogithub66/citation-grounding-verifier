"""Bounded headless High review of aggregate evaluation interpretation only."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("antigravity-review")
OUT.mkdir(exist_ok=False)
report = json.loads((ROOT / "results/ragtruth-small30-20261023/scored/report.json").read_text(encoding="utf-8"))
material = {k: report[k] for k in ("overall", "backends", "partial_aware_bootstrap", "runtime", "policy", "qualification")}
plan = Path(__file__).with_name("PLAN.md").read_text(encoding="utf-8")
prompt = """You are assisting the user's Citation Grounding verifier evaluation. Read-only review; use High reasoning.
Do NOT use tools, commands, files, browser, network, agents or external context. All needed information follows inline.
Review the interpretation of an already completed frozen exploratory 30-case evaluation. Do not propose benchmark-specific tuning, resampling, label changes or a new run. Do not claim author adjudication.
Check: scoring denominators and partial handling; whether generalization or improvement can be claimed; input adaptation risks (QA question omitted as evidence, Summary unchanged, Data2txt deterministic JSON preserving null/booleans); cost/latency interpretation; what limitations deserve prominence. Answer in concise Chinese, at most 600 words.
The preselection was committed before data selection, original production prompts/config unchanged. 30 unique sources, 10 per task, zero overlap with 33 known prior sources. Independent adaptation audit confirms byte-exact answers and source preservation; some literature exposure remains unmapped. No paired baseline on these 30. Complete empty outputs count negative under the frozen native scorer; there are 2, one FN and one TN. Do not infer that extraction completion guarantees semantic coverage.
PLAN:\n""" + plan + "\nAGGREGATE RESULTS:\n" + json.dumps(material, ensure_ascii=False)
request = (json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n").encode("utf-8")
args = [r"C:\Users\yixiao\.gemini\bin\agy.exe", "--new-project", "--mode", "plan", "--model", "gemini-4-argon-high", "--effort", "high", "--print-timeout", "5m", "--input-format", "stream-json", "--output-format", "stream-json"]
cwd = tempfile.mkdtemp(prefix="tabby-small30-review-")
def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
(OUT / "request.ndjson").write_bytes(request)
save("invocation.json", {"args": args, "cwd": cwd, "request_sha256": hashlib.sha256(request).hexdigest(), "scope": "aggregate read-only review; no tools; no author adjudication", "started_at": datetime.now(timezone.utc).isoformat()})
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
results = [event for event in events if event.get("event") == "result"]
save("process-result.json", {"exit_code": proc.returncode, "completed_at": datetime.now(timezone.utc).isoformat(), "event_types": [e.get("event") for e in events], "stderr_bytes": (OUT / "stderr.txt").stat().st_size})
if results:
    final = results[-1].get("result", results[-1])
    save("final-result.json", final)
    if isinstance(final.get("response"), str):
        (OUT / "response.md").write_text(final["response"] + "\n", encoding="utf-8", newline="\n")
    step_types = sorted({e["step_update"].get("step_type", "") for e in events if e.get("event") == "step_update"})
    valid = (proc.returncode == 0 and final.get("status") == "SUCCESS" and bool(final.get("response"))
             and not (set(step_types) - {"user_input", "agent_response"})
             and (OUT / "stderr.txt").stat().st_size == 0)
    save("validation.json", {"valid": valid, "step_types": step_types, "status": final.get("status"), "exit_code": proc.returncode})
    print(json.dumps({"exit_code": proc.returncode, "status": final.get("status"), "has_response": bool(final.get("response")), "output": str(OUT)}, ensure_ascii=False))
    if not valid:
        raise RuntimeError("Final result did not pass bounded review validation")
else:
    raise RuntimeError("No final result; inspect recorded events and stderr")
