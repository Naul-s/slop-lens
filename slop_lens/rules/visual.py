"""Visual design signals: default palettes, gradients, glass, glow, radius/shadow sameness."""
import re
from collections import Counter

from ..model import Evidence, Result, rule

AI_HEX = r"#(?:667eea|764ba2|6366f1|8b5cf6|a855f7|7c3aed|4f46e5|9333ea|c084fc|818cf8|a78bfa|d946ef|6d28d9|5b21b6|4338ca)\b"
GRAD_FROM = re.compile(r"\bfrom-(indigo|violet|purple|fuchsia|blue|pink|cyan|sky)-[3-7]00\b")
GRAD_TO = re.compile(r"\bto-(purple|violet|pink|fuchsia|indigo|cyan|blue|rose)-[3-7]00\b")


def _ev(f, pos, s):
    return Evidence(f.path, f.line_of(pos), s.strip()[:110])


@rule(id="VIS-01", title="AI 기본 그라디언트 (인디고→보라→핑크)", category="visual", kind="fingerprint",
      weight=4, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=4,
      why="indigo-500→purple-600 계열 그라디언트는 LLM이 '모던한 느낌'을 요청받았을 때 가장 먼저 꺼내는 기본값이다. "
          "사람들은 이 색 조합을 수많은 AI 생성 SaaS 페이지에서 반복해 봤기 때문에 보자마자 '자동 생성'으로 분류한다.",
      fix={"summary": "브랜드 고유 1차색 1개 + 중성색 스케일로 팔레트를 다시 정의하고, 그라디언트는 꼭 필요한 1곳에만 쓴다.",
           "steps": ["브랜드 성격을 형용사 3개로 정하고 그에 맞는 1차색을 고른다 (보라/남색 계열은 의도가 있을 때만).",
                     "CSS 변수/Tailwind theme에 --brand, --ink, --paper, --muted 토큰을 정의한다.",
                     "배경 그라디언트는 단색 + 질감(노이즈, 사진, 패턴)으로 대체한다.",
                     "강조는 색이 아니라 크기·굵기·여백 대비로 만든다."],
           "example": ":root{--brand:#e4572e;--ink:#1d1a16;--paper:#f6f1e7;--muted:#8a8172}\n"
                      ".hero{background:var(--paper);color:var(--ink)}\n.btn{background:var(--brand)}",
           "effort": "M",
           "directive": "indigo/violet/purple/pink 그라디언트를 쓰지 말 것. 브랜드 1차색 1개와 따뜻하거나 차가운 중성색 스케일로만 구성할 것."})
def vis_gradient(ctx):
    count, ev = 0, []
    for f, pos, cls in ctx.class_strings():
        if ("gradient-to" in cls or "linear-to" in cls or "bg-gradient" in cls) and GRAD_FROM.search(cls) and GRAD_TO.search(cls):
            count += 1
            if len(ev) < 6:
                ev.append(_ev(f, pos, cls))
    c2, ev2 = ctx.grep(r"(?:linear|radial|conic)-gradient\((?:[^;{}]){0,220}?" + AI_HEX, "style", "markup", "script")
    count += c2
    ev += ev2[: max(0, 6 - len(ev))]
    if count:
        return Result(count, ev, f"AI 기본 보라 계열 그라디언트 {count}곳")


@rule(id="VIS-02", title="그라디언트 텍스트 (bg-clip-text)", category="visual", kind="fingerprint",
      weight=3, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=4,
      why="헤드라인 일부에 그라디언트를 입히는 기법은 2023년 이후 AI 랜딩 페이지의 상징이 되었다. 의미 없이 '강조된 단어'는 오히려 읽기를 방해한다.",
      fix={"summary": "그라디언트 텍스트를 제거하고 단색 + 서체 대비(굵기/이탤릭/세리프 전환)로 강조한다.",
           "steps": ["bg-clip-text/text-transparent 조합을 제거한다.",
                     "강조 단어는 같은 색에서 굵기나 서체(예: 세리프 이탤릭)를 바꿔 표현한다.",
                     "정말 필요하면 1페이지 1회, 브랜드 색 단색 밑줄/하이라이트로 대체한다."],
           "example": "<h1>매일 쓰는 <em class=\"accent\">가계부</em></h1>\n.accent{font-family:'Fraunces',serif;font-style:italic;color:var(--brand)}",
           "effort": "S",
           "directive": "그라디언트 텍스트(bg-clip-text, text-transparent) 금지. 강조는 굵기·서체·크기 대비로만."})
