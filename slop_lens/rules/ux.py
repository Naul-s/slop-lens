"""Interaction / UX signals: hollow polish — looks finished, doesn't work."""
import re

from ..model import Result, rule


@rule(id="UX-01", title="죽은 링크·빈 버튼 (href=\"#\", onClick={() => {}})", category="ux", kind="quality",
      weight=4, drivers=["P3"], applies=["web", "game"], threshold=3, saturation=12,
      why="겉으로는 완성된 내비게이션·버튼인데 눌러도 아무 일이 없다. '보기엔 그럴듯하지만 동작하지 않는' 것은 AI 슬롭을 가장 확실하게 체감시키는 경험이다.",
      fix={"summary": "모든 링크/버튼에 실제 목적지 또는 동작을 연결하고, 준비되지 않은 기능은 노출하지 않는다.",
           "steps": ["href='#' 목록을 뽑아 각 항목을 (1) 실제 URL/앵커 연결 (2) 삭제 (3) '준비 중' 비활성 표시 중 하나로 처리한다.",
                     "빈 onClick 핸들러를 실제 동작으로 구현하거나 버튼을 제거한다.",
                     "Playwright 등으로 모든 링크 클릭 테스트를 자동화한다."],
           "example": "<a href=\"#pricing\">가격</a>  <!-- 실제 존재하는 id로 -->\n<button disabled aria-describedby=\"soon\">팀 플랜</button><span id=\"soon\">5월 출시</span>",
           "effort": "S",
           "directive": "href='#' 또는 빈 핸들러 금지. 동작하지 않는 UI는 만들지 말 것."})
def ux_dead(ctx):
    c, ev = ctx.grep(r"href\s*=\s*\{?\s*[\"']#[\"']|href\s*=\s*[\"']javascript:(?:void\(0\)|;)?[\"']|"
                     r"on[Cc]lick\s*=\s*\{\s*\(\)\s*=>\s*\{\s*\}\s*\}|onclick\s*=\s*[\"']\s*[\"']", "markup", "script")
    if c:
        return Result(c, ev, f"죽은 링크/빈 핸들러 {c}곳")


@rule(id="UX-02", title="가짜 폼 제출 (alert/console.log로 '감사합니다')", category="ux", kind="quality",
      weight=3, drivers=["P3"], applies=["web"], threshold=1, saturation=3,
      why="뉴스레터·문의 폼이 실제로 어디에도 전송하지 않고 alert('Thanks for subscribing!')만 띄운다. 사용자를 속이는 UI는 신뢰를 직접 깎는다.",
      fix={"summary": "폼을 실제 백엔드(또는 Formspree/Netlify Forms 등)에 연결하고, 로딩·성공·실패 상태를 화면 안에서 보여준다.",
           "steps": ["action/fetch 대상 엔드포인트를 연결한다.", "제출 중 버튼 비활성 + 스피너, 성공/실패 메시지를 인라인으로 표시한다.",
                     "연결할 수 없다면 폼을 빼고 메일 링크로 대체한다."],
           "example": "const r = await fetch('/api/subscribe',{method:'POST',body:new FormData(form)});\nstatus.textContent = r.ok ? '구독 완료! 첫 메일은 금요일에 갑니다.' : '실패했어요. 잠시 후 다시 시도해주세요.';",
           "effort": "M",
           "directive": "제출이 실제로 일어나지 않는 가짜 폼 금지. 폼은 실제 전송 + 로딩/성공/실패 상태를 가져야 함."})
def ux_fake_form(ctx):
    c, ev = ctx.grep(r"(?<![\w.])(?:alert|toast(?:\.success)?)\(\s*[\"'`][^\"'`]{0,60}(?:thank you|thanks|subscribed|submitted|we'?ll be in touch|"
                     r"감사합니다|신청(?:이)? 완료|구독(?:이)? 완료|접수(?:가)? 완료)", "script", "markup", skip_comments=True)
    if c:
        return Result(c, ev, f"가짜 제출 처리 {c}곳")


@rule(id="UX-03", title="포커스·상태 디자인 부재", category="ux", kind="quality",
      weight=2, drivers=["P3"], applies=["web"], threshold=1, saturation=1,
      why="hover 효과는 화려한데 키보드 포커스, 로딩, 비어 있음, 오류 상태가 전혀 없다. 데모 캡처용으로만 설계된 UI의 전형이다.",
      fix={"summary": ":focus-visible 스타일과 loading/empty/error 상태를 정의한다.",
           "steps": ["버튼·링크·입력에 :focus-visible 아웃라인을 추가한다.", "데이터를 보여주는 컴포넌트마다 빈 상태·오류 상태 문구를 작성한다."],
           "example": ":where(a,button,input):focus-visible{outline:2px solid var(--brand);outline-offset:2px}",
           "effort": "S",
           "directive": "모든 인터랙티브 요소에 focus-visible 스타일, 데이터 영역에 로딩/빈/오류 상태를 포함."})
def ux_states(ctx):
    inter, _ = ctx.grep(r"<(?:button|a|input|select|textarea)\b", "markup", max_ev=0)
    if inter < 6:
        return None
    if ctx.has(r"focus(?:-visible|-within)?:|:focus|outline", "markup", "style", "script"):
        return None
    return Result(1, [], f"인터랙티브 요소 {inter}개, focus 스타일 없음")


