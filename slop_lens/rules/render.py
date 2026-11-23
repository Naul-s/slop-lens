"""Measured rules — evaluated only when the Node render probe ran.

Each rule reads ground-truth measurements (computed styles, real clicks, real frames) and
`replaces` the static heuristic it is more accurate than. A rule returns:
  Result → problem found (replaces the static finding)
  CLEAN  → measured and fine (also drops the static guess, unless clean_supersedes=False)
  None   → not measurable here (static finding stays)
"""
import re

from ..model import CLEAN, Evidence, Result, rule
from .game import JUICE
from ._genre import play_reached, realtime
from .visual import FONT_DEFAULTS, _ev  # noqa: F401  (FONT_DEFAULTS reused)


def _r(ctx):
    r = ctx.render
    return r if r and r.get("ok") else None


def _d(ctx):
    r = _r(ctx)
    return r.get("desktop") if r else None


def _g(ctx):
    r = _r(ctx)
    return r.get("game") if r else None


def E(text, where="(렌더)"):
    return Evidence(where, 0, str(text)[:120])


# ============================================================ visual (measured)
@rule(id="RND-01", title="AI 기본 그라디언트 (렌더 색상환 실측)", category="visual", kind="fingerprint", source="render",
      weight=4, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=4, replaces=["VIS-01"],
      why="실제로 화면에 칠해진 그라디언트의 색상(hue)이 남색→보라→핑크(200°~340°) 구간에 걸쳐 있다. hex 목록이 아니라 렌더링된 색을 재므로 "
          "Tailwind 클래스, CSS 변수, 인라인 스타일 어느 방식으로 만들었든 잡힌다. 사람들이 'AI SaaS 색'으로 인식하는 바로 그 색 범위다.",
      fix={"summary": "브랜드 1차색 1개 + 중성색 스케일로 다시 정의하고, 그라디언트는 꼭 필요한 1곳에만 쓴다.",
           "steps": ["리포트의 선택자 위치에서 그라디언트를 단색·질감·사진으로 바꾼다.", "넓은 면적(섹션 배경)부터 우선 제거한다.",
                     "색 토큰을 정의하고 남색~보라 계열은 의도가 있을 때만 쓴다."],
           "example": ":root{--brand:#e4572e;--paper:#f6f1e7;--ink:#1d1a16}\n.cta{background:var(--ink);color:var(--paper)}",
           "effort": "M", "directive": "남색~보라~핑크(색상환 200°~340°) 그라디언트 금지. 브랜드 1차색 + 중성색으로만."})
def rnd_grad(ctx):
    d = _d(ctx)
    if d is None:
        return None
    gs = d.get("gradients", [])
    if not gs:
        return CLEAN
    area = sum(g["area"] for g in gs)
    ev = [E(f"{g['sel']} · hue {g['hues']} · 화면 면적 {g['area']:.0%}") for g in gs[:5]]
    return Result(len(gs) + (2 if area >= 0.3 else 0), ev, f"AI 색상 그라디언트 {len(gs)}개, 첫 화면 대비 면적 합 {area:.0%}")


@rule(id="RND-02", title="그라디언트 텍스트 (실측)", category="visual", kind="fingerprint", source="render",
      weight=3, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=4, replaces=["VIS-02"],
      why="화면에 색상이 크게 다른(30° 이상) 그라디언트 글자가 실제로 그려지고 있다. 같은 색 계열의 채우기·리빌 애니메이션은 제외한다.",
      fix={"summary": "그라디언트 텍스트를 단색 + 서체 대비(굵기/이탤릭/세리프)로 바꾼다.", "steps": ["bg-clip-text/text-transparent 조합 제거."],
           "example": "h1 em{font-style:italic;font-family:var(--font-display);color:var(--brand)}",
           "effort": "S", "directive": "그라디언트 텍스트 금지."})
def rnd_gradtext(ctx):
    d = _d(ctx)
    if d is None:
        return None
    n = d.get("gradientText", 0)
    return Result(n, [], f"여러 색상 그라디언트 텍스트 {n}곳 (단색 계열 연출 {d.get('gradientTextMono', 0)}곳은 제외)") if n else CLEAN