def vis_grad_text(ctx):
    count, ev = 0, []
    for f, pos, cls in ctx.class_strings():
        if "bg-clip-text" in cls and GRAD_FROM.search(cls):
            count += 1
            if len(ev) < 5:
                ev.append(_ev(f, pos, cls))
    # CSS: only blocks whose gradient uses AI-hue colors (var()-only reveal effects are not this pattern)
    for f in ctx.by_role("style", "markup"):
        for m in re.finditer(r"\{[^{}]*background-clip\s*:\s*text[^{}]*\}", f.text, re.I):
            block = m.group(0)
            if re.search(AI_HEX, block, re.I) or re.search(r"gradient\([^;]*\b(?:purple|violet|indigo|fuchsia|magenta|hotpink|deeppink)\b", block, re.I):
                count += 1
                if len(ev) < 5:
                    ev.append(Evidence(f.path, f.line_of(m.start()), f.snippet(m.start(), m.end())))
    if count:
        return Result(count, ev, f"보라 계열 그라디언트 텍스트 {count}곳")


@rule(id="VIS-03", title="글래스모피즘 남용 (backdrop-blur)", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=3, saturation=8,
      why="반투명 흰색 + 블러 카드는 깊이를 연출하려는 AI의 기본 해법이다. 여러 곳에 반복되면 정보 위계가 흐려지고 '템플릿' 인상이 강해진다.",
      fix={"summary": "블러는 실제 겹침이 있는 곳(고정 내비 등) 1곳에만 남기고 카드는 불투명 면 + 얇은 보더로 바꾼다.",
           "steps": ["backdrop-blur 사용처를 목록화하고 실제로 뒤에 콘텐츠가 겹치는 곳만 남긴다.",
                     "카드는 bg-[--paper] + 1px 보더 또는 그림자 없이 여백으로 구분한다."],
           "example": ".card{background:var(--paper);border:1px solid color-mix(in srgb,var(--ink) 12%,transparent)}",
           "effort": "S",
           "directive": "글래스모피즘(backdrop-blur 반투명 카드) 사용 금지, 고정 헤더 1곳만 예외."})
def vis_glass(ctx):
    c, ev = ctx.grep(r"\bbackdrop-blur(?:-[a-z0-9]+)?\b|backdrop-filter\s*:\s*blur", "markup", "style", "script")
    if c:
        return Result(c, ev, f"backdrop-blur {c}회")


@rule(id="VIS-04", title="Tailwind 기본 팔레트만 사용 (브랜드 토큰 없음)", category="visual", kind="fingerprint",
      weight=3, drivers=["P1", "P2"], applies=["web", "game"], threshold=15, saturation=60,
      why="indigo/slate/gray 기본 스케일을 그대로 쓰면 수만 개의 Tailwind 결과물과 같은 색 공간에 놓인다. 브랜드 토큰이 없다는 것은 '색을 결정한 사람이 없다'는 신호다.",
      fix={"summary": "tailwind theme(또는 @theme)에 브랜드 토큰을 정의하고 기본 팔레트 직접 참조를 토큰으로 치환한다.",
           "steps": ["tailwind.config / @theme 에 brand, ink, paper, muted, accent 토큰을 만든다.",
                     "bg-indigo-600 → bg-brand, text-gray-600 → text-muted 식으로 일괄 치환한다.",
                     "회색은 순수 회색 대신 브랜드 색조가 섞인 warm/cool gray로 정의한다."],
           "example": "@theme {\n  --color-brand: oklch(62% 0.19 35);\n  --color-ink: oklch(22% 0.02 60);\n  --color-paper: oklch(97% 0.01 80);\n}",
           "effort": "M",
           "directive": "Tailwind 기본 색(indigo/violet/slate/gray-xxx) 직접 사용 금지. 프로젝트 고유 디자인 토큰을 먼저 정의하고 그것만 사용."})
