"""Headless High discussion on supplied verified research; no UI or tool use."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--prompt", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
prompt = a.prompt.read_text(encoding="utf-8")
request = (json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n").encode("utf-8")
args = [r"C:\Users\yixiao\.gemini\bin\agy.exe", "--new-project", "--mode", "plan", "--model", "gemini-4-argon-high", "--effort", "high", "--print-timeout", "5m", "--input-format", "stream-json", "--output-format", "stream-json"]
cwd = tempfile.mkdtemp(prefix="tabby-methods-gemini-")
def save(name, data):
    (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
(out / "request.ndjson").write_bytes(request)
save("invocation.json", {"args": args, "cwd": cwd, "prompt_sha256": hashlib.sha256(a.prompt.read_bytes()).hexdigest(), "request_sha256": hashlib.sha256(request).hexdigest(), "started_at": datetime.now(timezone.utc).isoformat()})
with (out / "stdout.ndjson").open("wb") as so, (out / "stderr.txt").open("wb") as se:
    proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=so, stderr=se, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        proc.communicate(request, timeout=330)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        save("process-result.json", {"status": "timeout", "exit_code": proc.returncode})
        raise
events = [json.loads(line) for line in (out / "stdout.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
results = [e for e in events if e.get("event") == "result"]
final = results[-1].get("result", results[-1]) if results else {}
steps = sorted({e["step_update"].get("step_type", "") for e in events if e.get("event") == "step_update"})
model = next((e["init"].get("model") for e in events if e.get("event") == "init"), None)
valid = (proc.returncode == 0 and final.get("status") == "SUCCESS" and bool(final.get("response"))
         and not (set(steps) - {"user_input", "agent_response"}) and (out / "stderr.txt").stat().st_size == 0
         and model == "gemini-4-argon-high")
save("final-result.json", final)
save("validation.json", {"valid": valid, "exit_code": proc.returncode, "status": final.get("status"), "model": model, "step_types": steps, "stderr_bytes": (out / "stderr.txt").stat().st_size, "completed_at": datetime.now(timezone.utc).isoformat()})
if isinstance(final.get("response"), str):
    (out / "response.md").write_text(final["response"].rstrip() + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"valid": valid, "status": final.get("status"), "output": str(out)}))
if not valid:
    raise RuntimeError("Gemini discussion failed result validation; inspect recorded logs")
