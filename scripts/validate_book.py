from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "SUMMARY.md"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)")
INLINE_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MIN_CHARS = 1500
MIN_BOOK_CHARS = 250_000
MIN_CHAPTERS = 58


def chapter_paths() -> list[Path]:
    text = SUMMARY.read_text(encoding="utf-8")
    paths: list[Path] = []
    for raw in LINK_RE.findall(text):
        rel = unquote(raw.split("#", 1)[0])
        paths.append((ROOT / rel).resolve())
    return paths


def check_internal_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw in INLINE_LINK_RE.findall(text):
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_raw = unquote(raw.split("#", 1)[0])
        if not target_raw:
            continue
        target = (path.parent / target_raw).resolve()
        if not target.exists():
            errors.append(f"broken link: {path.relative_to(ROOT)} -> {raw}")
    return errors


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    total_chars = 0
    total_lines = 0
    total_fences = 0
    paths = chapter_paths()

    if len(paths) != len(set(paths)):
        errors.append("SUMMARY.md contains duplicate chapter paths")

    for path in paths:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        if not path.exists():
            errors.append(f"missing: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        content_chars = len(re.sub(r"\s+", "", text))
        total_chars += content_chars
        total_lines += text.count("\n") + 1
        fences = len(re.findall(r"^```", text, flags=re.MULTILINE))
        total_fences += fences
        if fences % 2:
            errors.append(f"unclosed code fence: {rel}")
        if content_chars < MIN_CHARS and path.name != "README.md":
            warnings.append(f"short chapter ({content_chars} chars): {rel}")
        if not re.search(r"^#\s+", text, flags=re.MULTILINE):
            warnings.append(f"no H1 heading: {rel}")
        is_technical = any(part in {"chapters", "examples"} for part in path.parts) and "00-introduction" not in path.parts
        if is_technical and "```kotlin" not in text.lower():
            warnings.append(f"no Kotlin code block: {rel}")
        if is_technical and not re.search(r"```(?:text|ascii)", text, flags=re.IGNORECASE):
            warnings.append(f"no ASCII/text diagram: {rel}")
        errors.extend(check_internal_links(path, text))

    print(f"chapters={len(paths)}")
    print(f"non_whitespace_chars={total_chars}")
    print(f"lines={total_lines}")
    print(f"code_fence_markers={total_fences}")
    if len(paths) < MIN_CHAPTERS:
        errors.append(f"too few chapters: {len(paths)} < {MIN_CHAPTERS}")
    if total_chars < MIN_BOOK_CHARS:
        errors.append(f"book too short: {total_chars} < {MIN_BOOK_CHARS} non-whitespace chars")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
