from __future__ import annotations

import concurrent.futures
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "SUMMARY.md"
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SUMMARY_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)")
USER_AGENT = "Mozilla/5.0 (compatible; book-link-check/1.0)"
TIMEOUT = 5.0
MAX_WORKERS = 8
RETRIES = 1
# 已知会拦截机器人或需要登录的域名：跳过精确匹配，避免误报。
SKIP_HOSTS = {"docs.qq.com", "github.com"}


def chapter_files() -> list[Path]:
    text = SUMMARY.read_text(encoding="utf-8")
    paths: list[Path] = []
    for raw in SUMMARY_LINK_RE.findall(text):
        rel = raw.split("#", 1)[0]
        p = (ROOT / rel).resolve()
        if p.exists():
            paths.append(p)
    return paths


def collect_links() -> list[tuple[Path, str, str]]:
    links: list[tuple[Path, str, str]] = []
    for path in chapter_files():
        text = path.read_text(encoding="utf-8")
        for label, raw in LINK_RE.findall(text):
            url = raw.strip()
            if not url.startswith(("http://", "https://")):
                continue
            links.append((path, label, url))
    return links


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc.lower()
    except ValueError:
        return ""


def fetch_get(url: str) -> tuple[str, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return "OK", resp.geturl(), f"GET {resp.status}"
    except urllib.error.HTTPError as exc:
        return "ERROR" if exc.code in (404, 410) else "WARN", url, f"GET HTTP {exc.code}"
    except Exception as exc:
        return "WARN", url, f"GET network: {type(exc).__name__}"


def fetch_status(url: str) -> tuple[str, str, str]:
    """返回 (分类, 终态URL, 说明)。分类: OK / ERROR / WARN"""
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return "OK", resp.geturl(), f"HEAD {resp.status}"
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code in (404, 410):
                return "ERROR", url, f"HEAD HTTP {code}"
            if code in (403, 405):
                return fetch_get(url)
            if attempt >= RETRIES:
                return "WARN", url, f"HEAD HTTP {code}"
        except Exception as exc:
            if attempt >= RETRIES:
                return "WARN", url, f"network: {type(exc).__name__}"
    return "WARN", url, "unresolved"


def main() -> int:
    links = collect_links()
    errors: list[str] = []
    warns: list[str] = []
    ok = 0
    skipped = 0

    def run(item: tuple[Path, str, str]) -> tuple[Path, str, str, tuple[str, str, str]]:
        path, label, url = item
        if host_of(url) in SKIP_HOSTS:
            return path, label, url, ("OK", url, "skipped")
        return path, label, url, fetch_status(url)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(run, links))

    for path, label, url, (status, final, note) in results:
        rel = path.relative_to(ROOT)
        if status == "OK":
            ok += 1
            if note != "skipped" and host_of(final) != host_of(url):
                warns.append(f"{rel}: 跨域重定向 {url} -> {final}（链接文字: {label}）")
            continue
        skipped += 1 if note == "skipped" else 0
        if status == "ERROR":
            errors.append(f"{rel}: {url}（{label}）{note}")
        else:
            warns.append(f"{rel}: {url}（{label}）{note}")

    print(
        f"external_links={len(links)} ok={ok} "
        f"errors={len(errors)} warnings={len(warns)}"
    )
    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"LINK CHECK FAILED: {len(errors)} broken link(s)")
        return 1
    print("LINK CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