@rule(id="RND-03", title="렌더된 서체 단조로움 (실제 적용 폰트)", category="visual", kind="fingerprint", source="render",
      weight=2, drivers=["P1"], applies=["web"], threshold=1, saturation=1, replaces=["VIS-05"],
      why="실제로 화면 글자의 대부분이 Inter/Poppins/시스템 산세리프 한 종으로 그려지고, 제목에도 별도 서체가 없다.",
      fix={"summary": "디스플레이 서체 1종 + 본문 서체 1종으로 페어링한다.", "steps": ["제목용 서체를 브랜드 성격에 맞게 고른다.", "타입 스케일을 토큰화한다."],
           "example": "h1,h2{font-family:'Fraunces',serif;letter-spacing:-.02em}",
           "effort": "S", "directive": "기본 산세리프 단독 사용 금지. 디스플레이/본문 서체 페어링."})
def rnd_font(ctx):
    d = _d(ctx)
    if d is None or not d.get("fonts"):
        return None
    top, share = d["fonts"][0]
    heads = set(d.get("headingFonts", []))
    if share >= 0.9 and top in FONT_DEFAULTS and heads <= FONT_DEFAULTS:
        return Result(1, [E(f"{f} {s:.0%}") for f, s in d["fonts"][:3]], f"화면 글자의 {share:.0%}가 '{top}'")
    return CLEAN


@rule(id="RND-04", title="글래스모피즘 (실측)", category="visual", kind="fingerprint", source="render",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=3, saturation=8, replaces=["VIS-03"],
      why="화면에 backdrop-filter: blur가 적용된 요소가 여러 개 렌더링되어 있다.",
      fix={"summary": "블러는 실제 겹침이 있는 곳 1곳만 남기고 불투명 면 + 얇은 보더로.", "steps": ["사용처를 줄인다."],
           "example": ".card{background:var(--paper);border:1px solid var(--line)}", "effort": "S",
           "directive": "글래스모피즘 금지 (고정 헤더 1곳 예외)."})
def rnd_glass(ctx):
    d = _d(ctx)
    if d is None:
        return None
    n = d.get("glass", 0)
    return Result(n, [], f"backdrop-blur 요소 {n}개") if n >= 3 else CLEAN


@rule(id="RND-05", title="장식 블러 블롭 (실측)", category="visual", kind="fingerprint", source="render",
      weight=3, drivers=["P1", "P2"], applies=["web"], threshold=1, saturation=4, replaces=["VIS-09"],
      why="filter: blur(30px 이상)가 걸린 큰 장식 요소가 실제로 화면에 깔려 있다. 정보 없는 '분위기용 블롭'이다.",
      fix={"summary": "블롭을 지우고 실제 제품 장면으로 채운다.", "steps": ["리포트 선택자의 요소 삭제."], "example": "",
           "effort": "M", "directive": "장식용 블러 블롭 금지."})
def rnd_blob(ctx):
    d = _d(ctx)
    if d is None:
        return None
    b = d.get("blobs", [])
    return Result(len(b), [E(f"{x['sel']} blur {x['blur']}px") for x in b[:4]], f"블러 블롭 {len(b)}개") if b else CLEAN


@rule(id="RND-06", title="큰 라운드 일괄 적용 (실측)", category="visual", kind="fingerprint", source="render",
      weight=2, drivers=["P1"], applies=["web"], threshold=8, saturation=25, replaces=["VIS-06"],
      why="배경·보더가 있는 박스의 대부분이 12px 이상의 같은 큰 라운드로 렌더링된다.",
      fix={"summary": "역할별 2~3단계 반경 토큰으로 나눈다.", "steps": ["큰 컨테이너는 작게/각지게."], "example": ":root{--r-s:4px;--r-m:10px}",
           "effort": "S", "directive": "큰 라운드 일괄 적용 금지."})
def rnd_radius(ctx):
    d = _d(ctx)
    if d is None:
        return None
    r = d.get("radius", {})
    big, tot = r.get("big", 0), r.get("total", 0)
    if big >= 8 and big / max(1, tot) >= 0.55:
        return Result(big, [], f"박스 {tot}개 중 {big}개가 큰 라운드 ({big / max(1, tot):.0%})")
    return CLEAN


