#!/usr/bin/env python3
"""Generate docs/CRITERIA.md and skills/slop-lens/references/criteria.md from the rule registry,
so the documentation can never drift from what the detector actually checks."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slop_lens.model import CATEGORIES, DRIVERS, EFFORT_LABEL  # noqa: E402
from slop_lens.rubric import RUBRIC  # noqa: E402
from slop_lens.review import SENSES, CRAFT, LEVEL_WORDS  # noqa: E402
from slop_lens.rules import get_rules  # noqa: E402
from slop_lens.scoring import CAT_WEIGHTS, VERDICTS  # noqa: E402

INTRO = """# SlopLens 판정 기준 (Criteria)

> 이 문서는 `scripts/gen_criteria.py`가 규칙 레지스트리에서 자동 생성합니다. 직접 수정하지 마세요.

## 1. 정의

**AI Slop**은 "AI가 만들었다"는 사실 자체가 아니다. **생성 모델의 기본값을 사람의 결정 없이 그대로 내보내서**,
보는 사람이 "대충 자동으로 찍어냈다"고 즉시 느끼는 결과물이다. AI로 만들었어도 사람이 방향을 정하고 다듬었다면 슬롭이 아니고,
사람이 만들었어도 템플릿 기본값과 가짜 완성도로 채웠다면 슬롭처럼 느껴진다.

따라서 SlopLens는 "AI가 썼는가?"를 맞히는 탐지기가 아니라, **사람이 슬롭이라고 느끼는 원인을 측정하고 고치게 하는 도구**다.

## 2. 두 축 모델

| 축 | 질문 | 대표 신호 |
|---|---|---|
| **AI 지문 (Genericness)** | 수천 개의 AI 결과물과 구별되는가? | 보라 그라디언트, Inter 단독, 정형 랜딩 골격, 상투어, 이모지 아이콘, 블러 블롭 |
| **완성도 결함 (Effort deficit)** | 보이는 것만큼 실제로 완성돼 있는가? | 죽은 링크, 가짜 후기·통계, alert 폼, 더미 텍스트, 게임필·사운드 없음 |

| | 완성도 결함 낮음 | 완성도 결함 높음 |
|---|---|---|
| **AI 지문 높음** | 세련된 템플릿 — 잘 돌아가지만 어디서 본 듯함 | **전형적 AI 슬롭** |
| **AI 지문 낮음** | 의도된 결과물 | 덜 만든 결과물 — 마무리가 비어 있음 |

## 3. 지각 요인 5가지 — 사람은 *왜* 슬롭이라고 느끼나

모든 규칙은 아래 요인 중 하나 이상에 연결된다. 리포트는 요인별 점수도 보여준다.
"""

SCORING = """
## 5. 점수 계산

1. 규칙이 발동하면 **증거량 = 가중치(1~5) × 강도(0~1)**. 강도는 발생 횟수가 `발동 기준`에서 `최대 강도` 사이일 때 0.4→1.0으로 증가한다 (상투어 밀도처럼 비율 기반 규칙은 자체 계산).
2. **영역 점수** = 100·(1 − e^(−Σ증거량/6)). 포화형이라 약한 신호가 많이 쌓이면 올라가지만 100을 넘지 않는다.
3. **정적 Slop Index** = 0.3·가중평균(영역) + 0.4·상위3영역 평균 + 0.3·최고 영역 + 수렴 가산(45점 이상 영역이 2개를 넘을 때마다 +4, 최대 +12).
   사람은 가장 눈에 띄는 문제와, 여러 영역에서 동시에 나타나는 신호로 판단하기 때문에 최악의 영역과 동시 발생에 무게를 둔다.
