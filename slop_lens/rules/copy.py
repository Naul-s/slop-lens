"""Copy / content signals: LLM vocabulary density, placeholders, fabricated proof."""
import re
from collections import Counter

from ..lexicon import CLICHE_EN, CLICHE_KO, CTA_GENERIC, HEADLINE_FORMULAS, STOCK_NAMES
from ..model import Evidence, Result, rule

_CLICHE_RX = re.compile(r"\b(?:" + "|".join(CLICHE_EN) + r")\b|(?:" + "|".join(CLICHE_KO) + r")", re.I)


@rule(id="CPY-01", title="AI 상투어 밀도 (elevate·seamless·혁신적인·원활한…)", category="copy", kind="fingerprint",
      weight=4, drivers=["P1", "P2"], applies=["web", "game"], threshold=3, saturation=3,
      why="LLM은 마케팅 문구에서 'seamless, elevate, unlock, 혁신적인, 원활한, 차세대' 같은 단어를 사람보다 수 배 높은 빈도로 쓴다. "
          "단어 하나하나는 문제가 아니지만, 짧은 카피에 몰려 있으면 독자는 즉시 '아무 말도 안 하는 글'로 느낀다.",
      fix={"summary": "모든 추상 형용사를 '구체적 사실(숫자, 대상, 상황)'로 바꾼다. 상투어 하나당 증거 하나.",
           "steps": ["리포트에 나온 상투어를 전부 찾아 표시한다.",
                     "각 문장에 '누가, 무엇을, 얼마나'가 들어가도록 다시 쓴다 (예: '원활한 협업' → '댓글 달면 담당자에게 슬랙 알림').",
                     "형용사를 지웠을 때 문장이 무너지면, 그 문장은 원래 내용이 없었던 것 → 삭제한다.",
                     "브랜드 보이스 3원칙(예: 짧게, 반말, 숫자 먼저)을 정하고 전체 카피를 통일한다."],
           "example": "Before: \"Elevate your workflow with seamless, AI-powered collaboration.\"\n"
                      "After : \"회의록을 붙여넣으면 할 일 7개가 담당자별로 나뉘어 나옵니다. 평균 40초.\"",
           "effort": "M",
           "directive": "elevate/seamless/unlock/empower/cutting-edge/혁신적인/원활한/차세대/극대화 같은 추상 마케팅 어휘 금지. 모든 주장은 구체적 숫자·대상·상황으로 쓸 것."})
def cpy_cliche(ctx):
    vt = ctx.visible_text
    words = max(1, ctx.word_count)
    hits = [m.group(0).lower() for m in _CLICHE_RX.finditer(vt)]
    n = len(hits)
    if n < 3:
        return None
    density = n / (words / 1000.0)
    if words >= 300 and density < 6:
        return None
    strength = min(1.0, max(0.35, density / 25.0)) if words >= 150 else min(1.0, 0.3 + n * 0.1)
    c, ev = ctx.grep(_CLICHE_RX, "markup", "script", flags=0, max_ev=6)
    top = Counter(hits).most_common(8)
    return Result(n, ev, f"상투어 {n}회 / {words}단어 (1000단어당 {density:.1f}) · 상위: " + ", ".join(f"{k}×{v}" for k, v in top),
                  strength=strength)


@rule(id="CPY-02", title="플레이스홀더·더미 텍스트 잔존", category="copy", kind="quality",
      weight=5, drivers=["P3", "P2"], applies=["web", "game"], threshold=1, saturation=4,
      why="Lorem ipsum, 'Your Company', Acme, John Doe, 555 전화번호가 남아 있으면 '아무도 끝까지 확인하지 않았다'는 결정적 증거가 된다. 신뢰가 한 번에 무너진다.",
      fix={"summary": "모든 더미 텍스트·이름·연락처를 실제 내용으로 교체하거나, 내용이 없으면 해당 요소를 삭제한다.",
           "steps": ["리포트의 위치를 따라 더미 텍스트를 전부 교체한다.",
                     "실제 정보가 아직 없다면 블록 자체를 빼는 것이 가짜를 두는 것보다 낫다.",
                     "CI에 `slop-lens scan --fail-over` 또는 grep 검사를 걸어 재발을 막는다."],
           "example": "grep -rniE 'lorem ipsum|your company|acme|john doe|555-' src/",
           "effort": "S",
           "directive": "Lorem ipsum, Your Company, Acme, John Doe, example.com, 555 번호 등 더미 텍스트 절대 금지. 모르면 해당 블록을 만들지 말 것."})