def vis_default_palette(ctx):
    c, ev = ctx.grep(r"\b(?:bg|text|border|from|to|via|ring|fill|stroke|shadow|outline|divide)-(?:indigo|violet|purple|slate|gray|zinc|blue)-\d{2,3}\b",
                     "markup", "script")
    if c < 15:
        return None
    tokens = ctx.has(r"--(?:color-)?(?:brand|primary|accent|ink|paper)\b|@theme|colors\s*:\s*\{[\s\S]{0,400}?(brand|primary)",
                     "style", "config", "markup", "script")
    if tokens:
        return None
    return Result(c, ev, f"기본 팔레트 클래스 {c}회, 브랜드 색 토큰 정의 없음")


FONT_DEFAULTS = {"inter", "poppins", "roboto", "open sans", "montserrat", "system-ui", "-apple-system",
                 "blinkmacsystemfont", "segoe ui", "arial", "helvetica", "helvetica neue", "sans-serif",
                 "plus jakarta sans", "dm sans", "outfit", "manrope", "geist", "geist sans", "ui-sans-serif",
                 "space grotesk", "lato", "nunito", "raleway"}


@rule(id="VIS-05", title="기본 서체 단일 사용 (Inter/Poppins/시스템)", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=1, saturation=1,
      why="Inter·Poppins·시스템 산세리프 한 종만 쓰면 타이포그래피에서 개성이 사라진다. 사람은 글자 모양에서 브랜드 목소리를 가장 먼저 느끼는데, 그 목소리가 '기본값'이다.",
      fix={"summary": "디스플레이 서체 1종 + 본문 서체 1종으로 페어링하고 크기·굵기·자간 스케일을 정의한다.",
           "steps": ["헤드라인용 개성 있는 서체(세리프, 그로테스크, 손글씨 등)를 브랜드 성격에 맞춰 고른다.",
                     "본문은 가독성 좋은 서체를 유지하되 한글은 Pretendard/본고딕/마루부리 등에서 의도적으로 선택한다.",
                     "타입 스케일(예: 1.25배)과 헤드라인 자간(-0.02em 등)을 토큰화한다."],
           "example": ":root{--font-display:'Fraunces',serif;--font-body:'Pretendard',sans-serif}\nh1,h2{font-family:var(--font-display);letter-spacing:-0.02em}",
           "effort": "S",
           "directive": "Inter/Poppins 단독 사용 금지. 브랜드 성격을 드러내는 디스플레이 서체와 본문 서체를 페어링할 것."})
def vis_font(ctx):
    fams, ev = [], []
    for f in ctx.by_role("style", "markup", "config", "script"):
        for m in re.finditer(r"font-family\s*:\s*([^;}{\n]+)|fontFamily\s*:\s*\{?[\s\S]{0,80}?[\"']([^\"']+)[\"']", f.text, re.I):
            val = (m.group(1) or m.group(2) or "").strip()
            if val.startswith("var(") or "inherit" in val:
                continue
            first = val.split(",")[0].strip().strip("\"'").lower()
            if first:
                fams.append(first)
                if len(ev) < 4:
                    ev.append(Evidence(f.path, f.line_of(m.start()), f.snippet(m.start(), m.end())))
        for m in re.finditer(r"(?<![\w-])font\s*:\s*[^;{}]*?\d(?:[\d.]*)(?:px|rem|em|%|pt)(?:\s*/\s*[\d.]+\w*)?\s+([^;{}\n]+)", f.text, re.I):
            first = m.group(1).split(",")[0].strip().strip("\"'").lower()
            if first and not first.startswith("var("):
                fams.append(first)
        for m in re.finditer(r"fonts\.googleapis\.com/css2?\?([^\"'>\s]+)", f.text):
            for fam in re.findall(r"family=([^:&]+)", m.group(1)):
                fams.append(urllib_unquote(fam).replace("+", " ").lower())
            if len(ev) < 4:
                ev.append(Evidence(f.path, f.line_of(m.start()), f.snippet(m.start(), m.end())))
        for m in re.finditer(r"import\s*\{([^}]+)\}\s*from\s*[\"']next/font/google", f.text):
            for fam in m.group(1).split(","):
                fams.append(fam.strip().replace("_", " ").lower())
    if not ctx.by_role("markup"):
        return None
    if not fams:
        return Result(1, [], "서체 지정이 없음 → 브라우저/프레임워크 기본 산세리프")
    uniq = set(fams)
    if uniq <= FONT_DEFAULTS:
        return Result(1, ev, "사용 서체: " + ", ".join(sorted(uniq)))