@rule(id="UX-04", title="hover 리프트·transition-all 남발", category="ux", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=6, saturation=20,
      why="모든 카드가 hover 시 살짝 떠오르고(scale-105, -translate-y-1) transition-all duration-300이 붙는 것은 AI 컴포넌트의 습관이다. 의미 없는 움직임은 피로감을 준다.",
      fix={"summary": "모션은 '상태 변화를 설명할 때'만 쓴다. 클릭 가능한 요소에만 절제된 피드백을 준다.",
           "steps": ["transition-all → 필요한 속성만(transition: background-color 120ms).",
                     "클릭 불가능한 카드의 hover 효과를 제거한다.", "prefers-reduced-motion을 존중한다."],
           "example": ".btn{transition:background-color .12s ease}\n@media (prefers-reduced-motion:reduce){*{transition:none!important}}",
           "effort": "S",
           "directive": "hover:scale/translate 리프트와 transition-all 남발 금지. 모션은 상태 변화 설명에만."})
def ux_hover(ctx):
    c, ev = ctx.grep(r"hover:scale-1(?:02|05|10)\b|hover:-translate-y-\d|\btransition-all\b|transform\s*:\s*translateY\(\s*-\d+px\s*\)\s*scale",
                     "markup", "style", "script")
    if c:
        return Result(c, ev, f"hover/transition 상투 패턴 {c}회")


@rule(id="UX-05", title="반응형 대응 없음", category="ux", kind="quality",
      weight=3, drivers=["P3"], applies=["web"], threshold=1, saturation=2,
      why="데스크톱 스크린샷 한 장을 위해 만들어진 페이지는 모바일에서 깨진다. 사람들은 AI 결과물을 '폰에서 열었을 때' 가장 먼저 슬롭으로 판정한다.",
      fix={"summary": "viewport 메타 + 모바일 우선 레이아웃 + 유동 타이포(clamp)를 적용하고 360px 폭에서 검수한다.",
           "steps": ["<meta name=viewport content=\"width=device-width, initial-scale=1\">를 추가한다.",
                     "고정 px 폭을 max-width + %/fr로 바꾼다.", "360/768/1280px에서 스크린샷 비교 검수한다."],
           "example": "h1{font-size:clamp(2rem,6vw,4.5rem)} .grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr))}",
           "effort": "M",
           "directive": "모바일 360px 폭에서 깨지지 않게 반응형으로 설계 (viewport 메타, 유동 레이아웃, clamp 타이포)."})
def ux_responsive(ctx):
    if not ctx.by_role("markup") or ctx.platform == "extension":
        return None
    reasons = []
    has_media = ctx.has(r"@media|@container|\b(?:sm|md|lg|xl):[a-z]|clamp\(|useMediaQuery|matchMedia", "style", "markup", "script")
    fixed = ctx.has(r"(?<![\w-])(?:min-)?width\s*:\s*(?:[6-9]\d\d|\d{4,})px|\bw-\[(?:[6-9]\d\d|\d{4,})px\]", "style", "markup")
    if not has_media and fixed:
        reasons.append("600px 이상 고정 폭이 있는데 미디어쿼리/반응형 처리 없음")
    for d in ctx.html_docs:
        if d.get("has_html_tag") and "viewport" not in d.get("metas", {}):
            reasons.append(f"{d['file']}: viewport 메타 없음")
    if reasons:
        return Result(len(reasons), [], "; ".join(reasons[:4]))


@rule(id="UX-06", title="스크롤 페이드인 일괄 적용", category="ux", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=4, saturation=12,
      why="모든 섹션이 스크롤 시 아래에서 위로 fade-in(AOS, whileInView, opacity:0→1)하는 연출은 AI 페이지의 기본 '고급스러움' 처리다. 내용 읽기를 지연시킨다.",
      fix={"summary": "스크롤 애니메이션을 제거하거나, 이야기가 있는 1곳(데모 시퀀스 등)에만 남긴다.",
           "steps": ["data-aos / whileInView / fade-in 클래스를 일괄 제거한다.", "정말 필요한 1곳은 내용 이해를 돕는 단계적 노출로 설계한다."],
           "example": "<!-- 제거: data-aos=\"fade-up\" -->",
           "effort": "S",
           "directive": "모든 섹션 스크롤 fade-in 금지. 애니메이션은 내용 이해를 돕는 1곳 이하."})
def ux_fade(ctx):
    c, ev = ctx.grep(r"data-aos\s*=|AOS\.init|initial\s*=\s*\{\{\s*opacity\s*:\s*0|whileInView|animate-fade-in|fade-?in-?up|"
                     r"class(?:Name)?=[\"'][^\"']*\bfade-in\b|\breveal-on-scroll\b", "markup", "script", "style")
    if c:
        return Result(c, ev, f"스크롤 페이드인 {c}회")


@rule(id="UX-07", title="네이티브 alert/confirm/prompt 사용", category="ux", kind="quality",
      weight=3, drivers=["P3"], applies=["web"], threshold=1, saturation=4,
      why="브라우저 기본 alert 창은 디자인된 경험을 단번에 깨뜨리고 '시제품/데모 코드'라는 인상을 준다.",
      fix={"summary": "인라인 메시지, 토스트, 모달(<dialog>) 등 디자인 시스템 안의 피드백으로 교체한다.",
           "steps": ["alert/confirm/prompt 호출을 찾아 용도별(정보/확인/입력)로 대체 UI를 만든다."],
           "example": "<dialog id=\"confirm\"><p>정말 삭제할까요?</p><button value=\"ok\">삭제</button></dialog>",
           "effort": "S",
           "directive": "alert/confirm/prompt 사용 금지. 피드백은 디자인된 인라인 UI로."})
def ux_alert(ctx):
    c, ev = ctx.grep(r"(?<![\w.])(?:window\.)?(?:alert|confirm|prompt)\s*\(", "script", skip_comments=True)
    if c:
        return Result(c, ev, f"네이티브 다이얼로그 {c}회")
