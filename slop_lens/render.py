"""Bridge to the optional Node render probe (probe/render-probe.mjs).

The core stays dependency-free: if Node.js or playwright-core is missing, SlopLens falls
back to static analysis and says so in the report. When available, the probe renders the
page in a real browser (installed Chrome/Edge, or Playwright's Chromium) and returns
measurements that replace several static heuristics with ground truth.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_DIR = os.path.join(ROOT, "probe")
PROBE = os.path.join(PROBE_DIR, "render-probe.mjs")
_NODE_CANDIDATES = [
    r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe",
    "/usr/local/bin/node", "/opt/homebrew/bin/node", "/usr/bin/node",
]


def find_node():
    p = shutil.which("node")
    if p:
        return p
    for c in _NODE_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def _has_playwright():
    # Node resolves packages from probe/node_modules first, then the repo root (where the
    # root package.json installs them, including Claude Code's automatic plugin install).
    return any(os.path.isdir(os.path.join(d, "node_modules", pkg))
               for d in (PROBE_DIR, ROOT) for pkg in ("playwright-core", "playwright"))


def status():
    node = find_node()
    if not node:
        return {"available": False, "reason": "Node.js 18+ 미설치 → 정적 분석만 수행 (렌더 측정을 쓰려면 Node 설치 후 SlopLens 폴더에서 `npm install`)"}
    if not os.path.isfile(PROBE):
        return {"available": False, "reason": "probe/render-probe.mjs 없음"}
    if not _has_playwright():
        return {"available": False, "node": node, "reason": "렌더 프로브 의존성 미설치 → SlopLens 폴더에서 `npm install` 실행 필요"}
    return {"available": True, "node": node}


def pick_entry(target):
    """Return (root, entry) for a local folder/file the probe should serve."""
    target = os.path.abspath(target)
    if os.path.isfile(target):
        return os.path.dirname(target), os.path.basename(target)
    for cand in ("dist/index.html", "build/index.html", "out/index.html", "index.html", "www/index.html", "public/index.html", "src/index.html"):
        full = os.path.join(target, cand)
        if os.path.isfile(full):
            # serve from the entry's folder: built apps reference /assets/... relative to their own root
            return os.path.dirname(full), "index.html"
    hits = [p for p in glob.glob(os.path.join(target, "*", "index.html")) + glob.glob(os.path.join(target, "*", "*", "index.html"))
            if "node_modules" not in p]
    if hits:
        return target, os.path.relpath(sorted(hits, key=len)[0], target)
    htmls = glob.glob(os.path.join(target, "*.html"))
    if htmls:
        return target, os.path.basename(sorted(htmls)[0])
    return None, None


def run(target, kind="auto", out_dir=None, timeout=240):
    st = status()
    if not st["available"]:
        return {"ok": False, "error": st["reason"], "skipped": True}
    if not out_dir:
        h = hashlib.sha1(f"{target}{time.time()}".encode()).hexdigest()[:8]
        out_dir = os.path.join(tempfile.gettempdir(), "slop-lens", h)
    cmd = [st["node"], PROBE, "--out", out_dir, "--kind", kind]
    if target.lower().startswith(("http://", "https://")):
        cmd += ["--url", target]
    else:
        root, entry = pick_entry(target)
        if not root:
            return {"ok": False, "error": "렌더할 HTML 진입점(index.html)을 찾지 못함 — 빌드 결과물 폴더나 dev 서버 URL로 검사하세요", "skipped": True}
        cmd += ["--root", root, "--entry", entry]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=PROBE_DIR)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"렌더 프로브 시간 초과({timeout}s)"}
    try:
        data = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "렌더 프로브 출력 해석 실패: " + p.stderr.decode("utf-8", "replace")[-300:]}
    data["out_dir"] = out_dir
    return data