def urllib_unquote(s):
    import urllib.parse
    return urllib.parse.unquote(s)


@rule(id="VIS-06", title="모든 요소에 같은 큰 라운드 (rounded-2xl 일괄)", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=8, saturation=25,
      why="카드·버튼·이미지·입력창이 전부 같은 rounded-xl/2xl이면 '말랑한 기본 UI 키트' 인상이 된다. 사람이 설계한 UI는 요소의 역할마다 모서리 규칙이 다르다.",
      fix={"summary": "모서리 반경을 역할별 2~3단계 토큰으로 나누고, 일부 요소는 각지게 둔다.",
           "steps": ["--radius-s(4px) / --radius-m(10px) / --radius-pill 로 역할 기반 규칙을 정한다.",
                     "큰 이미지·섹션 컨테이너는 0 또는 작은 반경으로 바꿔 긴장감을 만든다."],
           "example": ":root{--r-s:4px;--r-m:10px}\n.card{border-radius:var(--r-s)} .chip{border-radius:999px}",
           "effort": "S",
           "directive": "rounded-2xl 일괄 적용 금지. 역할별로 다른 모서리 반경 규칙(작게/각지게 포함)을 쓸 것."})
def vis_radius(ctx):
    big, ev = ctx.grep(r"\brounded-(?:xl|2xl|3xl)\b|border-radius\s*:\s*(?:1[2-9]|2[0-9]|3[0-2])px|border-radius\s*:\s*(?:1|1\.25|1\.5|2)rem",
                       "markup", "style", "script")
    allr, _ = ctx.grep(r"\brounded(?:-[a-z0-9]+)?\b|border-radius\s*:", "markup", "style", "script", max_ev=0)
    if big >= 8 and big / max(1, allr) >= 0.55:
        return Result(big, ev, f"큰 라운드 {big}/{allr}회 ({big * 100 // max(1, allr)}%)")


@rule(id="VIS-07", title="그림자 남발 (shadow-lg/xl 반복)", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=6, saturation=20,
      why="모든 카드가 떠 있으면 아무것도 떠 있지 않은 것과 같다. 큰 그림자의 반복은 깊이 체계가 설계되지 않았다는 신호다.",
      fix={"summary": "고도(elevation) 단계를 2개로 줄이고 대부분의 면은 그림자 없이 보더/여백으로 구분한다.",
           "steps": ["shadow-lg/xl/2xl을 전부 찾아 '정말 떠 있어야 하는 요소'(모달, 드롭다운)만 남긴다.",
                     "카드 구분은 배경 명도 차이 또는 1px 보더로 대체한다."],
           "example": ":root{--elev-1:0 1px 2px rgb(0 0 0/.06);--elev-2:0 8px 24px rgb(0 0 0/.12)}",
           "effort": "S",
           "directive": "shadow-lg/xl 반복 금지. 고도는 최대 2단계, 대부분은 그림자 없이."})
def vis_shadow(ctx):
    c, ev = ctx.grep(r"\b(?:hover:)?shadow-(?:lg|xl|2xl)\b|box-shadow\s*:\s*0\s+(?:1[0-9]|2[0-9])px\s+(?:2[5-9]|[3-6][0-9])px",
                     "markup", "style", "script")
    if c:
        return Result(c, ev, f"큰 그림자 {c}회")


