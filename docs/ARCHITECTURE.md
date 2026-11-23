# SlopLens 아키텍처

## v0.3 — 지각 우선 구조 (왜 바꿨나)

v0.2까지는 "코드에 AI 기본값 패턴이 있는가"를 셌다. 실제 결과물로 검증해 보니 정반대 결과가 나왔다.
- 비공개 사용자 게임 3개(웹 3D 1, Unity 2): 사용자가 명백한 AI 슬롭으로 보는데 낮은 점수 (코드는 깔끔함)
- Stripe: 누가 봐도 공들인 사이트인데 최고 점수 (AI가 흉내 내는 원본이라 패턴이 겹침)

사람은 **보이는 것과 들리는 것**으로 슬롭을 느낀다. 그래서 4단계로 바꿨다.

```
 수집(Capture)            지각 측정(Perceive)                 판단(Judge)                    설명·해결(Explain)
 ─────────────            ───────────────────                 ───────────                    ─────────────────
 웹: 브라우저 렌더·플레이   사운드: 단음 비프? 변주? 무음 비율?   리뷰어(에이전트/사람)가 시트를    "왜 AI 슬롭으로 느껴지나"
     + Web Audio 녹음      에셋: 가짜 픽셀아트, 스타일 혼재      보고 감각별 레벨·근거·이유·해결   느낌 → 근거 → 해결
 Unity: CLI 복사본 빌드 →  Unity: TMP 기본 폰트, Arial,          S1 첫인상 … S8 실체             + 수정 계획 + 브리프
     자동 플레이 캡처       기본 UI 스킨, 기본 도형, FMOD 이벤트    C1 공들인 흔적(반대 증거)
     (프레임·믹스 녹음)     공들인 흔적: 커스텀 폰트·모션 곡선·    → 확정 = 0.65 리뷰 + 0.35 측정
 에셋: 이미지·사운드 파일    일러스트·OpenType (웹)                리뷰 없음 → '잠정'
 → 화면 시트·에셋 시트
```

| 구성 요소 | 파일 |
|---|---|
| 사운드·이미지 지각 라이브러리 (브라우저 안에서 실행) | `probe/analysis-lib.js` |
| 에셋 지각 분석 + 리뷰용 시트 생성 | `probe/perceive.mjs`, `slop_lens/perceive.py` |
| 웹 런타임 사운드 녹음·구성 분석, 공들인 흔적 실측 | `probe/render-probe.mjs` |
| Unity 캡처 패키지 (런타임 녹화·녹음·텍스트/폰트 수집, CLI 빌드) | `unity/com.sloplens.capture/` |
| Unity 어댑터 (복사본 빌드·실행, OS 입력, YAML·FMOD 분석) | `slop_lens/unity.py` |
| 지각 규칙 AUD-/ART-/UNI- | `slop_lens/rules/perception.py` |
| 지각 리뷰 프로토콜·점수 | `slop_lens/review.py` |

Unity 캡처는 사용자의 원본 프로젝트를 절대 수정하지 않는다. 임시 폴더에 복사본(Library 제외)을 만든다.
패키지는 복사본의 manifest에만 추가한다. 키 입력은 게임 창이 맨 앞일 때만 보내고, 녹음하는 동안 스피커는 음소거한다.

## 설계 목표

1. **어떤 에이전트에도 꽂힌다** — Claude Code, Codex, Gemini CLI, Cursor, VS Code Copilot, Windsurf, Cline, Claude Desktop…
2. **설치 장벽 0, 정확도는 선택적으로** — 코어는 Python 3.9+ 표준 라이브러리만 사용한다. Node가 있으면 렌더 프로브가 추정을 실측으로 바꾼다.
3. **판정은 결정적(deterministic), 해석은 에이전트가** — 같은 입력이면 같은 점수. LLM은 시각 검토와 설명·수정에만 쓴다.
4. **기준이 곧 문서** — 규칙 레지스트리에서 문서(CRITERIA.md)를 자동 생성해 문서와 검사가 어긋나지 않는다.

## 계층 구조

