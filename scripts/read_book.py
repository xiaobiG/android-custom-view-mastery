from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_book"
INDEX = OUTPUT / "index.html"


def newest_source_mtime() -> float:
    files: list[Path] = list(ROOT.glob("*.md"))
    roots = [
        ROOT / "book.json",
        ROOT / "chapters",
        ROOT / "examples",
        ROOT / "appendices",
        ROOT / "assets",
    ]
    for item in roots:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(p for p in item.rglob("*") if p.is_file())
    return max((p.stat().st_mtime for p in files), default=0.0)


def ensure_book() -> None:
    if INDEX.exists() and INDEX.stat().st_mtime >= newest_source_mtime():
        return

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise SystemExit("未找到 npm。请先安装 Node.js 18 或更高版本。")

    if not (ROOT / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=ROOT, check=True)
    subprocess.run([npm, "run", "check"], cwd=ROOT, check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and read the HonKit book")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    ensure_book()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(OUTPUT),
    )

    try:
        server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        print(f"无法监听 {args.host}:{args.port}：{exc}", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}/"
    print(f"GitBook 已就绪：{url}", flush=True)
    print("按 Ctrl+C 停止服务。", flush=True)

    if not args.no_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n阅读服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
