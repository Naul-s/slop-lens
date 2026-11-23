# SlopLens

Explains why an AI-made website or game feels like "AI slop", with evidence and fixes.

[한국어](#한국어)

> [!NOTE]
> SlopLens is a reference tool, not an authoritative AI-slop detector.

## Features

- Finds the causes of a low-effort feel: default palettes, unedited AI images, repeated sound effects, stock UI and copy.
- Backs every finding with a file location, screenshot or measurement.
- Orders fixes by impact and effort.
- Works as a Claude Code plugin, an MCP server and a CLI.

## Install

Requires Python 3.9+.

**Claude Code**

```text
/plugin marketplace add Naul-s/slop-lens
/plugin install slop-lens@slop-lens
```

Or from a shell:

```bash
claude plugin install slop-lens --marketplace Naul-s/slop-lens
```

In the desktop app's Code tab, add the marketplace as above, then **+** → **Add plugins** → **slop-lens**.

**Other agents (MCP)**

```bash
git clone https://github.com/Naul-s/slop-lens.git
```

| Agent | Setup |
|---|---|
| Claude desktop app (Chat tab) | Paste [`integrations/generic/mcp.json`](integrations/generic/mcp.json) into Settings → Developer → Edit Config |
| Gemini CLI | `gemini extensions install https://github.com/Naul-s/slop-lens` |
| Codex CLI | `codex mcp add slop-lens -- python <path>/bin/slop-lens-mcp.py` |
| Cursor, VS Code, Windsurf | See [`integrations/`](integrations) |

**Browser measurement (optional)**

Needs Node 18+ and Chrome or Edge. The Claude Code plugin sets it up automatically; for a clone, run `npm install`. Check with `python bin/slop-lens.py doctor`.

## Usage

Ask your agent: *"Does this look like AI slop?"*

```bash
python bin/slop-lens.py scan ./my-site
python bin/slop-lens.py scan http://localhost:5173
python bin/slop-lens.py scan ./my-game --kind game
python bin/slop-lens.py unity-capture ./my-unity-project
```

- Games are judged by a review of the screens. Measurements stay hidden until the review is submitted.
- `unity-capture` builds and plays a copy of the project. The original is not modified.

## Update

```text
/slop-lens:update
```

```bash
python bin/slop-lens.py update [--check]
```

Then run `/reload-plugins` or start a new session.

## Safety

Scanned pages are treated as untrusted.

- Chromium runs sandboxed. `SLOP_LENS_NO_SANDBOX=1` disables this for containers.
- On non-local hosts, automated play only touches the game canvas and Play buttons.
- After input starts, outgoing POST/PUT/PATCH/DELETE requests and new WebSockets are blocked. State changes made over GET are not.
- The preview server only serves the target folder, excluding dot files and keys. Pages can read the rest of that folder.

## Accuracy

| | |
|---|---|
| Websites | First-pass check. AUC 0.83 on 20 held-out sites. |
| Games | Needs a screen review. AI-trace score: AUC 0.73 on 20 held-out games. |
| Reviews | Not yet validated against human raters. |
| Fixes | Effect not yet measured. |

See [docs/VALIDATION.md](docs/VALIDATION.md).

## Docs

[Criteria](docs/CRITERIA.md) · [Architecture](docs/ARCHITECTURE.md) · [Integrations](docs/INTEGRATIONS.md) · [Validation](docs/VALIDATION.md) · [Research](docs/RESEARCH.md) (Korean)

## License

MIT

---

## 한국어

AI로 만든 웹사이트·게임이 왜 "AI 슬롭"처럼 느껴지는지 근거와 해결책으로 설명합니다.

> [!NOTE]
> 참고용 도구이며, AI 슬롭을 판정하는 절대 기준이 아닙니다.

### 기능

- 대충 만든 느낌의 원인을 찾습니다: 기본 배색, 다듬지 않은 AI 이미지, 반복되는 효과음, 기본 UI와 상투 문구.
- 모든 지적에 파일 위치·스크린샷·측정값을 붙입니다.
- 효과와 작업량 순으로 수정 순서를 제안합니다.
- Claude Code 플러그인, MCP 서버, CLI로 쓸 수 있습니다.

### 설치

Python 3.9 이상이 필요합니다.

- **Claude Code:** `/plugin marketplace add Naul-s/slop-lens` → `/plugin install slop-lens@slop-lens`
- **데스크톱 앱 Code 탭:** 위처럼 마켓플레이스를 추가한 뒤 **+** → **Add plugins** → **slop-lens**
- **다른 에이전트(MCP):** 저장소를 클론하고 위 [Install](#install) 표를 따릅니다.
- **브라우저 측정(선택):** Node 18 이상과 Chrome·Edge가 필요합니다. 플러그인은 자동 설치되고, 클론했다면 `npm install`을 실행합니다. 확인은 `python bin/slop-lens.py doctor`.

### 사용

에이전트에게 *"이거 AI 슬롭처럼 보이는지 봐줘"*라고 요청합니다. CLI 명령은 위 [Usage](#usage)를 참고하세요.

- 게임은 화면 리뷰로 판정하며, 리뷰를 제출하기 전에는 측정 결과를 보여 주지 않습니다.
- `unity-capture`는 프로젝트 복사본을 빌드해 플레이합니다. 원본은 바뀌지 않습니다.

### 업데이트

`/slop-lens:update` 또는 `python bin/slop-lens.py update [--check]`. 이후 `/reload-plugins`를 실행하거나 새 세션을 엽니다.

### 안전

검사하는 페이지는 신뢰하지 않는 것으로 다룹니다.

- 브라우저를 샌드박스에서 실행합니다. 컨테이너에서는 `SLOP_LENS_NO_SANDBOX=1`로 끌 수 있습니다.
- 로컬이 아닌 사이트에서는 게임 캔버스와 시작 버튼만 조작합니다.
- 자동 조작이 시작되면 외부로 나가는 POST/PUT/PATCH/DELETE 요청과 새 WebSocket을 막습니다. GET으로 일어나는 상태 변경은 막지 못합니다.
- 미리보기 서버는 대상 폴더만 열며, 숨김 파일과 키 파일은 제외합니다. 그 폴더의 나머지 파일은 페이지가 읽을 수 있습니다.

### 정확도

| | |
|---|---|
| 웹사이트 | 1차 점검용. 처음 보는 사이트 20개에서 AUC 0.83 |
| 게임 | 화면 리뷰 필요. AI 제작 흔적 점수: 처음 보는 게임 20개에서 AUC 0.73 |
| 리뷰 | 사람 평가자 기준 검증 전 |
| 해결책 | 효과 측정 전 |

자세한 내용은 [docs/VALIDATION.md](docs/VALIDATION.md)에 있습니다.
