"""Accessibility / finish signals: details a person who cared would have fixed."""
import re

from ..lexicon import GENERIC_TITLES
from ..model import Evidence, Result, rule


@rule(id="A11Y-01", title="기본값 문서 제목 / lang 속성 누락", category="a11y", kind="quality",
      weight=3, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=2,
      why="브라우저 탭에 'Vite + React', 'Document', 'My Website'가 떠 있거나 <html lang>이 없으면 아무도 마무리하지 않았다는 신호다. 공유 링크 미리보기에서도 그대로 노출된다.",
      fix={"summary": "페이지마다 고유한 <title>과 올바른 lang 속성을 지정한다.",
           "steps": ["'제품명 — 핵심 가치 한 줄' 형식으로 title을 쓴다.", "<html lang=\"ko\"> 등 실제 언어를 지정한다."],
           "example": "<html lang=\"ko\"><title>잔고 — 월급날 3분 가계부</title>",
           "effort": "S",
           "directive": "고유한 <title>과 올바른 <html lang> 지정."})
def a11y_title(ctx):
    issues = []
    for d in ctx.displayed_docs():
        if not d.get("has_html_tag"):
            continue
        t = (d.get("title") or "").strip()
        if not t:
            issues.append(Evidence(d["file"], 1, "<title> 없음"))
        elif t.lower() in GENERIC_TITLES:
            issues.append(Evidence(d["file"], 1, f"기본값 title: {t}"))
        if not d.get("lang"):
            issues.append(Evidence(d["file"], 1, "<html lang> 없음"))
    if issues:
        return Result(len(issues), issues[:5], "; ".join(e.snippet for e in issues[:4]))


@rule(id="A11Y-02", title="공유 메타데이터·파비콘 누락", category="a11y", kind="quality",
      weight=2, drivers=["P3"], applies=["web", "game"], threshold=2, saturation=3,
      why="meta description, og:image가 없고 파비콘이 vite.svg/기본값이면 링크를 공유했을 때 '빈 카드'가 나온다. 출시를 고려하지 않은 결과물로 보인다.",
      fix={"summary": "description, og:title/og:image, 고유 파비콘을 추가한다.",
           "steps": ["1200×630 공유 이미지를 만든다.", "브랜드 마크로 SVG 파비콘을 만든다."],
           "example": "<meta name=\"description\" content=\"…\">\n<meta property=\"og:image\" content=\"https://…/og.png\">\n<link rel=\"icon\" href=\"/favicon.svg\">",
           "effort": "S",
           "directive": "meta description, og 태그, 고유 파비콘 포함."})
def a11y_meta(ctx):
    docs = [d for d in ctx.displayed_docs() if d.get("has_html_tag")]
    if not docs or ctx.platform == "extension":
        return None
    d = docs[0]
    missing = []
    m = d.get("metas", {})
    if "description" not in m:
        missing.append("meta description")
    if "og:image" not in m and "og:title" not in m:
        missing.append("og 태그")
    icons = [l for l in d.get("links", []) if "icon" in (l.get("rel") or "").lower()]
    if not icons:
        missing.append("파비콘")
    elif any(re.search(r"vite\.svg|react\.svg|favicon\.ico$", l.get("href", "")) and "vite" in l.get("href", "") for l in icons):
        missing.append("기본 vite.svg 파비콘")
    if missing:
        return Result(len(missing), [Evidence(d["file"], 1, "누락: " + ", ".join(missing))], "누락: " + ", ".join(missing))


@rule(id="A11Y-03", title="이미지 대체텍스트 누락·무의미 (alt=\"image\")", category="a11y", kind="quality",
      weight=2, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=6,
      why="alt가 없거나 'image', 'hero image', 'placeholder'인 것은 이미지의 의미를 아무도 생각하지 않았다는 뜻이다.",
      fix={"summary": "이미지마다 '무엇을 보여주는지'를 문장으로 쓰고, 장식 이미지는 alt=\"\"로 명시한다.",
           "steps": ["정보 이미지: 내용과 맥락을 쓴다.", "장식 이미지: alt=\"\" + aria-hidden."],
           "example": "<img src=\"week.avif\" alt=\"식비가 주간 예산을 12% 초과했다고 표시된 화면\">",
           "effort": "S",
           "directive": "모든 이미지에 의미 있는 alt (장식은 alt=\"\")."})
def a11y_alt(ctx):
    bad = []
    for f, ln, src, alt in ctx.imgs:
        if alt is None:
            bad.append(Evidence(f, ln, f"alt 없음: {src[:70]}"))
        elif re.fullmatch(r"\s*(?:image|img|photo|picture|hero(?: image)?|placeholder|banner|icon|logo|screenshot|이미지|사진|그림)\s*\d*\s*", alt, re.I):
            bad.append(Evidence(f, ln, f"무의미 alt='{alt}': {src[:60]}"))
    if bad:
        return Result(len(bad), bad[:6], f"문제 있는 alt {len(bad)}개 / 이미지 {len(ctx.imgs)}개")


@rule(id="A11Y-04", title="클릭 가능한 div/span (버튼 아님)", category="a11y", kind="quality",
      weight=2, drivers=["P3"], applies=["web"], threshold=2, saturation=8,
      why="onClick이 붙은 div는 키보드·스크린리더로 조작할 수 없다. 시각적으로만 동작하는 UI다.",
      fix={"summary": "클릭 요소는 <button> 또는 <a>로 바꾼다.",
           "steps": ["onClick 있는 div/span을 button으로 교체하고 스타일을 초기화한다."],
           "example": "<div onClick={open}> → <button type=\"button\" onClick={open}>",
           "effort": "S",
           "directive": "클릭 요소는 반드시 button/a 사용."})
def a11y_divbtn(ctx):
    c, ev = ctx.grep(r"<(?:div|span|li)\b(?![^>]*\brole=)[^>]*\son[Cc]lick\s*=", "markup")
    if c:
        return Result(c, ev, f"클릭 가능한 div/span {c}개")


@rule(id="A11Y-05", title="프레임워크 기본 보일러플레이트 잔존", category="a11y", kind="quality",
      weight=3, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=3,
      why="'Edit src/App.jsx and save', 'count is 0', vite.svg/react.svg 로고, App.css 기본 스타일이 남아 있으면 생성 후 정리 단계가 없었다는 뜻이다.",
      fix={"summary": "템플릿 기본 파일·문구·로고·CSS를 제거한다.",
           "steps": ["App.css/index.css의 기본 템플릿 스타일(#root max-width 1280px 등)을 삭제한다.", "기본 로고 에셋과 카운터 예제를 제거한다."],
           "example": "rm src/assets/react.svg public/vite.svg",
           "effort": "S",
           "directive": "프레임워크 템플릿 기본 코드·로고·문구를 모두 제거."})
def a11y_boiler(ctx):
    c, ev = ctx.grep(r"Edit <code>src/|and save to (?:test|reload)|count is \{?count|Click on the Vite and React logos|Get started by editing|"
                     r"Welcome to (?:Next\.js|Nuxt|SvelteKit)|vite\.svg|react\.svg|#root\s*\{\s*max-width:\s*1280px", "markup", "script", "style")
    if c:
        return Result(c, ev, f"보일러플레이트 흔적 {c}곳")