@rule(id="RND-07", title="큰 그림자·발광 효과 (실측)", category="visual", kind="fingerprint", source="render",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=4, saturation=15, replaces=["VIS-07", "VIS-08"],
      why="블러 20px 이상의 큰 그림자와 색이 있는 0 0 발광 그림자가 실제로 여러 요소에 걸려 있다.",
      fix={"summary": "고도는 2단계 이하, 발광은 의미 있는 피드백 1곳에만.", "steps": ["큰 그림자를 보더/명도 차이로 대체."],
           "example": ":root{--elev-1:0 1px 2px rgb(0 0 0/.06)}", "effort": "S", "directive": "큰 그림자 반복·네온 발광 금지."})
def rnd_shadow(ctx):
    d = _d(ctx)
    if d is None:
        return None
    s = d.get("shadows", {})
    n = s.get("big", 0) + 2 * s.get("glow", 0)
    return Result(n, [], f"큰 그림자 {s.get('big', 0)}, 발광 {s.get('glow', 0)}") if n >= 4 else CLEAN


@rule(id="RND-17", title="이모지를 아이콘/장식으로 사용 (렌더 실측)", category="visual", kind="fingerprint", source="render",
      weight=3, drivers=["P1", "P2"], applies=["web"], threshold=4, saturation=12, replaces=["VIS-10"],
      why="화면에 보이는 일반 글자(터미널·코드 목업의 고정폭 글꼴 제외) 속에 이모지가 장식·아이콘처럼 반복된다.",
      fix={"summary": "이모지를 일관된 아이콘 세트나 실제 이미지로 바꾸고, 장식용은 지운다.", "steps": [],
           "example": "<svg class=\"icon\" aria-hidden=\"true\"><use href=\"#i-receipt\"/></svg>", "effort": "S",
           "directive": "이모지를 아이콘·제목 장식으로 쓰지 말 것."})
def rnd_emoji_web(ctx):
    d = _d(ctx)
    if d is None or "emoji" not in d:
        return None
    n = d.get("emoji", 0)
    return Result(n, [], f"장식성 이모지 {n}개 (고정폭 목업 제외)") if n >= 4 else CLEAN


# ============================================================ layout (measured)
@rule(id="RND-08", title="같은 크기 카드 행 반복 (레이아웃 실측)", category="layout", kind="fingerprint", source="render",
      weight=2, drivers=["P1"], applies=["web"], threshold=2, saturation=5, replaces=["LAY-02"],
      why="실제 레이아웃에서 폭·높이가 같은 카드 3개 이상이 한 줄로 놓인 행이 여러 섹션에 반복된다. 위계 없는 패턴 반복이다.",
      fix={"summary": "섹션마다 가장 중요한 1개를 키우고 형태(리스트·표·비대칭)를 바꾼다.", "steps": ["리포트의 행 위치부터 위계를 준다."],
           "example": ".features{grid-template-columns:2fr 1fr}", "effort": "M", "directive": "동일 카드 3열 행 반복 금지."})
def rnd_cards(ctx):
    d = _d(ctx)
    if d is None:
        return None
    rows = d.get("cardRows", [])
    return Result(len(rows), [E(f"{r['sel']} ×{r['n']}") for r in rows[:4]], f"균일 카드 행 {len(rows)}개") if rows else CLEAN


@rule(id="RND-09", title="긴 텍스트 중앙 정렬 비중 (실측)", category="layout", kind="fingerprint", source="render",
      weight=1, drivers=["P1"], applies=["web"], threshold=1, saturation=1, replaces=["LAY-04"],
      why="40자 이상 문단 글자의 대부분이 실제로 가운데 정렬로 렌더링된다.",
      fix={"summary": "본문은 좌측 정렬, 중앙 정렬은 짧은 hero 문구만.", "steps": [], "example": ".section-head{text-align:start}",
           "effort": "S", "directive": "긴 텍스트 중앙 정렬 금지."})
def rnd_center(ctx):
    d = _d(ctx)
    if d is None or d.get("longTextChars", 0) < 300:
        return None
    c = d.get("centerShare", 0)
    return Result(1, [], f"긴 문단의 {c:.0%}가 중앙 정렬", strength=min(1.0, c)) if c >= 0.6 else CLEAN


