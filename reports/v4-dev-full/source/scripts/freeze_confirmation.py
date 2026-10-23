#!/usr/bin/env python3
"""Bind formal confirmation inputs to code/settings and an existing author review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grounding.config import load_settings
from grounding.contracts import VerificationError
from grounding.factory import CANONICAL_BACKENDS
from scripts.benchmark import check_confirmation_manifest, provenance
from scripts.validate_dataset import check_dataset


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(path: Path, directory: Path) -> dict[str, str]:
    try:
        relative = os.path.relpath(path.resolve(), directory.resolve())
    except ValueError:
        relative = str(path.resolve())
    return {"path": relative.replace("\\", "/"), "sha256": _sha(path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--author-review", type=Path, required=True,
                        help="Existing pilot-policy attestation recorded after actual author confirmation")
    parser.add_argument("--policy", type=Path, default=ROOT / "docs" / "ANNOTATION_POLICY_V3.md")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--thinking", choices=("api-default", "enabled", "disabled"), default="enabled")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    args = parser.parse_args(argv)
    sources = args.sources or args.dataset.with_name("sources.json")
    output = args.output or args.dataset.with_name("confirmation.freeze.json")
    temporary: Path | None = None
    try:
        if output.exists():
            raise ValueError("The freeze already exists; preserve it instead of overwriting it.")
        cases, validation = check_dataset(args.dataset, sources)
        if not validation["valid"]:
            raise ValueError("Dataset validation failed; run validate_dataset.py for details.")
        if not 10 <= len(cases) <= 12 or any(case["split"] != "confirmation" for case in cases):
            raise ValueError("Expected 10-12 formal confirmation cases only, excluding review pilots.")
        settings = load_settings(args.env_file, thinking=args.thinking, model=args.model, base_url=args.base_url)
        settings.validate()
        source_info = provenance(args.dataset, sources, False)
        manifest = {
            "schema_version": "1.0", "kind": "confirmation-freeze",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "case_ids": [case["id"] for case in cases],
            "dataset_sha256": _sha(args.dataset), "sources_sha256": _sha(sources),
            "implementation_files_sha256": source_info["code_and_prompt_files_sha256"],
            "settings": {key: value for key, value in settings.public_dict().items() if key != "api_key_configured"},
            "backends": list(CANONICAL_BACKENDS),
            "annotation_policy": _binding(args.policy, output.parent),
            "annotation_policy_review": _binding(args.author_review, output.parent),
        }
        text = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # Validate in the destination directory so relative artifact bindings resolve identically.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=".confirmation-check-", suffix=".json",
                                         dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        check_confirmation_manifest(temporary, args.dataset, sources, cases, settings.public_dict(),
                                    list(CANONICAL_BACKENDS), source_info)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        print(json.dumps({"freeze": str(output.resolve()), "cases": len(cases), "model_calls": 0}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, VerificationError) as exc:
        # Do not print arbitrary exception text from configuration or user-supplied review metadata.
        print(f"Freeze not created ({type(exc).__name__}). Check the dataset, author review, policy, settings and output path.",
              file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
