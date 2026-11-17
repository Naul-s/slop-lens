"""Structure / layout signals: the stock landing-page skeleton and its rhythm."""
import re
from collections import Counter

from ..lexicon import STOCK_SECTIONS
from ..model import Evidence, Result, rule


@rule(id="LAY-01", title="정형화된 랜딩 페이지 골격", category="layout", kind="fingerprint",
      weight=4, drivers=["P1", "P2"], applies=["web"], threshold=5, saturation=8,
      why="Hero → 기능 3개 → 사용 방법 3단계 → 후기 → 요금제 3단 → FAQ → CTA → 푸터. LLM은 '랜딩 페이지'를 이 순서로 거의 고정 생성한다. "
          "사람은 내용을 읽기도 전에 스크롤 리듬만으로 '또 이 구조'라고 느낀다.",
      fix={"summary": "섹션을 '사용자가 결정에 필요한 질문' 순서로 재구성하고, 해당 제품에만 있는 섹션을 1개 이상 만든다.",
           "steps": ["방문자가 이 페이지에서 답을 얻어야 할 질문 3~5개를 적는다 (예: '내 은행도 되나?').",
                     "각 질문에 답하는 섹션만 남기고 관성적으로 넣은 섹션(How it works, Stats, FAQ 등)은 삭제·병합한다.",
                     "제품 고유 섹션(실제 데모, 비교표, 제작 과정, 창업자 노트 등)을 추가한다.",
                     "섹션마다 레이아웃 형태(전폭 이미지/2열/리스트/표)를 다르게 한다."],
           "example": "Hero(실제 화면) → '이런 분께 맞아요/안 맞아요' → 라이브 데모 → 실제 고객 1명 케이스 스터디 → 가격(1개 플랜+FAQ 통합) → 창업자 노트",
           "effort": "L",
           "directive": "Hero→Features→How it works→Testimonials→Pricing→FAQ→CTA 정형 순서 금지. 방문자의 실제 질문 순서로 섹션을 구성하고, 이 제품에만 있는 섹션을 포함할 것."})
def lay_skeleton(ctx):
    pool = [(t, f, ln) for _lvl, t, f, ln in ctx.headings] + [(t, f, ln) for f, ln, t in ctx.markers]
    pool += [(t, f, ln) for t, f, ln in ctx.buttons if len(t) < 30]
    found, ev = {}, []
    for name, pat in STOCK_SECTIONS.items():
        rx = re.compile(pat, re.I)
        for t, f, ln in pool:
            if rx.search(t):
                found[name] = (t, f, ln)
                break
    # comments like <!-- Pricing Section -->
    for f in ctx.by_role("markup"):
        for name, pat in STOCK_SECTIONS.items():
            if name in found:
                continue
            m = re.search(r"<!--\s*(?:" + pat + r")[^>]{0,30}-->|\{/\*\s*(?:" + pat + r")[^*]{0,30}\*/\}", f.text, re.I)
            if m:
                found[name] = (m.group(0), f.path, f.line_of(m.start()))
    for name, (t, f, ln) in list(found.items())[:7]:
        ev.append(Evidence(f, ln, f"[{name}] {t[:80]}"))
    if len(found) >= 5:
        return Result(len(found), ev, "정형 섹션: " + ", ".join(found.keys()))


@rule(id="LAY-02", title="3열 동일 카드 그리드 반복", category="layout", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=3, saturation=7,
      why="기능·후기·요금제가 모두 '같은 크기 카드 3개'로 배열되면 페이지 전체가 하나의 패턴 반복으로 읽힌다. 위계(무엇이 가장 중요한가)가 사라진다.",
      fix={"summary": "그리드마다 위계를 준다: 1개 크게 + 나머지 작게, 비대칭 2열, 리스트, 표 등으로 형태를 바꾼다.",
           "steps": ["3열 그리드를 전부 찾고 섹션별로 '가장 중요한 1개'를 정한다.",
                     "그 1개는 span-2 또는 전폭으로 키우고 나머지는 보조 리스트로 만든다."],
           "example": ".features{display:grid;grid-template-columns:2fr 1fr;gap:var(--space-6)}\n.features .lead{grid-row:span 2}",
           "effort": "M",
           "directive": "동일 크기 카드 3열 그리드를 섹션마다 반복하지 말 것. 섹션마다 레이아웃 형태와 위계를 다르게."})
