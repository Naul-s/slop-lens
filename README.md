# SlopLens

An agent plugin & skill that finds **why an AI-made website or game feels like "AI slop"** — and shows the evidence and how to fix it.

[한국어 설명은 아래에 있습니다 ↓](#한국어)

> [!IMPORTANT]
> This is **not an authoritative AI-slop detector.** People make the call; SlopLens gives reference evidence and suggested fixes.

## What it does

- **Causes** — spots what makes work feel low-effort: purple gradients, raw AI-generated images, the same beep for every sound, default engine UI, cliché copy.
- **Evidence** — every finding comes with a file location, screenshot, or measurement.
- **Fixes** — suggests what to fix first and how.

## Install

Requires Python 3.9+. This repository is its own plugin marketplace (`slop-lens`); it is not listed in Anthropic's official marketplace yet.

**Claude Code — terminal · VS Code**

```text
/plugin marketplace add Naul-s/slop-lens
/plugin install slop-lens@slop-lens
```

Or from your shell in one step:

```bash
claude plugin install slop-lens --marketplace Naul-s/slop-lens
```

**Claude desktop app — Code tab**

1. Add the marketplace once with the shell command above. The terminal, VS Code and the desktop app share the same plugin settings.
2. In the Code tab, click **+** next to the prompt box → **Add plugins** (or **Plugins → Browse plugins**) → select **slop-lens**.

**Other agents (MCP)** — clone the repo first: `git clone https://github.com/Naul-s/slop-lens.git`

| Agent | Setup |
|---|---|
| Claude desktop app — Chat tab | Settings → Developer → Edit Config, paste [`integrations/generic/mcp.json`](integrations/generic/mcp.json), restart |
| Gemini CLI | `gemini extensions install https://github.com/Naul-s/slop-lens` |
| Codex CLI | `codex mcp add slop-lens -- python <path>/bin/slop-lens-mcp.py` |
| Cursor · VS Code · Windsurf, etc. | `mcp.json` in [`integrations/`](integrations) |

Replace `/ABS/PATH` or `<path>` with the folder you cloned into.

**Optional: real-browser measurement** (Node 18+, uses your installed Chrome or Edge). Without it, scans read the source only.

```bash
npm install --prefix probe                                              # cloned repo
npm install --prefix ~/.claude/plugins/cache/slop-lens/slop-lens/0.4.0/probe   # Claude Code plugin
```

## Usage

Inside an agent, just ask: **"Does this look like AI slop?"**

Or run it directly:

```bash
python bin/slop-lens.py scan ./my-site              # folder
python bin/slop-lens.py scan http://localhost:5173  # URL
python bin/slop-lens.py scan ./my-game --kind game  # game
```

## How far can you trust it?

| | |
|---|---|
| Websites | Useful as a first-pass check |
| Games | Measurements alone can't decide → a review of the actual screens is required |
| Fixes | Evidence is checkable; real-world effect is still being validated |

Details: [docs/VALIDATION.md](docs/VALIDATION.md)

## Feedback

Wrong verdicts, missed slop signals, results after applying fixes — please open an [issue](https://github.com/Naul-s/slop-lens/issues).

## Docs (Korean)

[Criteria](docs/CRITERIA.md) · [Architecture](docs/ARCHITECTURE.md) · [Integrations](docs/INTEGRATIONS.md) · [Validation](docs/VALIDATION.md)

## License

MIT

---

## 한국어

AI로 만든 웹사이트·게임이 **왜 "AI 슬롭"처럼 보이는지** 찾아서, 근거와 해결책을 알려주는 에이전트 플러그인·스킬입니다.

> [!IMPORTANT]
> AI 슬롭을 판정하는 **절대적인 기준이 아닙니다.** 판단은 사람이 하고, 이 도구는 참고용 근거와 해결책을 제공합니다.

**무엇을 해주나요**

- **원인** — 보라 그라디언트, 다듬지 않은 생성 이미지, 똑같은 비프 효과음, 엔진 기본 UI, 상투 문구 같은 "대충 만든 느낌"의 원인을 찾습니다.
- **근거** — 각 지적마다 파일 위치·화면·측정값을 함께 보여줍니다.
- **해결** — 무엇부터 고치면 좋은지 순서와 방법을 제안합니다.

**설치** — Python 3.9+가 필요합니다. 이 리포 자체가 플러그인 마켓플레이스(`slop-lens`)이며, Anthropic 공식 마켓플레이스에는 아직 등록되어 있지 않습니다.

- **Claude Code (터미널 · VS Code)** — 세션에서 `/plugin marketplace add Naul-s/slop-lens` → `/plugin install slop-lens@slop-lens`
  또는 셸에서 한 번에: `claude plugin install slop-lens --marketplace Naul-s/slop-lens`
- **Claude 데스크탑 앱 (Code 탭)**
  1. 위 셸 명령으로 마켓플레이스를 한 번 추가합니다. 터미널·VS Code·데스크탑 앱은 같은 플러그인 설정을 씁니다.
  2. Code 탭 입력창 옆 **+** → **Add plugins** (또는 **Plugins → Browse plugins**) → **slop-lens** 선택
- **Claude 데스크탑 앱 (Chat 탭)** — 리포를 클론한 뒤 설정 → 개발자 → 구성 편집에서 [`integrations/generic/mcp.json`](integrations/generic/mcp.json) 내용을 붙여 넣고 앱을 다시 시작합니다.
- **Gemini · Codex · Cursor 등** — 위 [Install](#install) 표를 참고하세요.
- **선택: 실제 브라우저 측정** — Node 18+와 설치된 Chrome·Edge를 씁니다. 없으면 소스만 읽고 판정합니다. 명령은 위 [Install](#install) 끝에 있습니다.

**사용** — 에이전트 안에서 **"이거 AI 슬롭처럼 보이는지 봐줘"** 라고 말하면 됩니다. 직접 실행하려면 위 [Usage](#usage) 명령을 쓰세요.

**얼마나 믿어도 되나요**

| | |
|---|---|
| 웹사이트 | 1차 점검용으로 쓸 만함 |
| 게임 | 측정만으로는 판단 불가 → 화면을 직접 본 리뷰가 있어야 판정 |
| 해결책 | 근거는 확인 가능, 실제 효과는 아직 검증 중 |

**의견 보내기** — 틀린 판정, 놓친 슬롭 신호, 해결책 후기를 [이슈](https://github.com/Naul-s/slop-lens/issues)로 알려주세요.
