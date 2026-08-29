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
# 章节总数不再硬编码：以 SUMMARY.md 收录为准（防止增删章节后常量过时），
# 全书体量下限由 MIN_BOOK_CHARS 兜底。
CONTENT_ROOTS = ("chapters", "examples", "appendices")


def chapter_paths() -> list[Path]:
    text = SUMMARY.read_text(encoding="utf-8")
    paths: list[Path] = []
    for raw in LINK_RE.findall(text):
        rel = unquote(raw.split("#", 1)[0])
        paths.append((ROOT / rel).resolve())
    return paths


def orphan_markdown_files(listed: set[Path]) -> list[Path]:
    """返回 content 目录下存在但未被 SUMMARY 收录的 Markdown 文件。"""
    files: list[Path] = []
    for root_name in CONTENT_ROOTS:
        root = ROOT / root_name
        if root.is_dir():
            files.extend(p for p in root.rglob("*.md") if p.is_file())
    return [p for p in files if p not in listed]


def check_internal_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw in INLINE_LINK_RE.findall(text):
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_raw = unquote(raw.split("#", 1)[0])
        if not target_raw:
            continue
        if target_raw.startswith("/"):
            # VitePress 绝对路由（如 /chapters/00-introduction/how-to-read），相对仓库根解析。
            rel = target_raw.lstrip("/")
            if not rel.endswith(".md"):
                rel += ".md"
            target = (ROOT / rel).resolve()
        else:
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

    for orphan in orphan_markdown_files(set(paths)):
        errors.append(
            f"orphan markdown not in SUMMARY: "
            f"{orphan.relative_to(ROOT).as_posix()}"
        )

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