# ============================================================ a11y / finish (measured)
@rule(id="RND-10", title="텍스트 대비 부족 (WCAG 실측)", category="a11y", kind="quality", source="render",
      weight=2, drivers=["P3"], applies=["web"], threshold=1, saturation=1,
      why="실제 배경색 위에서 글자 대비가 WCAG 기준(본문 4.5:1, 큰 글자 3:1)에 못 미친다. 회색 글씨를 어두운 배경에 얹는 AI 다크 테마에서 특히 흔하며, 읽기 힘든 화면은 '덜 만든' 인상을 준다.",
      fix={"summary": "본문 대비 4.5:1 이상이 되도록 글자색 토큰을 조정한다.", "steps": ["리포트의 대비값이 낮은 텍스트부터 색을 올린다.",
           "muted 색 토큰 하나를 정의해 모든 보조 텍스트에 일괄 적용한다."],
           "example": ":root{--muted:#a39b8f} /* #15120f 배경에서 7.1:1 */", "effort": "S",
           "directive": "모든 텍스트는 WCAG AA 대비(4.5:1, 큰 글자 3:1) 이상."})
def rnd_contrast(ctx):
    d = _d(ctx)
    if d is None or d.get("chars", 0) < 100:
        return None
    c = d.get("contrast", {})
    share, samples = c.get("lowShare", 0), c.get("samples", [])
    if share >= 0.04 or len(samples) >= 4:
        return Result(1, [E(f"{s['ratio']}:1 · '{s['text']}' · {s['sel']}") for s in samples[:5]],
                      f"대비 미달 텍스트 비중 {share:.0%}", strength=min(1.0, 0.4 + share * 4))
    return CLEAN


@rule(id="RND-11", title="깨진 리소스·런타임 오류", category="a11y", kind="quality", source="render",
      weight=3, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=5,
      why="페이지를 열면 404 리소스(이미지·스크립트·사운드)나 자바스크립트 오류가 발생한다. 생성된 코드가 존재하지 않는 파일을 참조하는 일은 AI 결과물에서 매우 흔하다.",
      fix={"summary": "참조된 모든 파일이 실제로 존재하는지 확인하고, 런타임 오류를 0으로 만든다.",
           "steps": ["리포트의 실패 URL을 실제 에셋으로 채우거나 참조를 제거한다.", "브라우저 콘솔 오류를 하나씩 해결한다."],
           "example": "", "effort": "S", "directive": "존재하지 않는 파일 참조와 콘솔 오류 0개."})
def rnd_errors(ctx):
    r = _r(ctx)
    if r is None:
        return None
    c = r.get("console", {})
    import urllib.parse as _u
    host = _u.urlparse(r.get("url", "")).hostname or ""
    base = ".".join(host.split(".")[-2:])
    def own(u):
        h = _u.urlparse(u).hostname or ""
        return h in ("127.0.0.1", "localhost") or h.endswith(base)
    failed = [f for f in c.get("failed", []) if own(f.get("url", "")) and not re.search(r"favicon\.ico", f.get("url", ""))
              and not (f.get("status") and (int(f["status"]) >= 500 or int(f["status"]) in (401, 403)))
              and "ERR_BLOCKED" not in str(f.get("error") or "")]  # browser security blocks (ORB/CORB/CSP) are not missing files
    errs = [e for e in c.get("errors", []) if e.startswith("pageerror")]
    n = len(failed) + len(errs)
    if not n:
        return CLEAN
    ev = [E(f"{f.get('status') or f.get('error')} {f['url']}") for f in failed[:4]] + [E(e) for e in errs[:2]]
    return Result(n, ev, f"실패한 리소스 {len(failed)}개, JS 오류 {len(errs)}개")


# ============================================================ ux (measured)
@rule(id="RND-12", title="모바일 레이아웃 붕괴 (390px 실측)", category="ux", kind="quality", source="render",
      weight=3, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=1, replaces=["UX-05"],
      why="휴대폰 폭(390px)으로 열었을 때 viewport 설정이 없어 데스크톱 화면이 축소되어 보이거나, 가로로 넘쳐 좌우 스크롤이 생긴다.",
      fix={"summary": "viewport 메타 + 유동 레이아웃으로 바꾸고 390px에서 다시 확인한다.",
           "steps": ["<meta name=viewport content=\"width=device-width, initial-scale=1\"> 추가.", "넘치는 요소(리포트 선택자)의 고정 폭 제거."],
           "example": "img,video,canvas{max-width:100%;height:auto}", "effort": "M", "directive": "390px 폭에서 축소·가로 넘침 없이."})
