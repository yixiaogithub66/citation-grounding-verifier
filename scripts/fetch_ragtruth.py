"""Fetch an immutable upstream RAGTruth snapshot without displaying its records."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen


REVISION = "c103204b9ce28d6bbad859304bf30de72b8ed8fe"
REPOSITORY = "https://github.com/ParticleMedia/RAGTruth"
FILES = {
    "response.jsonl": ("dataset/response.jsonl", "f9ae5913fb9976684f3e13be3cd3465062db54cc",
                       "e4c2e4ac24fff676d8984cc61c35d791612fadc58015335d97dd632375e18073"),
    "source_info.jsonl": ("dataset/source_info.jsonl", "119277774009f110aa58596b93f9512f62594a89",
                          "0dffc26ea9f3c1c3d7c7e8336b56ef1646e3cec876edffcca3c9c624d12d578b"),
    "LICENSE": ("LICENSE", "71ba6fcf69d6c0d3c246115c237d63ab98a5baad", None),
}


def verify_bytes(data: bytes, blob_sha1: str, sha256: str | None) -> dict:
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    digest = hashlib.sha256(data).hexdigest()
    if blob != blob_sha1 or (sha256 is not None and digest != sha256):
        raise ValueError("Downloaded bytes do not match the pinned upstream snapshot")
    return {"bytes": len(data), "sha256": digest, "git_blob_sha1": blob}


def fetch_snapshot(output_dir: Path, *, timeout: float = 120.0) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, (remote_path, blob, sha) in FILES.items():
        target = output_dir / name
        url = f"https://raw.githubusercontent.com/ParticleMedia/RAGTruth/{REVISION}/{remote_path}"
        if target.exists():
            data = target.read_bytes()
        else:
            with urlopen(url, timeout=timeout) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError("Unexpectedly large upstream file")
        metadata = verify_bytes(data, blob, sha)
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        records[name] = {"url": url, **metadata}
    provenance_path = output_dir / "provenance.json"
    if provenance_path.exists():
        previous = json.loads(provenance_path.read_text(encoding="utf-8"))
        if previous.get("revision") != REVISION:
            raise ValueError("Existing provenance refers to a different upstream revision")
        for name in ("response.jsonl", "source_info.jsonl"):
            if previous.get("files", {}).get(name, {}).get("sha256") != records[name]["sha256"]:
                raise ValueError("Existing provenance does not match the verified files")
        return previous
    provenance = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": records,
        "note": "Pinned original files; no response text or labels printed during download.",
    }
    with provenance_path.open("x", encoding="utf-8") as stream:
        json.dump(provenance, stream, indent=2)
        stream.write("\n")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/ragtruth-upstream"))
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if not 0 < args.timeout <= 600:
        parser.error("timeout must be within (0, 600] seconds")
    result = fetch_snapshot(args.output_dir, timeout=args.timeout)
    print(json.dumps({"revision": result["revision"], "output_dir": str(args.output_dir),
                      "verified_files": list(FILES)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