def cpy_placeholder(ctx):
    c, ev = ctx.grep(r"lorem ipsum|dolor sit amet|(?:>|©\s*(?:20\d\d\s*)?)\s*your (?:company|brand|business|product|app)(?: name)?\s*(?:<|\.|,)|>\s*company name\s*<|"
                     r"\bacme(?: corp| inc| co)\b|\b(?:hello|info|contact|support|john|jane|user|name|email|you|your|test|admin)@example\.(?:com|org)\b|"
                     r"\[your [^\]]{2,30}\]|\bjohn doe\b|\bjane doe\b|"
                     r"\b123 main st|\(555\)\s*\d{3}|\b555-\d{4}\b|\b(?:hello|info|contact|support)@(?:company|example|yourcompany|yourdomain|acme)\.com\b|"
                     r"placeholder text|insert (?:text|image|content) here|홍길동|회사명을? 입력|여기에 (?:내용|텍스트|설명)|OOO 회사|주식회사 OO",
                     "markup", "script")
    if c:
        return Result(c, ev, f"더미 텍스트 {c}곳")


@rule(id="CPY-03", title="꾸며낸 사회적 증거 (가짜 후기·통계·별점)", category="copy", kind="quality",
      weight=4, drivers=["P3", "P2"], applies=["web"], threshold=2, saturation=8,
      why="'Sarah Johnson, CEO at TechCorp ★★★★★', '10,000+ happy customers', '99.9% uptime'처럼 출처 없는 숫자와 전형적 이름은 "
          "AI가 빈칸을 채운 흔적이다. 사람들은 이런 후기를 '가짜'로 인지하고 사이트 전체를 불신한다.",
      fix={"summary": "검증 가능한 실제 증거만 남긴다. 없으면 '왜 믿을 수 있는지'를 다른 방식(제작 과정, 데모, 오픈 데이터)으로 보여준다.",
           "steps": ["실제 사용자 후기가 없다면 후기 섹션을 삭제한다.",
                     "후기를 쓴다면 실명·사진·링크(원문 트윗/리뷰) 등 출처를 함께 단다.",
                     "통계는 측정 기간·기준을 명시한다 (예: '2025년 3월 베타 사용자 212명 기준').",
                     "대안: 라이브 데모, 변경 로그, 창업자 소개로 신뢰를 만든다."],
           "example": "<blockquote cite=\"https://x.com/realuser/status/…\">“…”<footer>— @realuser, 프리랜서 디자이너 (원문 링크)</footer></blockquote>",
           "effort": "M",
           "directive": "가짜 후기·가짜 이름(Sarah Johnson 등)·출처 없는 통계(10,000+ users, 99.9%)·별점 금지. 검증 가능한 증거만 사용."})
def cpy_fake_proof(ctx):
    names = r"\b(?:" + "|".join(re.escape(n) for n in STOCK_NAMES if n.isascii()) + r")\b|" + \
            "|".join(re.escape(n) for n in STOCK_NAMES if not n.isascii())
    pats = [
        names,
        r"\b(?:CEO|CTO|COO|Founder|Co-founder|Product Manager|Marketing Director|Head of \w+|Lead Designer|Engineer)\s*(?:at|@|,)\s*"
        r"(?:Tech\w*|\w*Corp|\w+Labs|\w+ Inc|StartupX|InnovateCo|\w+ly|Acme\w*|\w+Solutions|\w+Hub)\b",
        r"★{4,5}|⭐{4,5}|\b4\.[89]\s*/\s*5\b|\b5\.0\s*(?:rating|stars)",
        r"\b\d{1,3}(?:,\d{3})+\+?\s*(?:happy|satisfied|active)?\s*(?:customers|users|clients|companies|teams|developers|creators)\b|"
        r"\b\d{2,3}[kK]\+\s*(?:users|customers|downloads)|\b99\.9+%|\btrusted by (?:over )?\d|\b\d+\+ (?:companies|countries|teams)\b|"
        r"만족도\s*9\d%|\d+만\s*\+?\s*명(?:의)? (?:사용자|고객)|누적 (?:사용자|다운로드)\s*\d",
    ]
    total, ev = 0, []
    for p in pats:
        c, e = ctx.grep(p, "markup", "script", max_ev=3)
        total += c
        ev += e
    if total:
        return Result(total, ev[:6], f"가짜 증거 패턴 {total}곳")


@rule(id="CPY-04", title="공식형 헤드라인 ('The Future of X', 'X, Reimagined')", category="copy", kind="fingerprint",
      weight=3, drivers=["P1"], applies=["web", "game"], threshold=2, saturation=5,
      why="'The future of X', 'X reimagined', 'Everything you need to…', '모든 것을 한 곳에서' 같은 문형은 무엇에든 붙일 수 있는 문장이다. 제품명만 바꿔도 성립한다면 헤드라인이 아니다.",
      fix={"summary": "헤드라인을 '이 제품만 할 수 있는 구체적 약속'으로 바꾼다. 경쟁사 이름을 넣어도 성립하면 다시 쓴다.",
           "steps": ["모든 h1~h3를 나열하고 '다른 제품 이름을 넣어도 말이 되는가?' 테스트를 한다.",
                     "통과하지 못하면 대상(누구) + 결과(무엇이 달라지나) + 구체(숫자/장면)로 다시 쓴다."],
           "example": "Before: \"The Future of Personal Finance\"\nAfter : \"월급날 3분, 이번 달 고정지출이 정리됩니다\"",
           "effort": "S",
           "directive": "'The future of', 'Reimagined', 'Everything you need', '모든 것을 한 곳에서' 같은 범용 헤드라인 금지. 제품 고유의 구체적 약속으로."})
