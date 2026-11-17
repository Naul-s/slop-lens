#!/usr/bin/env python3
"""Print (or apply) the exact commands to connect SlopLens to each agent.

  python scripts/install.py                 # print instructions for every agent (changes nothing)
  python scripts/install.py --skill codex   # copy the Agent Skill into ~/.codex/skills/slop-lens
  python scripts/install.py --skill claude  # copy into ~/.claude/skills/slop-lens
  python scripts/install.py --skill gemini  # copy into ~/.gemini/skills/slop-lens
  python scripts/install.py --skill agents  # copy into ~/.agents/skills/slop-lens (shared skills dir)

Only --skill writes files, and only inside the chosen skills folder.
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP = os.path.join(ROOT, "bin", "slop-lens-mcp.py")
CLI = os.path.join(ROOT, "bin", "slop-lens.py")
PY = "python" if os.name == "nt" else "python3"

SKILL_DIRS = {
    "codex": os.path.join("~", ".codex", "skills"),
    "claude": os.path.join("~", ".claude", "skills"),
    "gemini": os.path.join("~", ".gemini", "skills"),
    "agents": os.path.join("~", ".agents", "skills"),
}


def q(p):
    return f'"{p}"' if " " in p else p


def instructions():
    m = q(MCP)
    return f"""
SlopLens 위치: {ROOT}
Python: {sys.version.split()[0]} (정적 분석: 의존성 없음)
렌더 프로브: {probe_line()}

━━ (선택) 렌더 실측 켜기 — 실제 브라우저로 색·대비·클릭·모바일·게임 런타임 측정 ━━
      Node.js 18+ 설치 후:
      npm install --prefix {q(os.path.join(ROOT, 'probe'))}
      (Chrome/Edge가 없으면) npx --prefix {q(os.path.join(ROOT, 'probe'))} playwright-core install chromium
      {PY} {q(CLI)} doctor

━━ Claude Code ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  (A) 플러그인으로 (스킬 + /slop-check, /slop-fix + 서브에이전트 + MCP 전부)
      /plugin marketplace add {ROOT}
      /plugin install slop-lens@slop-lens
  (B) MCP만
      claude mcp add slop-lens --scope user -- {PY} {m}

━━ OpenAI Codex CLI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      codex mcp add slop-lens -- {PY} {m}
      {PY} {q(os.path.join(ROOT, 'scripts', 'install.py'))} --skill codex     # 스킬 설치(선택)
  (또는 ~/.codex/config.toml 에 integrations/codex/config.toml 내용 추가)

━━ Gemini CLI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  (A) 확장으로 (MCP + GEMINI.md + /slop-check, /slop-fix)
      gemini extensions link {ROOT}
  (B) MCP만
      gemini mcp add slop-lens {PY} {m}

━━ Cursor / VS Code(Copilot) / Windsurf / Cline / Claude Desktop / Zed ━━
  integrations/ 폴더의 mcp.json 을 각 클라이언트 설정에 붙여 넣고 경로를 아래로 바꾸세요:
      command: {PY}
      args:    ["{MCP.replace(chr(92), '/')}"]

━━ MCP를 지원하지 않는 에이전트 / CI ━━━━━━━━━━━━━━━━━━━━━━━━━━
      {PY} {q(CLI)} scan <폴더|URL>
      {PY} {q(CLI)} scan <폴더> --fail-over 40      # CI 게이트
  프로젝트 AGENTS.md 에 위 명령을 적어두면 대부분의 에이전트가 따라 실행합니다.
"""


def probe_line():
    sys.path.insert(0, ROOT)
    try:
        from slop_lens import render
        st = render.status()
        return "사용 가능" if st["available"] else "꺼짐 — " + st["reason"]
    except Exception as e:  # pragma: no cover
        return f"확인 실패 ({e})"


def install_skill(target):
    dest_root = os.path.expanduser(SKILL_DIRS[target])
    dest = os.path.join(dest_root, "slop-lens")
    src = os.path.join(ROOT, "skills", "slop-lens")
    if os.path.exists(dest):
        print(f"이미 존재합니다: {dest}  (덮어쓰지 않음. 지우고 다시 실행하세요)")
        return 1
    shutil.copytree(src, dest)
    home = ROOT.replace("\\", "/")
    p = os.path.join(dest, "SKILL.md")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    with open(p, "w", encoding="utf-8") as f:
        f.write(s.replace("{{SLOP_LENS_HOME}}", home))
    print(f"스킬 설치 완료: {dest}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", choices=list(SKILL_DIRS))
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if a.skill:
        return install_skill(a.skill)
    print(instructions())
    return 0


if __name__ == "__main__":
    sys.exit(main())