def rnd_mobile(ctx):
    r = _r(ctx)
    if r is None or not r.get("mobile"):
        return None
    m = r["mobile"]
    reasons, ev = [], []
    if m.get("noViewport") and ctx.kind == "game":
        return None  # no viewport tag: a desktop game by design. Not being on phones is a scope choice, not a defect you see
    if m.get("noViewport"):
        reasons.append(f"viewport 미설정 → 폰에서 {m.get('layoutWidth')}px 데스크톱 화면이 축소 표시")
    if m.get("overflow"):
        reasons.append(f"가로 넘침 (문서 폭 {m.get('scrollWidth')}px)")
        ev = [E(f"{o['sel']} → right {o['right']}px") for o in m.get("offenders", [])[:4]]
    return Result(len(reasons), ev, "; ".join(reasons)) if reasons else CLEAN


@rule(id="RND-13", title="너무 작은 터치 영역·글자 (모바일 실측)", category="a11y", kind="quality", source="render",
      weight=1, drivers=["P3"], applies=["web"], threshold=1, saturation=1,
      why="모바일에서 버튼·링크의 터치 영역이 24px보다 작거나 12px 미만 글자가 많아 손가락으로 쓰기 어렵다.",
      fix={"summary": "터치 대상은 최소 24px(권장 44px), 본문은 16px 이상.", "steps": ["작은 대상에 padding을 추가한다."],
           "example": "nav a{display:inline-block;padding:.6rem .4rem}", "effort": "S", "directive": "모바일 터치 대상 최소 24px, 본문 16px."})
def rnd_targets(ctx):
    r = _r(ctx)
    if r is None or not r.get("mobile"):
        return None
    m = r["mobile"]
    if m.get("noViewport"):
        return None  # RND-12 already covers it; sizes are meaningless when zoomed out
    small, tot, tiny = m.get("smallTargets", 0), m.get("targets", 0), m.get("tinyTextShare", 0)
    if (small >= 5 and small / max(1, tot) >= 0.25) or tiny >= 0.15:
        return Result(1, [E(s) for s in m.get("smallSamples", [])[:4]], f"작은 터치 대상 {small}/{tot}, 12px 미만 글자 {tiny:.0%}")
    return CLEAN


@rule(id="RND-14", title="죽은 클릭 (실제 클릭 테스트)", category="ux", kind="quality", source="render",
      weight=4, drivers=["P3"], applies=["web"], threshold=1, saturation=6, replaces=["UX-01"],
      why="화면의 버튼·링크를 실제로 눌러봤더니 화면·주소·네트워크 어디에도 변화가 없다. 정적 추정이 아니라 실측이다. "
          "'그럴듯해 보이는데 아무것도 안 되는' 경험은 AI 슬롭을 가장 확실하게 체감시킨다.",
      fix={"summary": "죽은 버튼마다 (1) 실제 동작 연결 (2) 삭제 (3) 비활성+사유 표시 중 하나로 처리한다.",
           "steps": ["리포트의 버튼 문구로 위치를 찾는다.", "준비되지 않은 기능은 노출하지 않는다.", "Playwright로 클릭 테스트를 CI에 넣는다."],
           "example": "<button disabled aria-describedby=\"soon\">팀 플랜</button><small id=\"soon\">5월 출시</small>",
           "effort": "S", "directive": "눌러서 아무 일도 없는 버튼·링크 금지."})
def rnd_dead(ctx):
    r = _r(ctx)
    c = r.get("clicks") if r else None
    if not c or not c.get("tested"):
        return None
    dead = c.get("dead", [])
    if not dead:
        return CLEAN
    ev = [E(f"'{x['text'] or x['tag']}' (href={x.get('href')}) — {x['reason']}") for x in dead[:6]]
    return Result(len(dead), ev, f"클릭한 {c['tested']}개 중 {len(dead)}개가 아무 동작 없음",
                  strength=min(1.0, 0.4 + 0.6 * len(dead) / max(1, c["tested"])))