```
┌──────────────────────────── 에이전트 어댑터 (얇은 껍데기) ─────────────────────────────┐
│ Claude Code 플러그인        Gemini CLI 확장          Codex / Cursor / VS Code / 기타    │
│ .claude-plugin/plugin.json  gemini-extension.json    integrations/*/  AGENTS.md         │
│ skills/ commands/*.md       GEMINI.md commands/*.toml                                    │
│ agents/slop-auditor.md                                                                   │
└───────────────┬──────────────────────────┬──────────────────────────────┬───────────────┘
                │ MCP (stdio JSON-RPC)     │ Agent Skill (SKILL.md)       │ CLI (MCP 미지원/CI)
┌───────────────▼──────────────────────────▼──────────────────────────────▼───────────────┐
│ 인터페이스   slop_lens/mcp_server.py (의존성 0)        slop_lens/cli.py                   │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 엔진        engine.py   스캔 → 규칙 실행 → Finding → 점수 → 수정 계획 → 브리프             │
│             scoring.py  영역 점수 · Slop Index · 2축 · 지각 요인 · 시각 검토 블렌딩 · 신뢰도│
│             report.py   Markdown / JSON / HTML                                            │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 판정 기준    rules/*.py   정적 규칙 61개 (visual·layout·copy·imagery·ux·code·game·gametech·a11y)│
│             rubric.py    시각 검토 루브릭 22개 (멀티모달 에이전트가 화면을 보고 판정)       │
│             lexicon.py   EN/KO 상투어, 가짜 이름, 정형 섹션, 범용 CTA·헤드라인 패턴         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ 수집        context.py   폴더·단일 파일·URL → SourceFile(역할: markup/style/script/engine)  │
│             textextract.py 보이는 텍스트·제목·버튼·이미지 alt 추출 (HTML/JSX/Vue/Svelte)   │
│             images.py    PNG/JPEG/WebP/GIF 해상도 + 생성기 메타데이터(C2PA, SD params…)   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## 렌더 실측 계층 (선택)

```
Python engine ──subprocess──► node probe/render-probe.mjs ──► Chrome/Edge(headless, Playwright)
                                   │  로컬 폴더는 내장 정적 서버로 서빙, URL은 그대로 방문
                                   │  addInitScript 계측: rAF·setInterval·Canvas 2D/WebGL 드로우콜·
                                   │  globalAlpha·shadowBlur·AudioContext/Audio.play·alert/confirm
                                   ├─ 데스크톱 1440px: 계산된 스타일·대비·카드 행·폰트, Tab 포커스, 스크린샷
                                   ├─ 클릭 테스트: 버튼/링크를 하나씩 눌러 DOM 변화·URL·네트워크·팝업 관측
                                   ├─ 게임: 8초 무작위 입력 플레이 → 프레임·오디오·드로우콜·픽셀 팔레트·새로고침
                                   └─ 모바일 390px: viewport·가로 넘침·터치 영역, 스크린샷
                              ◄── JSON 1개 (실패 시 {ok:false,error})
```

- **의존성 격리**: Python 코어는 여전히 의존성 0. Node·playwright-core는 `probe/`에만 있고, 없으면 `render.status()`가 이유를 돌려주고 정적 분석만 수행한다.
- **브라우저**: 설치된 Chrome → Edge → Playwright Chromium 순으로 시도하므로 대부분의 PC에서 브라우저 다운로드가 필요 없다.
- **대체(supersede) 규칙**: 실측 규칙은 `replaces=[정적 규칙]`를 선언한다. 결과가
  `Result`면 문제를 실측으로 보고하고 정적 규칙을 버린다. `CLEAN`이면 측정상 문제가 없으므로 정적 추정(오탐 가능)을 버린다.
  `None`이면 측정 불가로 정적 결과를 유지한다. 무작위 플레이에서 재현되지 않을 수 있는 항목(alert 게임오버 등)은 `clean_supersedes=False`로 정적 증거를 유지한다.
- **URL/SPA**: URL 검사 시 렌더링된 DOM으로 컨텍스트를 다시 만들어 JS로 그려지는 페이지도 카피·구조 규칙이 동작한다.

## 안전·신뢰 경계

| 경계 | 담당 | 규칙 |
|---|---|---|
| 브라우저 ↔ OS | `probe/safety.mjs` `launchBrowser` | 샌드박스 켬 |
| 페이지 ↔ 파일 | `serveDirs` | 대상 폴더 안의 파일만, 숨김·키 파일 제외, Host 검사 |
| 자동 입력 ↔ 외부 서비스 | `inputPolicy`, `guardContext` | 캔버스·시작 버튼만, 변경 요청 차단 |
| 대상의 글자 ↔ 리뷰 에이전트 | `review.one_line` | 한 줄 데이터로만 인용 |
| 측정 ↔ 리뷰어 | `report.needs_blind`, `ScanResult.revealed` | 완전한 리뷰 전에는 비공개, 공개 뒤 리뷰는 비블라인드 |
| MCP ↔ 자식 프로세스 | `slop_lens/proc.py` | stdin 상속 안 함, 취소 시 트리 종료 |

새 자동 입력은 반드시 `inputPolicy`를 거치고, 새 자식 프로세스는 `proc.run`으로 띄운다.

## 판정 파이프라인

```
target ──► build_context ──► detect_kind(web|game) ──► 규칙 실행(해당 kind만)
                                                         │   Result(count, evidence[file:line], detail)
                                                         ▼
                                    strength = f(count, threshold, saturation)   (0.4→1.0)
                                                         ▼
               Finding(rule, strength, evidence)  ──►  영역 점수 / Slop Index / 2축 / 지각요인
                                                         ▼
     (선택) 멀티모달 에이전트가 루브릭 판정 제출 ──► 블렌딩(최대 45%) + 신뢰도 상승
                                                         ▼
                  수정 계획(노력 S/M/L × 영향) + 단계별 예상 점수 + Anti-Slop 브리프