def lay_three_grid(ctx):
    c, ev = ctx.grep(r"\b(?:sm:|md:|lg:|xl:)?grid-cols-3\b|grid-template-columns\s*:\s*repeat\(\s*3\s*,|"
                     r"grid-template-columns\s*:\s*repeat\(\s*auto-(?:fit|fill)\s*,\s*minmax", "markup", "style", "script")
    if c:
        return Result(c, ev, f"3열/자동 카드 그리드 {c}회")


@rule(id="LAY-03", title="'Most Popular' 가운데 강조 요금제", category="layout", kind="fingerprint",
      weight=3, drivers=["P1", "P3"], applies=["web"], threshold=1, saturation=2,
      why="3단 요금제의 가운데 카드를 scale-105 + 'Most Popular' 배지로 띄우는 구성은 AI 요금제 섹션의 기본값이다. 실제 가격 정책이 없는 데모에서 특히 공허하게 보인다.",
      fix={"summary": "실제 가격 정책이 없다면 요금제 섹션을 빼고, 있다면 실제 차이(한도·지원 범위)를 표로 명확히 비교한다.",
           "steps": ["가격이 정해지지 않았다면 '베타 무료 · 정식 출시 시 안내' 한 줄로 대체한다.",
                     "가격이 있다면 플랜 수를 줄이고 차이를 비교표로 보여준다."],
           "example": "<table class=\"plans\"><tr><th></th><th>개인</th><th>팀</th></tr><tr><td>월 거래 내역</td><td>500건</td><td>무제한</td></tr></table>",
           "effort": "M",
           "directive": "가짜 3단 요금제 + 'Most Popular' 배지 금지. 실제 가격 정책이 있을 때만 비교표로."})
def lay_popular(ctx):
    vt = ctx.visible_text
    if not re.search(r"/\s*mo(nth)?\b|per month|월\s*\d|/월|\bplan\b|요금|pricing", vt, re.I):
        return None
    c, ev = ctx.grep(r"most popular|best value|>\s*recommended\s*<|가장 인기|인기 플랜|추천 플랜", "markup", "script")
    if c:
        return Result(c, ev, "가운데 강조 요금제 배지")


@rule(id="LAY-04", title="모든 것을 가운데 정렬", category="layout", kind="fingerprint",
      weight=1, drivers=["P1"], applies=["web"], threshold=8, saturation=20,
      why="모든 섹션 제목과 문단이 중앙 정렬이면 읽기 흐름이 끊기고, 디자인 결정 없이 '안전한 기본값'을 택한 인상이 된다.",
      fix={"summary": "본문·긴 문단은 좌측 정렬, 중앙 정렬은 짧은 hero 문구 정도로 제한한다.",
           "steps": ["text-center 사용처를 찾아 두 줄 이상 문단은 좌측 정렬로 바꾼다.", "섹션 제목도 그리드 기준선에 맞춰 좌측 정렬을 기본으로 한다."],
           "example": ".section-head{text-align:start;max-width:38rem}",
           "effort": "S",
           "directive": "모든 텍스트 중앙 정렬 금지. 본문과 섹션 제목은 그리드 기준선에 맞춰 좌측 정렬."})
def lay_center(ctx):
    c, ev = ctx.grep(r"\btext-center\b|text-align\s*:\s*center", "markup", "style", "script")
    left, _ = ctx.grep(r"\btext-(?:left|start)\b|text-align\s*:\s*(?:left|start)", "markup", "style", "script", max_ev=0)
    if c >= 8 and left < c * 0.25:
        return Result(c, ev, f"중앙 정렬 {c}회 / 좌측 정렬 {left}회")