@rule(id="VIS-08", title="네온 글로우 다크 테마", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=2, saturation=6,
      why="검은 배경 위 보라/시안 글로우는 'AI·미래·테크'를 표현하려는 프롬프트의 평균값이다. 특히 게임에서는 '네온 사이버' 기본값으로 인식된다.",
      fix={"summary": "글로우를 제거하거나 단 하나의 상호작용 피드백(예: 포커스, 히트)에만 의미 있게 사용한다.",
           "steps": ["0 0 Npx 형태의 glow 그림자·text-shadow를 찾아 제거한다.",
                     "다크 테마는 순검정 대신 색조가 있는 어두운 배경(#14110f 등)과 낮은 채도의 강조색을 쓴다."],
           "example": ":root{--bg:#15120f;--fg:#ece3d4;--accent:#d9a441}",
           "effort": "S",
           "directive": "네온 글로우(0 0 Npx 발광 그림자, 보라/시안 발광) 금지. 다크 테마는 색조가 있는 저채도 팔레트로."})
def vis_glow(ctx):
    c, ev = ctx.grep(r"shadow-\[0_0_\d+px|drop-shadow-\[0_0|text-shadow\s*:\s*0\s+0\s+\d+px|box-shadow\s*:\s*0\s+0\s+\d{2,}px|"
                     r"shadow-(?:purple|violet|cyan|fuchsia|pink|indigo|blue)-500/\d+|shadowBlur\s*=\s*\d{2,}",
                     "markup", "style", "script")
    if c:
        return Result(c, ev, f"발광 효과 {c}회")


@rule(id="VIS-09", title="장식용 블러 블롭 (흐릿한 원형 배경)", category="visual", kind="fingerprint",
      weight=3, drivers=["P1", "P2"], applies=["web"], threshold=1, saturation=4,
      why="hero 뒤에 absolute + rounded-full + blur-3xl 원을 깔아 '분위기'를 만드는 패턴은 AI 랜딩 페이지의 서명과 같다. 정보는 없고 장식만 있다.",
      fix={"summary": "블롭을 제거하고 그 자리를 제품의 실제 장면(스크린샷, 사진, 사용 맥락 일러스트)으로 채운다.",
           "steps": ["blur-2xl/3xl 장식 div를 삭제한다.",
                     "hero 비주얼은 '이 제품이 실제로 무엇을 하는지' 보여주는 요소로 바꾼다."],
           "example": "<figure class=\"hero-shot\"><img src=\"/shots/dashboard-real.png\" alt=\"이번 달 지출을 카테고리별로 보여주는 실제 화면\"></figure>",
           "effort": "M",
           "directive": "장식용 블러 원(blob)·그라디언트 메쉬 배경 금지. 시각 요소는 실제 제품/사용 장면을 보여줘야 함."})
def vis_blobs(ctx):
    count, ev = 0, []
    for f, pos, cls in ctx.class_strings():
        if "rounded-full" in cls and re.search(r"\bblur-(?:2xl|3xl|\[\d{2,}px\])", cls) and re.search(r"\b(absolute|fixed)\b", cls):
            count += 1
            if len(ev) < 5:
                ev.append(_ev(f, pos, cls))
    c2, ev2 = ctx.grep(r"filter\s*:\s*blur\(\s*(?:[4-9]\d|\d{3,})px", "style", "markup")
    count += c2
    ev += ev2[: max(0, 5 - len(ev))]
    if count:
        return Result(count, ev, f"장식 블롭 {count}개")


EMOJI = re.compile("[🌀-🫿☀-⛿✀-➿⭐]")
HYPE = set("🚀✨💡⚡🔥🎯💎🌟🙌💪📈🎉")


@rule(id="VIS-10", title="이모지를 아이콘/장식으로 사용", category="visual", kind="fingerprint",
      weight=3, drivers=["P1", "P2"], applies=["web"], threshold=4, saturation=12,
      why="🚀✨💡 같은 이모지를 기능 아이콘이나 제목 장식으로 쓰는 것은 LLM 출력의 대표 습관이다. 플랫폼마다 모양이 달라 일관성도 깨진다.",
      fix={"summary": "이모지를 하나의 아이콘 세트(또는 직접 그린 픽토그램)로 교체하고, 아이콘이 필요 없는 곳은 지운다.",
           "steps": ["기능 카드의 이모지를 동일 stroke/크기의 SVG 아이콘으로 교체한다.",
                     "제목·버튼 앞 장식용 이모지는 삭제한다.",
                     "가능하면 아이콘 대신 실제 화면 조각·숫자·사진으로 기능을 설명한다."],
           "example": "<svg class=\"icon\" aria-hidden=\"true\"><use href=\"#i-receipt\"/></svg>",
           "effort": "S",
           "directive": "이모지를 아이콘·제목 장식으로 쓰지 말 것 (🚀✨💡 등). 일관된 아이콘 세트 또는 실제 이미지 사용."})