@rule(id="RND-15", title="키보드 포커스 표시 없음 (Tab 실측)", category="a11y", kind="quality", source="render",
      weight=1, drivers=["P3"], applies=["web"], threshold=1, saturation=1, replaces=["UX-03"],
      why="Tab 키로 이동했을 때 포커스된 요소의 모습이 전혀 바뀌지 않는다 (outline:none 등으로 제거됨).",
      fix={"summary": ":focus-visible 스타일을 정의한다.", "steps": [], "example": ":where(a,button,input):focus-visible{outline:2px solid var(--brand);outline-offset:2px}",
           "effort": "S", "directive": "모든 인터랙티브 요소에 보이는 focus-visible 스타일."})
def rnd_focus(ctx):
    r = _r(ctx)
    f = r.get("focus") if r else None
    if not f or not f.get("tested"):
        return None
    inv = f.get("invisible", [])
    if len(inv) >= 3 and len(inv) / f["tested"] >= 0.5:
        return Result(1, [E(f"<{x['tag']}> {x['text']}") for x in inv[:4]], f"Tab 이동 {f['tested']}회 중 {len(inv)}회 포커스가 보이지 않음")
    return CLEAN


@rule(id="RND-16", title="런타임 alert/confirm 팝업 (실측)", category="ux", kind="quality", source="render",
      weight=3, drivers=["P3"], applies=["web"], threshold=1, saturation=3, replaces=["UX-07"], clean_supersedes=False,
      why="페이지를 사용하는 중에 브라우저 기본 alert/confirm 창이 실제로 떴다.",
      fix={"summary": "인라인 메시지·토스트·<dialog>로 대체한다.", "steps": [], "example": "status.textContent='구독 완료!'",
           "effort": "S", "directive": "alert/confirm/prompt 금지."})
def rnd_dialogs(ctx):
    r = _r(ctx)
    if r is None:
        return None
    ds = (r.get("dialogs") or []) + (r.get("clickDialogs") or [])
    return Result(len(ds), [E(f"{x['type']}: {x['message']}") for x in ds[:4]], f"네이티브 팝업 {len(ds)}회") if ds else CLEAN


# ============================================================ game runtime (measured)
@rule(id="RND-G1", title="게임 루프 품질 (프레임 실측)", category="gametech", kind="quality", source="render",
      weight=3, drivers=["P3"], applies=["game"], threshold=1, saturation=1, replaces=["GAM-01"],
      why="실제로 실행해보니 requestAnimationFrame 대신 setInterval로 그리거나, 프레임 간격이 들쭉날쭉(34ms 초과 프레임 다수)하다.",
      fix={"summary": "requestAnimationFrame + 고정 timestep 루프로 교체하고 프레임당 작업을 줄인다.", "steps": [],
           "example": "requestAnimationFrame(frame) // update(STEP) 누적 처리", "effort": "S", "directive": "rAF + 고정 timestep 루프."})
def rnd_loop(ctx):
    g = _g(ctx)
    if g is None or ("hasCanvas" in g and not g.get("hasCanvas")):
        return None  # DOM / idle games tick on timers by design
    issues = []
    fast_iv = [i for i in g.get("intervals", []) if 0 < i <= 40]
    if g.get("rafFrames", 0) < 10 and fast_iv:
        issues.append(f"setInterval({fast_iv[0]}ms) 렌더 루프, rAF 프레임 {g.get('rafFrames', 0)}")
    if g.get("rafFrames", 0) > 60 and g.get("longFrameShare", 0) >= 0.1:
        issues.append(f"34ms 초과 프레임 {g['longFrameShare']:.0%}")
    if issues:
        return Result(len(issues), [], "; ".join(issues))
    return CLEAN if g.get("rafFrames", 0) > 30 else None


