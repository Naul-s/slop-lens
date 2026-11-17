"""Code trace signals: leftovers that LLM-generated code characteristically contains."""
import re

from ..model import Evidence, Result, rule


@rule(id="COD-01", title="AI 스캐폴딩 주석 ('In a real app…', 'Add more…', 'TODO: implement')", category="code", kind="fingerprint",
      weight=4, drivers=["P3", "P2"], applies=["web", "game"], threshold=1, saturation=5,
      why="'In a real application you would…', 'Replace with your API key', 'Add more items as needed', '실제 서비스에서는…' 같은 주석은 "
          "LLM이 미완성 부분을 사람에게 떠넘긴 흔적이다. 이 주석이 남아 있으면 해당 기능이 실제로는 구현되지 않았을 가능성이 높다.",
      fix={"summary": "주석이 가리키는 미구현 부분을 실제로 구현하거나, 기능 자체를 제거한 뒤 주석을 삭제한다.",
           "steps": ["리포트 위치의 주석을 하나씩 열어 '무엇을 미뤘는지' 확인한다.",
                     "mock/simulate 코드는 실제 API 호출로 교체하거나 데모임을 UI에 명시한다.",
                     "남길 주석은 '왜(why)'를 설명하는 것만 남긴다."],
           "example": "// In a real app, fetch from API  ← 삭제\nconst res = await fetch('/api/items'); // 캐시 5분: 대시보드 새로고침 폭주 방지",
           "effort": "M",
           "directive": "'In a real app', 'Add more', 'Replace with your', 'TODO: implement', '실제 서비스에서는' 류의 미루기 주석과 mock/simulate 코드 금지. 끝까지 구현할 것."})
def cod_scaffold(ctx):
    c, ev = ctx.grep(r"(?://|#|/\*|<!--|\{/\*)\s*(?:TODO:?\s*(?:implement|add|replace|connect|hook up)|add (?:more|your)\b|"
                     r"replace (?:this |with )?(?:with )?(?:your|actual|real)|in a (?:real|production)(?: world)? (?:app|application|project|implementation|scenario|environment)|"
                     r"this is a (?:placeholder|simplified|basic|mock|simple)|for (?:demo|demonstration|simplicity)(?: purposes)?|"
                     r"you (?:can|could|might|may|would) (?:customize|replace|add|want|need)|rest of (?:the )?(?:code|component|logic)|"
                     r"\.\.\.\s*(?:rest|more|other)|placeholder for|simulat(?:e|ed|ing) (?:an? )?(?:api|network|request|loading|server|delay)|"
                     r"mock (?:data|api|response)|여기에 .{0,20}(?:추가|구현|입력)|실제 (?:앱|서비스|구현|환경)에서는|필요에 따라 수정|예시(?:용)? (?:데이터|코드))",
                     "script", "markup", "style")
    if c:
        return Result(c, ev, f"스캐폴딩 주석 {c}개")


@rule(id="COD-02", title="코드를 그대로 읽어주는 주석 ('// Function to handle click')", category="code", kind="fingerprint",
      weight=2, drivers=["P2"], applies=["web", "game"], threshold=6, saturation=20,
      why="'// Get the button element', '// Add event listener', '// Update the score' 처럼 코드를 한 줄씩 번역한 주석은 LLM 코드의 강한 특징이다.",
      fix={"summary": "무엇(what)을 설명하는 주석은 지우고, 이유(why)·제약·트레이드오프만 남긴다.",
           "steps": ["리포트의 주석을 삭제한다.", "이름이 의도를 드러내도록 함수·변수명을 개선한다."],
           "example": "// Update the score  ← 삭제\n// 콤보 3 이상부터 배율 적용: 초반 난이도 완화를 위해  ← 유지",
           "effort": "S",
           "directive": "코드를 그대로 설명하는 주석 금지. 주석은 이유와 제약만."})
def cod_narrate(ctx):
    c, ev = ctx.grep(r"^\s*(?://|#)\s*(?:Function to \w+|(?:Get|Set|Create|Initiali[sz]e|Update|Add|Draw|Clear|Render|Reset|Start|Call|Define|Return|Handle|Check|Loop through|Increment|Spawn|Move|Show|Hide)"
                     r"\s+(?:the|a|an|all|if|event|new)\b[ \w'-]{0,40})\.?\s*$", "script", flags=re.I | re.M)
    if c:
        return Result(c, ev, f"서술형 주석 {c}개")