def cpy_headline(ctx):
    rx = re.compile(HEADLINE_FORMULAS, re.I)
    hits = [(t, f, ln) for _l, t, f, ln in ctx.headings if rx.search(t)]
    for d in ctx.html_docs:
        if d.get("title") and rx.search(d["title"]):
            hits.append((d["title"], d["file"], 1))
    if hits:
        return Result(len(hits), [Evidence(f, ln, t[:100]) for t, f, ln in hits[:6]], f"공식형 헤드라인 {len(hits)}개")


@rule(id="CPY-05", title="리듬형 3단 문구·대시 남용 ('Fast. Simple. Secure.')", category="copy", kind="fingerprint",
      weight=2, drivers=["P1"], applies=["web", "game"], threshold=2, saturation=6,
      why="세 단어 끊어치기('Fast. Simple. Secure.'), 'Not just X — it's Y' 구문, 과도한 em dash(—)는 LLM 문체의 대표 리듬이다.",
      fix={"summary": "끊어치기·대시 구문을 일반 문장으로 풀고, 세 가지 나열은 가장 중요한 하나만 남긴다.",
           "steps": ["'A. B. C.' 형태의 문구를 하나의 구체적 문장으로 바꾼다.", "em dash는 쉼표나 마침표로 바꾼다.",
                     "'~가 아니라 ~입니다' 대조 구문을 줄인다."],
           "example": "Before: \"Fast. Secure. Reliable.\"\nAfter : \"1초 안에 결제 완료, 카드 정보는 저장하지 않습니다.\"",
           "effort": "S",
           "directive": "'A. B. C.' 3단 끊어치기, 'Not just X — it's Y' 구문, em dash(—) 남용 금지."})
def cpy_rhythm(ctx):
    vt = ctx.visible_text
    trip = len(re.findall(r"\b[A-Z][a-z]{2,10}\.\s+[A-Z][a-z]{2,10}\.\s+[A-Z][a-z]{2,10}\.", vt))
    trip += len(re.findall(r"(?:^|\s)[가-힣]{1,6}\.\s+[가-힣]{1,6}\.\s+[가-힣]{1,6}\.", vt))
    notjust = len(re.findall(r"\bnot just (?:a|an|another)\b|isn'?t just|more than just|단순한 \S+(?:이|가) 아닌", vt, re.I))
    words = max(1, ctx.word_count)
    dashes = vt.count("—")
    dash_excess = max(0, int(dashes - words / 150))
    score = trip * 2 + notjust + min(3, dash_excess)
    if score >= 2:
        c, ev = ctx.grep(r"\b[A-Z][a-z]{2,10}\.\s+[A-Z][a-z]{2,10}\.\s+[A-Z][a-z]{2,10}\.|not just (?:a|an|another)\b|—", "markup", "script", flags=0, max_ev=5)
        return Result(score, ev, f"3단 끊어치기 {trip}, 'not just' {notjust}, em dash {dashes}")


@rule(id="CPY-06", title="CTA 문구 단조로움 (Get Started / 더 알아보기 반복)", category="copy", kind="fingerprint",
      weight=2, drivers=["P1", "P2"], applies=["web"], threshold=4, saturation=10,
      why="모든 버튼이 'Get Started', 'Learn More', '시작하기'면 버튼을 눌렀을 때 무슨 일이 일어나는지 알 수 없다. 행동 설계가 빠진 기본값이다.",
      fix={"summary": "각 CTA를 '누르면 일어나는 일'로 구체화한다.",
           "steps": ["버튼별로 클릭 후 결과를 적어본다.", "그 결과를 버튼 문구로 쓴다 (예: '시작하기' → '내 카드 내역 불러오기')."],
           "example": "<button>예시 데이터로 30초 체험</button>",
           "effort": "S",
           "directive": "Get Started/Learn More/시작하기/더 알아보기 같은 범용 CTA 금지. 버튼 문구는 클릭 결과를 구체적으로 설명."})
def cpy_cta(ctx):
    rx = re.compile(CTA_GENERIC, re.I)
    hits = [(t, f, ln) for t, f, ln in ctx.buttons if len(t) <= 40 and rx.search(t)]
    labelled = [t for t, _, _ in ctx.buttons if t.strip()]
    if hits and len(hits) / max(1, len(labelled)) < 0.3:
        return None  # a few "Learn more" links among many specific labels is normal
    if hits:
        return Result(len(hits), [Evidence(f, ln, t) for t, f, ln in hits[:5]],
                      "범용 CTA: " + ", ".join(sorted(set(t for t, _, _ in hits))[:6]))