@rule(id="RND-G2", title="플레이 중 사운드 없음 (실측)", category="game", kind="quality", source="render",
      weight=3, drivers=["P2"], applies=["game"], threshold=1, saturation=1, replaces=["GAM-05"],
      why="실제로 8초 이상 입력하며 플레이하는 동안 오디오 재생 호출이 한 번도 없었다.",
      fix={"summary": "핵심 행동 효과음 + BGM + 음소거 토글.", "steps": [], "example": "sfx.hit.cloneNode().play()",
           "effort": "S", "directive": "핵심 행동 효과음과 BGM 필수."})
def rnd_audio(ctx):
    g = _g(ctx)
    if g is None or g.get("sound") or not play_reached(ctx):
        return None  # AUD-03 judges sound from the audio tap; unreached play is unmeasured
    return Result(1, [], f"{g.get('played_ms', 0) // 1000}초 플레이 중 오디오 호출 0회") if not g.get("audioCalls") else CLEAN


@rule(id="RND-G3", title="프로그래머 아트 (드로우콜 실측)", category="game", kind="quality", source="render",
      weight=3, drivers=["P2", "P3"], applies=["game"], threshold=1, saturation=1, replaces=["GAM-03"],
      why="플레이 중 캔버스에 그려진 것이 사각형·원·텍스트뿐이고 이미지(스프라이트)는 한 장도 그려지지 않았다.",
      fix={"summary": "아트 방향을 정하고 핵심 오브젝트부터 스프라이트로 교체한다.", "steps": [],
           "example": "ctx.drawImage(sprites,frame*16,0,16,16,x,y,32,32)", "effort": "L", "directive": "도형·텍스트만으로 그린 게임 금지."})
def rnd_art(ctx):
    g = _g(ctx)
    if g is None:
        return None
    dr = g.get("draw", {})
    if dr.get("webgl") or (g.get("canvas") or {}).get("kind") == "webgl":
        return CLEAN
    prims = sum(dr.get(k, 0) for k in ("fillRect", "strokeRect", "rect", "roundRect", "arc", "ellipse", "fillText"))
    if prims >= 50 and not dr.get("drawImage"):
        return Result(1, [E(", ".join(f"{k} {v}" for k, v in dr.items()))], f"도형/텍스트 호출 {prims}회, drawImage 0회")
    return CLEAN if dr.get("drawImage") else None


@rule(id="RND-G4", title="이모지 스프라이트 (실측)", category="game", kind="fingerprint", source="render",
      weight=3, drivers=["P1", "P2"], applies=["game"], threshold=5, saturation=40, replaces=["GAM-12"],
      why="플레이 중 캔버스에 이모지 문자를 그려 캐릭터·적으로 사용했다.",
      fix={"summary": "이모지를 스프라이트로 교체한다.", "steps": [], "example": "", "effort": "M", "directive": "이모지 스프라이트 금지."})
def rnd_emoji(ctx):
    g = _g(ctx)
    if g is None:
        return None
    n = g.get("emojiText", 0)
    return Result(n, [], f"이모지 그리기 {n}회") if n >= 5 else CLEAN


@rule(id="RND-G5", title="원색 팔레트 (캔버스 픽셀 실측)", category="game", kind="fingerprint", source="render",
      weight=2, drivers=["P1", "P5"], applies=["game"], threshold=1, saturation=1, replaces=["GAM-14"],
      why="실제 게임 화면 픽셀 중 배경을 뺀 부분의 상당량이 #ff0000, #00ff00, #ffff00 같은 CSS 기본 원색이다.",
      fix={"summary": "4~8색 제한 팔레트를 정해 모든 색을 거기서만 가져온다.", "steps": [], "example": "const P={bg:'#1a1c2c',hero:'#ffcd75',enemy:'#b13e53'}",
           "effort": "S", "directive": "기본 원색 금지, 제한 팔레트 사용."})
def rnd_palette(ctx):
    g = _g(ctx)
    pal = ((g or {}).get("canvas") or {}).get("palette")
    if not pal or "primaryShare" not in pal:
        return None
    s = pal["primaryShare"]
    return Result(1, [], f"배경 제외 픽셀의 {s:.0%}가 순수 원색", strength=min(1.0, 0.4 + s)) if s >= 0.25 else CLEAN


