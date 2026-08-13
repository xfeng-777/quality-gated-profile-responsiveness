from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "audit"

EXCLUDED_PARTS = {".git", "__pycache__", "audit"}
SCAN_EXCLUDED_FILES = {"audit_package.py"}
NAME_ALLOWED_FILES = {"LICENSE-CODE", "LICENSE-DATA", "LICENSE-SCOPE.md"}
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".py", ".txt"}

SENSITIVE_PATTERNS = {
    "credential_like_value": re.compile(
        r"(?:sk-[A-Za-z0-9_-]{8,}|"
        r"(?:api[_-]?key|authorization|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,})",
        re.IGNORECASE,
    ),
    "email_address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "local_absolute_path": re.compile(
        r"(?:/home/[^\s,;\"']+|\\\\wsl\.localhost\\[^\s,;\"']+)",
        re.IGNORECASE,
    ),
    "known_natural_person_name": re.compile(
        r"\b(?:Yixin Tian|Jiayi Li|Jiayu Sun|Shicong Yuan|zhengjiuzhe)\b",
        re.IGNORECASE,
    ),
}


def included_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_text(path: Path) -> list[dict[str, object]]:
    if path.name in SCAN_EXCLUDED_FILES or path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    findings: list[dict[str, object]] = []
    text = path.read_text(encoding="utf-8-sig")
    for line_number, line in enumerate(text.splitlines(), 1):
        for category, pattern in SENSITIVE_PATTERNS.items():
            if category == "known_natural_person_name" and path.name in NAME_ALLOWED_FILES:
                continue
            if pattern.search(line):
                findings.append({
                    "file": path.relative_to(ROOT).as_posix(),
                    "line": line_number,
                    "category": category,
                })
    return findings


def main() -> int:
    AUDIT.mkdir(exist_ok=True)
    files = included_files()
    manifest = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]
    findings = [finding for path in files for finding in scan_text(path)]
    report = {
        "scope": "release candidates excluding .git/, audit/, and __pycache__/",
        "files_scanned": len(files),
        "content_scan_exclusions": sorted(SCAN_EXCLUDED_FILES),
        "patterns": sorted(SENSITIVE_PATTERNS),
        "finding_count": len(findings),
        "status": "pass" if not findings else "review_required",
        "findings": findings,
    }
    (AUDIT / "sha256_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (AUDIT / "sensitive_information_scan.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