@rule(id="LAY-05", title="모든 섹션 동일한 세로 여백 (py-20 반복)", category="layout", kind="fingerprint",
      weight=1, drivers=["P1"], applies=["web"], threshold=4, saturation=8,
      why="모든 섹션이 py-20/py-24로 같은 높이 리듬을 가지면 페이지가 '같은 상자 쌓기'로 보인다. 사람이 편집한 페이지는 내용에 따라 밀도가 달라진다.",
      fix={"summary": "섹션 밀도를 내용에 맞춰 조절한다: 핵심 섹션은 넉넉히, 보조 섹션은 촘촘히, 일부는 전폭으로.",
           "steps": ["섹션마다 역할(강조/정보/전환)을 정하고 여백 토큰을 3단계로 나눠 적용한다."],
           "example": ".section--hero{padding-block:clamp(4rem,10vw,9rem)} .section--dense{padding-block:2.5rem}",
           "effort": "S",
           "directive": "모든 섹션에 같은 py 값을 쓰지 말 것. 내용 역할에 따라 섹션 밀도를 다르게."})
def lay_padding(ctx):
    vals, ev = [], []
    for f in ctx.by_role("markup"):
        for m in re.finditer(r"<section\b[^>]*class(?:Name)?\s*=\s*[\"'{`]+([^\"'`}]*)", f.text):
            pv = re.findall(r"\bpy-(\d+)\b", m.group(1))
            if pv:
                vals.append(pv[0])
                if len(ev) < 4:
                    ev.append(Evidence(f.path, f.line_of(m.start()), f.snippet(m.start(), m.end())))
    if len(vals) >= 4:
        top, n = Counter(vals).most_common(1)[0]
        if n / len(vals) >= 0.75:
            return Result(n, ev, f"섹션 {len(vals)}개 중 {n}개가 py-{top}")


@rule(id="LAY-06", title="보일러플레이트 푸터 (가짜 법적 링크·소셜)", category="layout", kind="quality",
      weight=2, drivers=["P2", "P3"], applies=["web"], threshold=2, saturation=5,
      why="'© 2024 Company. All rights reserved.' + 아무 데도 가지 않는 Privacy/Terms/소셜 링크는 실제 운영 주체가 없다는 신호다.",
      fix={"summary": "실제로 존재하는 정보(운영자, 연락처, 실제 정책 페이지)만 남기고 링크 없는 항목은 삭제한다.",
           "steps": ["href='#'인 Privacy/Terms/소셜 링크를 삭제하거나 실제 URL로 연결한다.",
                     "푸터에 만든 사람/팀의 실제 정보나 짧은 한 줄 소개를 넣는다."],
           "example": "<footer><p>서울에서 두 명이 만듭니다 · <a href=\"mailto:hi@realdomain.kr\">hi@realdomain.kr</a></p></footer>",
           "effort": "S",
           "directive": "가짜 Privacy/Terms/소셜 링크(href='#') 금지. 실제 존재하는 정보만 푸터에."})
def lay_footer(ctx):
    c1, ev1 = ctx.grep(r"all rights reserved|모든 권리 보유|무단 전재", "markup", "script")
    c2, ev2 = ctx.grep(r"<a\b[^>]*href\s*=\s*[\"']#[\"'][^>]*>\s*(?:privacy|terms|cookie|twitter|github|linkedin|facebook|instagram|개인정보|이용약관)",
                       "markup")
    c3, ev3 = ctx.grep(r"aria-label\s*=\s*[\"'](?:twitter|github|linkedin|facebook|instagram|x)[\"'][^>]*href\s*=\s*[\"']#|href\s*=\s*[\"']#[\"'][^>]*aria-label\s*=\s*[\"'](?:twitter|github|linkedin|facebook|instagram)",
                       "markup")
    c = c1 + c2 + c3
    if c >= 2 and (c2 + c3) >= 1 or c1 >= 1 and (c2 + c3) >= 1:
        return Result(c, (ev1 + ev2 + ev3)[:5], f"저작권 문구 {c1}, 죽은 법적/소셜 링크 {c2 + c3}")