def vis_emoji(ctx):
    txt = ctx.visible_text
    found = EMOJI.findall(txt)
    found = [e for e in found if e not in "★☆✓✔"]
    if len(found) < 4:
        return None
    c, ev = ctx.grep(EMOJI, "markup", "script", flags=0, max_ev=5)
    hype = Counter(e for e in found if e in HYPE)
    detail = f"이모지 {len(found)}개" + (f" (과장형: {' '.join(k for k, _ in hype.most_common(6))})" if hype else "")
    return Result(len(found), ev, detail)


@rule(id="VIS-11", title="색 타일 안의 아이콘 (기능 카드 공식)", category="visual", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=3, saturation=8,
      why="'연한 색 둥근 사각형 안에 아이콘 + 제목 + 설명 2줄' 카드는 AI가 기능 섹션을 만들 때의 정형 패턴이다.",
      fix={"summary": "기능 설명을 '아이콘 타일 카드' 대신 실제 화면·사례·숫자를 보여주는 형태로 바꾸고 레이아웃에 변주를 준다.",
           "steps": ["가장 중요한 기능 1개는 크게, 나머지는 리스트로 위계를 만든다.",
                     "아이콘 타일 대신 기능이 동작하는 실제 UI 조각(크롭 스크린샷)을 쓴다."],
           "example": "<article class=\"feature feature--lead\"><img src=\"/shots/split-bill.png\" alt=\"…\"><h3>더치페이를 3초에</h3></article>",
           "effort": "M",
           "directive": "'둥근 색 타일 아이콘 + 제목 + 2줄 설명' 기능 카드 3개 반복 금지. 기능은 실제 화면·사례로 위계 있게 보여줄 것."})
def vis_icon_tile(ctx):
    count, ev = 0, []
    for f, pos, cls in ctx.class_strings():
        if re.search(r"\b(?:w|h|size)-(?:10|11|12|14|16)\b", cls) and re.search(r"\brounded-(?:md|lg|xl|2xl|full)\b", cls) and \
                re.search(r"\bbg-(?:[a-z]+)-(?:50|100|500/10|500/20|600/10|400/10)\b|\bbg-(?:primary|brand)/(?:10|20)\b", cls) and \
                re.search(r"\b(?:flex|grid)\b", cls):
            count += 1
            if len(ev) < 5:
                ev.append(_ev(f, pos, cls))
    if count:
        return Result(count, ev, f"아이콘 타일 {count}개")


@rule(id="VIS-12", title="토큰 없는 하드코딩 색상 난립", category="visual", kind="quality",
      weight=1, drivers=["P5"], applies=["web", "game"], threshold=14, saturation=40,
      why="색이 체계 없이 hex 값으로 흩어져 있으면 미세하게 다른 색이 섞여 화면이 '조금씩 어긋나' 보인다.",
      fix={"summary": "사용 중인 색을 추출해 6~10개 토큰으로 수렴시키고 나머지는 토큰으로 치환한다.",
           "steps": ["모든 hex 값을 뽑아 비슷한 색끼리 묶는다.", "CSS 변수로 정의 후 치환한다."],
           "example": ":root{--ink:#1d1a16;--ink-2:#4a443b;--line:#e4ddd0}",
           "effort": "M",
           "directive": "색상은 반드시 CSS 변수(디자인 토큰)로 정의해서 사용."})
def vis_hex(ctx):
    style = ctx.joined("style")
    if not style:
        return None
    if re.search(r"--[\w-]+\s*:\s*#", style):
        return None
    hexes = set(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", style))
    if len(hexes) >= 14:
        return Result(len(hexes), [], f"서로 다른 hex 색 {len(hexes)}개, CSS 변수 없음")
