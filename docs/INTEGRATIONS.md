# 에이전트별 연결 방법

> 가장 쉬운 방법: `python scripts/install.py` — 현재 설치 위치의 절대 경로가 채워진 명령을 에이전트별로 출력한다 (아무것도 변경하지 않음).
> 아래의 `/ABS/PATH/slop-lens`는 실제 경로로, macOS/Linux에서는 `python`을 `python3`로 바꾼다.

## 렌더 실측 켜기 (모든 에이전트 공통, 선택)

```bash
# Node.js 18+ 설치 후 (Windows: winget install OpenJS.NodeJS.LTS / macOS: brew install node)
npm install --prefix /ABS/PATH/slop-lens/probe
# Chrome·Edge가 없는 서버/CI라면:
npx --prefix /ABS/PATH/slop-lens/probe playwright-core install --with-deps chromium
python /ABS/PATH/slop-lens/bin/slop-lens.py doctor     # "렌더 프로브: 사용 가능" 확인
```
설치하면 `slop_scan`이 자동으로(render: "auto") 실제 브라우저 측정과 스크린샷을 추가한다. 한 번 검사에 15~60초 걸리므로,
MCP 클라이언트의 도구 타임아웃은 120초 이상을 권장한다 (Codex 예시 설정에 반영됨).

## Claude Code

**플러그인 (권장)** — MCP 서버 + 스킬 + `/slop-check`, `/slop-fix` 명령 + `slop-auditor` 서브에이전트가 한 번에 설치된다.
```
/plugin marketplace add /ABS/PATH/slop-lens
/plugin install slop-lens@slop-lens
```
Git 저장소로 올렸다면 `/plugin marketplace add <owner>/<repo>`.

**MCP만**
```bash
claude mcp add slop-lens --scope user -- python /ABS/PATH/slop-lens/bin/slop-lens-mcp.py
```

## OpenAI Codex CLI

```bash
codex mcp add slop-lens -- python /ABS/PATH/slop-lens/bin/slop-lens-mcp.py
python /ABS/PATH/slop-lens/scripts/install.py --skill codex   # 선택: ~/.codex/skills/slop-lens 설치
```
또는 `~/.codex/config.toml`에 [integrations/codex/config.toml](../integrations/codex/config.toml) 내용을 추가.
프로젝트 루트의 `AGENTS.md`에 "UI/게임 작업 후 slop_scan 실행" 같은 규칙을 적어두면 Codex가 자동으로 따른다.

## Gemini CLI

**확장 (권장)** — MCP 서버 + `GEMINI.md` 컨텍스트 + `/slop-check`, `/slop-fix` 명령.
```bash
gemini extensions link /ABS/PATH/slop-lens      # 개발용 링크
gemini extensions install <git-url>             # 저장소로 배포 시
```
**MCP만**: `gemini mcp add slop-lens python /ABS/PATH/slop-lens/bin/slop-lens-mcp.py`

## Cursor

`~/.cursor/mcp.json`(전역) 또는 `.cursor/mcp.json`(프로젝트)에 [integrations/cursor/mcp.json](../integrations/cursor/mcp.json).

## VS Code (GitHub Copilot Agent mode)

`.vscode/mcp.json`에 [integrations/vscode/mcp.json](../integrations/vscode/mcp.json) (`servers` 키 형식).

## Windsurf · Cline · Claude Desktop · Zed · Goose · 기타 MCP 클라이언트

`mcpServers` 형식: [integrations/generic/mcp.json](../integrations/generic/mcp.json).

## MCP를 지원하지 않는 에이전트 · CI

```bash
python /ABS/PATH/slop-lens/bin/slop-lens.py scan ./my-site                 # 마크다운 리포트
python /ABS/PATH/slop-lens/bin/slop-lens.py scan ./my-site --format json   # 기계 판독
python /ABS/PATH/slop-lens/bin/slop-lens.py scan ./my-site --format html --out report.html
python /ABS/PATH/slop-lens/bin/slop-lens.py brief ./my-site               # 리디자인 브리프만 (게임은 리뷰 전이면 --reveal 필요)
python /ABS/PATH/slop-lens/bin/slop-lens.py scan ./my-site --fail-over 40  # CI 게이트 (초과 시 exit 1)
```

GitHub Actions 예:
```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: python tools/slop-lens/bin/slop-lens.py scan . --fail-over 40 --format md --out slop-report.md
```

## 시각 검토를 자동화하려면

정적 분석만으로도 판정은 나오지만, 이미지 아티팩트·시선 초점·실제 클릭 경험은 화면을 봐야 한다.
에이전트에 브라우저 도구(Playwright MCP, Chrome DevTools MCP, 내장 브라우저 등)가 있으면 스킬이 자동으로
`slop_visual_rubric` → 스크린샷 판정 → `slop_submit_visual_review` 순서로 진행한다.
CLI에서는 답변 파일로 합칠 수 있다:

```json
{ "answers": [ { "id": "VR-03", "answer": "yes", "note": "hero 인물 손가락 6개" },
               { "id": "VR-11", "answer": "partial", "note": "Pricing 링크만 동작" } ] }
```
```bash
python bin/slop-lens.py scan ./my-site --visual answers.json
```