@rule(id="COD-03", title="섹션 라벨 주석 (<!-- Hero Section -->)", category="code", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web"], threshold=3, saturation=8,
      why="'<!-- Hero Section -->', '{/* Features Section */}', '/* ===== Pricing ===== */' 형태의 블록 주석은 AI가 생성한 템플릿 마크업의 전형적 서명이다.",
      fix={"summary": "라벨 주석 대신 의미 있는 시맨틱 태그와 id/aria-label로 구조를 드러낸다.",
           "steps": ["라벨 주석을 삭제하고 <section aria-labelledby>로 대체한다.", "컴포넌트로 분리되어 있다면 파일명이 라벨 역할을 한다."],
           "example": "<section id=\"how-we-price\" aria-labelledby=\"how-we-price-title\">",
           "effort": "S",
           "directive": "<!-- Hero Section --> 류의 섹션 라벨 주석 금지."})
def cod_labels(ctx):
    c, ev = ctx.grep(r"<!--\s*(?:=+\s*)?[A-Z][\w &/-]{1,30}\s+(?:Section|Area|Container|Wrapper)\s*(?:=+\s*)?-->|"
                     r"\{/\*\s*[A-Z][\w &/-]{1,30}\s+Section\s*\*/\}|/\*\s*=+\s*[A-Z][\w &/-]{1,30}\s*=+\s*\*/", "markup", "style", "script", flags=0)
    if c:
        return Result(c, ev, f"섹션 라벨 주석 {c}개")


@rule(id="COD-04", title="console.log 잔존", category="code", kind="quality",
      weight=1, drivers=["P3"], applies=["web", "game"], threshold=3, saturation=15,
      why="디버그 로그가 그대로 남아 있으면 정리 단계를 거치지 않았다는 신호다.",
      fix={"summary": "console.log를 제거하거나 개발 모드 전용 로거로 감싼다.",
           "steps": ["eslint no-console 규칙을 켠다.", "빌드 시 drop_console 옵션을 사용한다."],
           "example": "// eslint.config.js\nrules: { 'no-console': ['warn', { allow: ['error'] }] }",
           "effort": "S",
           "directive": "console.log 남기지 말 것."})
def cod_console(ctx):
    c, ev = ctx.grep(r"\bconsole\.log\(", "script", flags=0)
    if c:
        return Result(c, ev, f"console.log {c}개")


@rule(id="COD-05", title="CDN 즉석 스택 (Tailwind Play CDN, Babel standalone)", category="code", kind="fingerprint",
      weight=2, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=2,
      why="cdn.tailwindcss.com, @babel/standalone + type=\"text/babel\"는 채팅창에서 바로 미리보기 가능한 단일 HTML을 만들 때 AI가 쓰는 방식이다. 프로덕션용이 아니며(성능·FOUC) 결과물이 '일회용 데모'로 보인다.",
      fix={"summary": "빌드 도구(Vite 등)로 옮겨 Tailwind/React를 빌드 타임에 처리한다.",
           "steps": ["npm create vite@latest 로 프로젝트를 만들고 코드를 컴포넌트로 옮긴다.", "Tailwind는 CLI/플러그인으로 빌드해 사용하지 않는 클래스를 제거한다."],
           "example": "npm create vite@latest my-site -- --template react-ts\nnpm i -D tailwindcss @tailwindcss/vite",
           "effort": "M",
           "directive": "Tailwind Play CDN, Babel standalone 사용 금지. 빌드 파이프라인 사용."})
def cod_cdn(ctx):
    c, ev = ctx.grep(r"cdn\.tailwindcss\.com|@babel/standalone|babel\.min\.js|type\s*=\s*[\"']text/babel[\"']", "markup")
    if c:
        return Result(c, ev, f"즉석 CDN 스택 {c}곳")


@rule(id="COD-06", title="인라인 style 남발", category="code", kind="quality",
      weight=1, drivers=["P5"], applies=["web"], threshold=20, saturation=60,
      why="인라인 스타일이 대량으로 흩어져 있으면 일관된 디자인 규칙이 없다는 뜻이고, 미세하게 다른 간격·색이 섞인다.",
      fix={"summary": "반복되는 인라인 스타일을 클래스/토큰으로 추출한다.",
           "steps": ["style= 값을 빈도순으로 정리해 공통 클래스로 만든다."],
           "example": "style=\"margin-top:24px;color:#666\" → class=\"mt-6 text-muted\"",
           "effort": "M",
           "directive": "인라인 style 대신 토큰 기반 클래스 사용."})
def cod_inline(ctx):
    if ctx.rendered_dom:
        return None
    c, ev = ctx.grep(r"\sstyle\s*=\s*[\"']", "markup", max_ev=3)
    if c:
        return Result(c, ev, f"인라인 style {c}개")