@rule(id="RND-G6", title="플레이 중 피드백(Juice) 신호 부족 (실측)", category="game", kind="quality", source="render",
      weight=4, drivers=["P2"], applies=["game"], threshold=1, saturation=1, replaces=["GAM-04"],
      why="실제 플레이 중 화면 흔들림/변형, 투명도 연출(플래시·페이드), 파티클, 발광 같은 피드백이 거의 관측되지 않았다.",
      fix={"summary": "핵심 행동 1개에 히트스톱·플래시·파티클·카메라 흔들림·사운드를 겹친다.", "steps": [],
           "example": "function onHit(e){hitStop=.05;shake=6;e.flash=.08;burst(e.x,e.y,10);sfx.hit.play()}", "effort": "M",
           "directive": "핵심 행동마다 다층 피드백."})
def rnd_juice(ctx):
    g = _g(ctx)
    if g is None or "juice" not in g or not realtime(ctx) or not play_reached(ctx):
        return None  # no runtime play reached, or not an action game
    if (g.get("draw") or {}).get("webgl") or ((g.get("canvas") or {}).get("kind") == "webgl"):
        return None  # 2D-canvas instrumentation can't see WebGL effects; keep the static estimate
    seen = [k for k, v in g["juice"].items() if v]
    code = ctx.joined("script", "engine", "markup")
    static_n = sum(1 for p in JUICE.values() if re.search(p, code))
    if len(seen) >= 2:
        return CLEAN
    strength = 1.0 if not seen else 0.6
    if static_n >= 2:
        strength = 0.3  # code has juice; random input probably didn't trigger it
    return Result(1, [], f"런타임 관측: {', '.join(seen) or '없음'} · 코드상 기법 {static_n}개", strength=strength)


@rule(id="RND-G7", title="alert 게임오버 / 새로고침 재시작 (실측)", category="gametech", kind="quality", source="render",
      weight=4, drivers=["P3"], applies=["game"], threshold=1, saturation=2, replaces=["GAM-06"], clean_supersedes=False,
      why="플레이 중 브라우저 alert 창이 뜨거나 페이지가 통째로 새로고침되었다.",
      fix={"summary": "게임 내 게임오버 화면과 reset() 함수로 즉시 재시작.", "steps": [], "example": "function reset(){Object.assign(state,{score:0,mode:'play'})}",
           "effort": "S", "directive": "alert 게임오버·새로고침 재시작 금지."})
def rnd_gameover(ctx):
    r = _r(ctx)
    g = _g(ctx)
    if g is None:
        return None
    ds = r.get("dialogs") or []
    n = len(ds) + g.get("navigations", 0)
    if n:
        ev = [E(f"{d['type']}: {d['message']}") for d in ds[:3]]
        if g.get("navigations"):
            ev.append(E(f"플레이 중 페이지 새로고침 {g['navigations']}회"))
        return Result(n, ev, f"팝업 {len(ds)}회, 새로고침 {g.get('navigations', 0)}회")
    return CLEAN


@rule(id="RND-G8", title="게임이 반응하지 않거나 오류로 멈춤", category="gametech", kind="quality", source="render",
      weight=4, drivers=["P3"], applies=["game"], threshold=1, saturation=1,
      why="실제로 실행해보니 JS 오류가 나거나, 입력을 줘도 화면이 전혀 변하지 않았다.",
      fix={"summary": "콘솔 오류를 해결하고 시작 화면에서 입력 안내를 명확히 한다.", "steps": [], "example": "", "effort": "M",
           "directive": "실행 후 오류 없이 입력에 반응해야 함."})
def rnd_frozen(ctx):
    r = _r(ctx)
    g = _g(ctx)
    if g is None:
        return None
    errs = [e for e in (r.get("console") or {}).get("errors", []) if e.startswith("pageerror")]
    if errs:
        return Result(1, [E(e) for e in errs[:3]], "JS 오류: " + str(len(errs)))
    if not g.get("changedDuringPlay") and not g.get("animatesIdle"):
        # can't tell "game ignores input" from "auto-input didn't know how to start it" — report, don't score
        note = "자동 플레이 입력에 화면이 바뀌지 않음 → 게임 본편에 도달 못 했을 수 있어 런타임 게임필·사운드는 측정하지 않음"
        if note not in ctx.notes:
            ctx.notes.append(note)
        return None
    return CLEAN
