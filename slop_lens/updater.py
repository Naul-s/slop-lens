"""`slop-lens update` — bring this SlopLens install up to date with GitHub main.

Detects how SlopLens was installed and uses that channel's own updater:
  plugin  Claude Code plugin  → `claude plugin marketplace update` + `claude plugin update`
  git     git clone           → `git pull --ff-only`
  gemini  Gemini CLI extension → `gemini extensions update`
After updating, it makes sure the optional browser-probe dependency is installed.
"""
import json
import os
import shutil
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Naul-s/slop-lens"
MARKETPLACE = "slop-lens"
PLUGIN_ID = "slop-lens@slop-lens"


def _run(cmd, log, cwd=None, timeout=300):
    log("$ " + " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"  실패: {e}")
        return 1, ""
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    for line in out.splitlines():
        log("  " + line)
    return p.returncode, out


def _which(name, extra=()):
    p = shutil.which(name)
    if p:
        return p
    for c in extra:
        if os.path.isfile(c):
            return c
    return None


def find_claude():
    home = os.path.expanduser("~")
    return _which("claude", [os.path.join(home, ".local", "bin", n) for n in ("claude.exe", "claude")])


def detect(root=ROOT):
    norm = os.path.abspath(root).replace("\\", "/").lower()
    if "/.claude/plugins/" in norm or os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "plugin"
    if os.path.isdir(os.path.join(root, ".git")):
        return "git"
    if "/.gemini/extensions/" in norm:
        return "gemini"
    return "unknown"


def latest_sha(timeout=10):
    """Commit SHA of GitHub main, or None when offline."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/commits/main",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "slop-lens-updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("sha")
    except Exception:
        return None


def _plugins_root():
    return os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "plugins")


def plugin_installs():
    """Install records for this plugin from Claude Code's installed_plugins.json."""
    try:
        with open(os.path.join(_plugins_root(), "installed_plugins.json"), encoding="utf-8") as f:
            return json.load(f).get("plugins", {}).get(PLUGIN_ID, [])
    except (OSError, ValueError):
        return []


def _git_head(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=30).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def ensure_probe_deps(root, log):
    """Install the browser-probe dependency into `root` when Node is present and it's missing."""
    from . import render
    if not os.path.isfile(os.path.join(root, "package.json")):
        return
    if any(os.path.isdir(os.path.join(d, "node_modules", "playwright-core")) for d in (root, os.path.join(root, "probe"))):
        log("브라우저 측정 모듈: 이미 설치됨")
        return
    if not render.find_node():
        log("브라우저 측정 모듈: Node.js가 없어 건너뜀 (소스 분석만 사용)")
        return
    npm = _which("npm", [r"C:\Program Files\nodejs\npm.cmd"])
    if not npm:
        log("브라우저 측정 모듈: npm을 찾지 못해 건너뜀")
        return
    rc, _ = _run([npm, "install", "--no-audit", "--no-fund"], log, cwd=root)
    log("브라우저 측정 모듈: " + ("설치됨" if rc == 0 else "설치 실패 (소스 분석은 계속 사용 가능)"))


def _short(sha):
    return (sha or "?")[:7]


def update_plugin(log, check=False):
    claude = find_claude()
    if not claude:
        log("Claude Code CLI(`claude`)를 찾지 못했습니다. https://code.claude.com 에서 설치한 뒤 다시 실행하세요.")
        return 1
    before = plugin_installs()
    if not before:
        log(f"{PLUGIN_ID} 설치 기록이 없습니다. 먼저 설치하세요: claude plugin install slop-lens --marketplace {REPO}")
        return 1
    latest = latest_sha()
    for rec in before:
        log(f"현재 ({rec.get('scope')}): {rec.get('version')} · 커밋 {_short(rec.get('gitCommitSha'))}")
    log(f"GitHub 최신: 커밋 {_short(latest)}" if latest else "GitHub 최신 커밋을 확인하지 못했습니다 (오프라인?)")
    if check:
        behind = latest and any(r.get("gitCommitSha") != latest for r in before)
        log("→ 업데이트가 있습니다. `slop-lens update`로 받으세요." if behind else "→ 최신 상태입니다." if latest else "")
        return 0
    rc, _ = _run([claude, "plugin", "marketplace", "update", MARKETPLACE], log)
    if rc != 0:
        log("마켓플레이스를 새로 받지 못했습니다. 네트워크를 확인하세요.")
        return 1
    failed = False
    for scope in sorted({r.get("scope") or "user" for r in before}):
        rc, _ = _run([claude, "plugin", "update", PLUGIN_ID, "--scope", scope], log)
        failed |= rc != 0
    after = plugin_installs()
    for rec in after:
        path = rec.get("installPath")
        if path and os.path.isdir(path):
            ensure_probe_deps(path, log)
    changed = {r.get("gitCommitSha") for r in before} != {r.get("gitCommitSha") for r in after}
    for rec in after:
        log(f"업데이트 후 ({rec.get('scope')}): {rec.get('version')} · 커밋 {_short(rec.get('gitCommitSha'))}")
    if failed:
        return 1
    log("새 버전을 받았습니다. 열려 있는 세션에서는 `/reload-plugins`, 또는 새 세션부터 적용됩니다."
        if changed else "이미 최신 버전입니다.")
    return 0


def update_git(log, root=ROOT, check=False):
    head = _git_head(root)
    latest = latest_sha()
    log(f"현재: 커밋 {_short(head)} · GitHub 최신: 커밋 {_short(latest)}")
    if check:
        log("→ 최신 상태입니다." if head and head == latest else "→ 업데이트가 있습니다. `slop-lens update`로 받으세요." if latest else "")
        return 0
    rc, _ = _run(["git", "-C", root, "pull", "--ff-only"], log, timeout=180)
    if rc != 0:
        log("자동으로 합칠 수 없습니다. 이 폴더에서 직접 고친 내용이 있으면 정리한 뒤 다시 실행하세요.")
        return 1
    new = _git_head(root)
    if os.path.isdir(os.path.join(root, "node_modules")) or os.path.isdir(os.path.join(root, "probe", "node_modules")):
        ensure_probe_deps(root, log)
    log(f"업데이트 완료: {_short(head)} → {_short(new)}" if new != head else "이미 최신 버전입니다.")
    return 0


def update_gemini(log, check=False):
    gemini = _which("gemini")
    if not gemini:
        log("Gemini CLI를 찾지 못했습니다. `gemini extensions update slop-lens`를 직접 실행하세요.")
        return 1
    if check:
        log(f"GitHub 최신: 커밋 {_short(latest_sha())}")
        return 0
    rc, _ = _run([gemini, "extensions", "update", "slop-lens"], log)
    return 0 if rc == 0 else 1


def run(mode="auto", check=False, log=print):
    mode = detect() if mode == "auto" else mode
    log(f"SlopLens 설치 방식: {mode} ({ROOT})")
    if mode == "plugin":
        return update_plugin(log, check)
    if mode == "git":
        return update_git(log, check=check)
    if mode == "gemini":
        return update_gemini(log, check)
    log("자동 업데이트할 수 없는 설치입니다 (zip 다운로드 등). 아래처럼 다시 설치하면 이후부터 자동 업데이트됩니다:\n"
        f"  Claude Code: claude plugin install slop-lens --marketplace {REPO}\n"
        f"  그 외: git clone https://github.com/{REPO}.git")
    return 1