```

**왜 하이브리드인가?**
정적 분석은 코드·카피·에셋 메타데이터에서 *증거*를 정확히 짚을 수 있지만, "이 이미지 손가락이 뭉개졌다", "첫 화면에 초점이 없다", "타격감이 없다" 같은 지각은 화면을 봐야 안다. 대부분의 최신 에이전트는 스크린샷을 볼 수 있으므로 SlopLens는 **사람의 눈을 대신할 체크리스트(루브릭)를 에이전트에게 주고, 그 답을 다시 받아 점수에 합치는** 구조다. 판정 로직은 서버에, 시각 판단은 에이전트에 둔다.

## MCP 도구

| 도구 | 역할 |
|---|---|
| `slop_scan` | 정적 분석 → 리포트 + `scan_id` |
| `slop_visual_rubric` | 시각 검토 체크리스트 + 제출 템플릿 |
| `slop_submit_visual_review` | 루브릭 답변 제출 → 최종 판정 갱신 |
| `slop_fix_plan` | 단계별 수정 계획 + 예상 점수 + Anti-Slop 브리프 |
| `slop_explain_rule` | 규칙 하나의 기준·이유·해결 예시 |
| `slop_list_rules` | 전체 기준 목록 |

MCP 프롬프트: `slop_audit`(전체 감사), `slop_fix`(수정 실행). 프롬프트를 슬래시 명령으로 노출하는 클라이언트에서는 별도 설정 없이 명령으로 쓸 수 있다.

## 규칙 추가하기

```python
# slop_lens/rules/visual.py
@rule(id="VIS-13", title="…", category="visual", kind="fingerprint", weight=2, drivers=["P1"],
      applies=["web"], threshold=3, saturation=8,
      why="사람이 왜 슬롭으로 느끼는지",
      fix={"summary": "…", "steps": ["…"], "example": "…", "effort": "S", "directive": "에이전트 지시문"})
def vis_new(ctx):
    c, ev = ctx.grep(r"pattern", "markup", "style")
    if c:
        return Result(c, ev, f"{c}곳")
```

1. 위처럼 등록하면 CLI·MCP·리포트·수정 계획·브리프에 자동 반영된다.
2. `python scripts/gen_criteria.py`로 문서를 다시 생성한다.
3. `examples/`에 양성/음성 샘플을 추가하고 `python -m unittest discover -s tests`로 보정을 확인한다.
   `RuleHygiene` 테스트가 why/fix/directive/effort 누락을 막는다.

## 확장 지점

- **헤드리스 브라우저 연동**: 에이전트가 Playwright/브라우저 MCP를 갖고 있으면 루브릭 단계에서 그대로 활용된다. 서버 자체는 브라우저를 띄우지 않는다(의존성 0 유지).
- **엔진 게임**: Unity(C#)·Godot(GDScript)·LÖVE(Lua)는 키워드 수준 규칙(GAM-02/04/05/07/08)이 동작한다. 엔진별 심화 규칙은 `rules/game.py`에 추가.
- **CI 게이트**: `slop-lens scan . --fail-over 40` (종료 코드 1).