4. **시각 검토** (멀티모달 에이전트가 스크린샷/플레이로 판정): yes=1, partial=0.5, no=0, na=제외 → 가중 평균 → 최종 = (1−a)·정적 + a·시각, a = 0.45 × 응답 비율.
5. **신뢰도**: 마크업·텍스트량·스타일·이미지·렌더 실측·시각 검토 응답 비율로 높음/보통/낮음. 렌더 실측이 없으면 색·대비·클릭·모바일·게임 런타임이 추정치이고, 시각 검토가 없으면 이미지 품질과 레이아웃 감각이 반영되지 않는다.

### 영역 가중치
"""

POLICY = """
## 7. 오탐 방지 원칙

- **단일 신호로 단정하지 않는다.** 대부분의 규칙은 여러 번 반복될 때만 발동하고(`발동 기준`), 점수는 여러 영역에서 수렴할 때 크게 오른다.
- **상투어는 밀도로 본다.** 300단어 이상이면 1000단어당 6회 미만은 무시한다.
- **약한 신호는 가중치가 낮다.** 예: AI 기본 해상도(IMG-02)는 가중치 1, 이미지 2장 이상일 때만.
- **C2PA는 약한 증거로만 센다.** 카메라·편집기도 C2PA를 남기므로 생성기 이름이 없으면 0.5로 계산.
- **검사기를 속이는 수정은 해결이 아니다.** 목표는 점수가 아니라 사람이 받는 인상이다. 가짜 후기를 더 그럴듯한 가짜로 바꾸는 것은 금지.
- **측정이 추정을 이긴다.** 렌더 실측이 가능한 항목(클릭, 색, 대비, 모바일, 게임 런타임)은 실측 결과가 정적 추정을 대체한다. 예: JS가 처리하는 `href="#"` 탭은 정적으로는 '죽은 링크'지만 실제 클릭으로 동작이 확인되면 제외된다 (`examples/js-handled-links`).
- **보정 기준**: `examples/`의 슬롭 샘플은 웹 ≥80 / 게임 ≥60, 수작업 샘플은 <20을 정적·실측 두 모드 모두에서 유지하도록 테스트(`tests/`)가 강제한다.
"""


def build():
    L = [INTRO, "| 요인 | 이름 | 설명 |", "|---|---|---|"]
    for k, d in DRIVERS.items():
        L.append(f"| {k} | {d['name']} ({d['en']}) | {d['desc']} |")
    L += ["", "## 4. 판정 규칙 (정적 분석 + 렌더 실측)", "",
          "- **정적** 규칙은 소스·에셋만으로 항상 실행된다 (Python만 있으면 됨).",
          "- **실측(RND-)** 규칙은 Node 렌더 프로브가 설치돼 있을 때 실제 브라우저로 렌더링·클릭·플레이한 결과로 판정한다. "
          "`대체` 열의 정적 규칙은 실측이 있으면 버려진다 — 실측이 문제를 찾으면 실측 결과로, 문제가 없으면 정적 추정의 오탐이 제거된다 "
          "(`clean_supersedes=False`인 규칙은 실측에서 재현되지 않아도 정적 증거를 유지).",
          "- `유형`: 지문 = AI 지문 축, 결함 = 완성도 결함 축 · `노력`: " + ", ".join(f"{k}={v}" for k, v in EFFORT_LABEL.items()), ""]
    rules = get_rules()
    for cat, label in CATEGORIES.items():
        sub = [r for r in rules if r.category == cat]
        if not sub:
            continue
        L += [f"### {label} (`{cat}`)", "", "| ID | 기준 | 출처 | 유형 | 가중치 | 발동/최대 | 요인 | 대상 | 대체 | 노력 |", "|---|---|---|---|---:|---|---|---|---|---|"]
        for r in sub:
            L.append(f"| {r.id} | {r.title} | {'실측' if r.source == 'render' else '정적'} | {'지문' if r.kind == 'fingerprint' else '결함'} | {r.weight:g} | "
                     f"{r.threshold:g}/{r.saturation:g} | {','.join(r.drivers)} | {'/'.join(r.applies)} | {', '.join(r.replaces) or '—'} | {r.fix.get('effort')} |")
        L.append("")
        for r in sub:
            L += [f"#### {r.id} {r.title}", "", f"**왜 슬롭으로 느끼나** — {r.why}", "", f"**해결** — {r.fix['summary']}", ""]
            L += [f"{i}. {s}" for i, s in enumerate(r.fix.get("steps", []), 1)]
            if r.fix.get("example"):
                L += ["", "```", r.fix["example"], "```"]
            L += ["", f"> 에이전트 지시문: {r.fix['directive']}", ""]
    L.append(SCORING)
    L += ["| 영역 | 웹 | 게임 |", "|---|---:|---:|"]
    for cat, label in CATEGORIES.items():
        L.append(f"| {label} | {CAT_WEIGHTS['web'].get(cat, '—')} | {CAT_WEIGHTS['game'].get(cat, '—')} |")
    L += ["", "### 판정 등급", "", "| Index | 등급 | 의미 |", "|---|---|---|"]
    for lo, hi, code, label, desc in VERDICTS:
        L.append(f"| {lo}–{min(hi, 100)} | {label} (`{code}`) | {desc} |")
    L += ["", "## 6. 지각 리뷰 (판정의 핵심)", "",
          "슬롭인지는 사람이 판단한다. 리뷰어(이미지를 볼 수 있는 에이전트 또는 사람)가 SlopLens가 만든 화면 시트·에셋 시트·플레이 프레임·사운드 분석을 보고 "
          "감각별로 레벨·근거·이유·해결을 답한다. 리뷰가 있으면 **최종 = 0.65 × 지각 지수 + 0.35 × 측정 근거 지수**로 확정하고, 없으면 측정 근거만으로 **잠정** 판정한다.", "",
          "레벨: " + " · ".join(f"{k} {v}" for k, v in LEVEL_WORDS.items()), "",
          "| ID | 감각 | 질문 | 가중치(웹/게임) |", "|---|---|---|---|"]
    for sid, title, q, ww, wg in SENSES:
        L.append(f"| {sid} | {title} | {q} | {ww} / {wg} |")
    L.append(f"| {CRAFT[0]} | {CRAFT[1]} | {CRAFT[2]} | 레벨×4점을 지각 지수에서 차감 |")
    L += ["", "### 공들인 흔적 실측 (웹)", "",
          "커스텀 폰트, 직접 정의한 모션 곡선, 다양한 레이아웃 그리드, OpenType/가변폰트 설정, SVG 일러스트, 큰 이미지·영상을 실측해 0~100점을 낸다. "
          "AI가 흉내 내는 원본(예: Stripe)은 표면 패턴을 공유하지만 이런 디테일이 많다 → AI 지문 신호를 최대 60%까지 낮춰 반영한다.", ""]
    L += ["", "## 7. 예전 예/아니오 시각 루브릭 (호환용)", "",
          "정적 분석으로 볼 수 없는 것 — 이미지 아티팩트, 시선 초점, 스타일 일관성, 실제 클릭·플레이 경험 — 을 멀티모달 에이전트가 화면을 보고 판정한다. 모든 문항은 **yes = 슬롭 신호 있음**.", "",
          "| ID | 항목 | 질문 | 가중치 | 대상 |", "|---|---|---|---:|---|"]
    for rid, (r, qn, lf) in RUBRIC.items():
        L.append(f"| {rid} | {r.title} | {qn}{(' — ' + lf) if lf else ''} | {r.weight:g} | {'/'.join(r.applies)} |")
    L.append(POLICY.replace("## 7. 오탐 방지 원칙", "## 8. 오탐 방지 원칙"))
    return "\n".join(L)


if __name__ == "__main__":
    text = build()
    for p in (os.path.join(ROOT, "docs", "CRITERIA.md"), os.path.join(ROOT, "skills", "slop-lens", "references", "criteria.md")):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        print("written", os.path.relpath(p, ROOT))
