#!/usr/bin/env python3
"""Archive this completed experiment and verify a relocated offline rescore.

No model or provider client is invoked. Original evidence and frozen manifests
are never modified. All paths in the ZIP retain workspace-relative structure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

REL = "ragtruth-fresh180-20261024"
FREEZE = "results/ragtruth-fresh180-freeze-20261024"
RUN = "results/" + REL
REPORTS = "reports/" + REL
RESEARCH = "research/" + REL
DATA = "dataset/" + REL
MANIFEST = "FILES-SHA256.json"
EXCLUDE_NAMES = {"evidence.zip", "evidence.zip.sha256", "PACKAGE-VALIDATION.json", MANIFEST}
SENSITIVE_NAMES = {"credentials.json", "credential.json", "oauth_creds.json", "token.json", "tokens.json", "secrets.json"}
SECRET_PATTERN = re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AIza[A-Za-z0-9_-]{30,})\b")
PLACEHOLDER_WORDS = (b"test", b"fake", b"example", b"dummy", b"redacted", b"placeholder")


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def safe_member(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not name or "\\" in name or ":" in name or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("Unsafe archive member name")
    return path


def forbidden_name(path):
    name = path.name.lower()
    return name.startswith(".env") or name in SENSITIVE_NAMES or name.startswith("client_secret") or name.startswith("credentials.")


def exclude(path):
    return "__pycache__" in path.parts or path.suffix.lower() in (".pyc", ".pyo", ".zip", ".tmp") or path.name in EXCLUDE_NAMES


def scan_bytes(name, raw):
    if re.search(rb"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{32,}", raw):
        raise ValueError("Private-key marker in archive candidate: " + name)
    for match in SECRET_PATTERN.finditer(raw):
        if not any(word in match.group().lower() for word in PLACEHOLDER_WORDS):
            raise ValueError("Possible credential in archive candidate (value withheld): " + name)
    # Exact configured credentials in the process environment are also forbidden.
    for variable in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(variable, "")
        if value and len(value) >= 8 and value.encode() in raw:
            raise ValueError("Configured credential in archive candidate (value withheld): " + name)


def candidates(workspace):
    pre = read(workspace / FREEZE / "preselection.json")
    frozen = pre["code_files_sha256"]
    source_prefix = FREEZE + "/source/"
    files = {}
    for folder in (DATA, RESEARCH, REPORTS, FREEZE, RUN):
        base = workspace / folder
        if not base.is_dir():
            raise ValueError("Missing required evidence directory: " + folder)
        for path in sorted(base.rglob("*")):
            if not path.is_file() or exclude(path):
                continue
            if forbidden_name(path):
                raise ValueError("Credential/configuration file is not permitted: " + path.name)
            if path.is_symlink() or not path.resolve().is_relative_to(workspace):
                raise ValueError("Archive candidate is a link or escaped workspace")
            name = path.relative_to(workspace).as_posix()
            safe_member(name)
            if name.startswith(source_prefix) and name[len(source_prefix):] not in frozen:
                raise ValueError("Unfrozen file in frozen source tree: " + name)
            raw = path.read_bytes()
            scan_bytes(name, raw)
            files[name] = {"sha256": sha_bytes(raw), "size_bytes": len(raw)}
    for name, digest in frozen.items():
        member = source_prefix + name
        if files.get(member, {}).get("sha256") != digest:
            raise ValueError("Frozen source is absent or changed: " + name)
    required = [RUN + "/predictions.jsonl", RUN + "/result-integrity.json", RUN + "/progress.json",
                RUN + "/config.json", RUN + "/preselection.json", RUN + "/binding.json",
                RUN + "/exposure-reservation.json", RUN + "/exposure-final.json",
                REPORTS + "/scored/report.json", REPORTS + "/operational-audit.json", REPORTS + "/REPRODUCE.md",
                DATA + "/UPSTREAM_LICENSE"]
    if any(name not in files for name in required):
        raise ValueError("A required completed-run artifact is missing")
    progress = read(workspace / RUN / "progress.json")
    if progress.get("status") not in ("completed", "completed_with_unknown") or progress.get("finalized_records") != 540 or progress.get("frozen_artifacts_unchanged") is not True:
        raise ValueError("Run is not finalized and frozen")
    audit = read(workspace / REPORTS / "operational-audit.json")
    if audit.get("final") is not True or audit.get("status") != "passed" or audit.get("violations"):
        raise ValueError("Final operational audit has not passed")
    return files, pre


def make_zip(path, workspace, files, manifest):
    with path.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, metadata in files.items():
                raw = (workspace / name).read_bytes()
                if sha_bytes(raw) != metadata["sha256"]:
                    raise ValueError("Evidence changed while packaging: " + name)
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 24, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            info = zipfile.ZipInfo(MANIFEST, date_time=(2026, 10, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, encoded(manifest), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        stream.flush()
        os.fsync(stream.fileno())


def extract_verify(archive_path, destination, expected):
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected) | {MANIFEST}:
            raise ValueError("ZIP member inventory differs or contains duplicate members")
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC check failed")
        manifest = json.loads(archive.read(MANIFEST))
        if manifest["files"] != expected:
            raise ValueError("ZIP manifest differs from the prepackaging inventory")
        for name in names:
            member = safe_member(name)
            target = destination.joinpath(*member.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Extraction path escaped destination")
            raw = archive.read(name)
            if name != MANIFEST and (sha_bytes(raw) != expected[name]["sha256"] or len(raw) != expected[name]["size_bytes"]):
                raise ValueError("Archived file does not match manifest: " + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    if actual != set(expected) | {MANIFEST}:
        raise ValueError("Extracted file inventory differs")
    for name, metadata in expected.items():
        if sha(destination / name) != metadata["sha256"]:
            raise ValueError("Extracted file hash differs: " + name)
    return len(actual)


def differences(a, b, path="$", limit=12):
    if type(a) is not type(b):
        return [path + " (type)"]
    if isinstance(a, dict):
        if set(a) != set(b):
            return [path + " (keys)"]
        found = []
        for key in sorted(a):
            found.extend(differences(a[key], b[key], path + "." + str(key), limit))
            if len(found) >= limit:
                break
        return found[:limit]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + " (length)"]
        found = []
        for index, (left, right) in enumerate(zip(a, b)):
            found.extend(differences(left, right, f"{path}[{index}]", limit))
            if len(found) >= limit:
                break
        return found[:limit]
    return [] if a == b else [path]


def package(workspace):
    workspace = Path(workspace).resolve()
    destination = workspace / RESEARCH / "evidence.zip"
    digest_path = destination.with_name(destination.name + ".sha256")
    validation_path = workspace / RESEARCH / "PACKAGE-VALIDATION.json"
    if destination.exists() or digest_path.exists() or validation_path.exists():
        raise FileExistsError("Package outputs already exist; refusing to silently replace an archived experiment")
    files, pre = candidates(workspace)
    manifest = {"schema_version": "ragtruth-fresh180-evidence-manifest-v1", "file_count": len(files),
                "files": files, "self_hash_policy": "This manifest and the final ZIP hash are excluded from the per-file map.",
                "archive_paths": "workspace-relative; source and run manifests are preserved byte-for-byte",
                "frozen_source_file_count": len(pre["code_files_sha256"])}
    temporary_root = workspace / "tmp"
    temporary_root.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="ragtruth-fresh180-package-check-", dir=temporary_root))
    archive_path, extracted = stage / "evidence.zip", stage / "extracted"
    make_zip(archive_path, workspace, files, manifest)
    extracted_count = extract_verify(archive_path, extracted, files)
    scorer = extracted / FREEZE / "source/research/ragtruth-fresh180-20261024/summarize.py"
    rescored = stage / "rescored"
    command = [sys.executable, "-B", "-X", "utf8", str(scorer), "--run-dir", str(extracted / RUN),
               "--data-dir", str(extracted / DATA), "--output-dir", str(rescored)]
    env = dict(os.environ)
    for key in tuple(env):
        if key in ("PYTHONPATH", "LLM_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
            env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    if completed.returncode:
        raise RuntimeError("Offline rescore failed (see retained temporary directory): " + completed.stderr[-4000:])
    reported = json.loads(completed.stdout)
    if reported.get("model_calls") != 0 or reported.get("manifest_count") != 180:
        raise ValueError("Offline scorer did not report zero model calls and 180 cases")
    original_report = extracted / REPORTS / "scored/report.json"
    reproduced_report = rescored / "report.json"
    original, reproduced = read(original_report), read(reproduced_report)
    diff = differences(original, reproduced)
    if diff:
        raise ValueError("Full offline report semantic comparison failed: " + ", ".join(diff))
    # Detect concurrent changes before publishing. Added evidence also invalidates
    # the archive, even when existing file bytes have remained unchanged.
    current, _ = candidates(workspace)
    if current != files:
        raise ValueError("Evidence inventory changed during packaging; archive not published")
    archive_sha = sha(archive_path)
    validation = {"schema_version": "ragtruth-fresh180-package-validation-v1", "status": "passed",
                  "validated_at": datetime.now(timezone.utc).isoformat(), "archive_path": destination.relative_to(workspace).as_posix(),
                  "archive_sha256": archive_sha, "archive_bytes": archive_path.stat().st_size,
                  "evidence_file_count": len(files), "zip_member_count": len(files) + 1, "extracted_file_count": extracted_count,
                  "uncompressed_evidence_bytes": sum(v["size_bytes"] for v in files.values()),
                  "all_extracted_file_hashes_match": True, "frozen_source_file_count": len(pre["code_files_sha256"]),
                  "offline_rescore": {"model_calls": 0, "manifest_count": 180, "exit_code": completed.returncode,
                                      "full_report_semantically_identical": True, "compared_top_level_keys": sorted(original),
                                      "original_report_sha256": sha(original_report), "rescored_report_sha256": sha(reproduced_report),
                                      "byte_identical": original_report.read_bytes() == reproduced_report.read_bytes(),
                                      "retained_validation_directory": str(stage)},
                  "secrets": {"credential_files_excluded_or_rejected": True, "common_literal_secret_prefix_scan_passed": True,
                              "configured_environment_credentials_scan_passed": True,
                              "limitation": "Finite filename/prefix/exact-environment checks; not a cryptographic proof that arbitrary text can never contain a secret."},
                  "package_script_sha256": sha(__file__), "preselection_sha256": sha(workspace / FREEZE / "preselection.json")}
    # Same-volume hardlink publishes complete ZIP bytes without replacement.
    os.link(archive_path, destination)
    with digest_path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(archive_sha + "  evidence.zip\n")
    with validation_path.open("xb") as stream:
        stream.write(encoded(validation))
    return validation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    result = package(args.workspace)
    print(json.dumps({key: result[key] for key in ("status", "archive_path", "archive_sha256", "archive_bytes", "evidence_file_count", "zip_member_count", "frozen_source_file_count")} | {"offline_rescore_identical": result["offline_rescore"]["full_report_semantically_identical"]}, sort_keys=True))
