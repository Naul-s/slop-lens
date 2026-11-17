"""On-screen text rules — what a person actually READS on the rendered page / game screen.

Sources (ctx.screen_texts): rendered DOM text (title + after play), Unity capture text components.
TXT-01 decorative all-caps micro labels · TXT-02 icons with redundant word labels · TXT-03 over-instruction
TXT-04 shortcut-hint lists · TXT-05 dev/placeholder strings on screen · TXT-06 generic taglines / UI clichés
"""
import re

from ..lexicon import CLICHE_EN, CLICHE_KO
from ..model import CLEAN, Evidence, Result, rule


def _texts(ctx):
    t = getattr(ctx, "screen_texts", None)
    return t if t else None


def E(items, n=5):
    return [Evidence(x.get("src", "(화면)"), 0, x["t"][:110]) for x in items[:n]]


LETTERS = re.compile(r"[A-Za-z]")
HANGUL = re.compile(r"[가-힣]")


def _is_caps_label(x):
    t = x["t"]
    words = t.split()
    if x.get("fs") is not None and (x["fs"] > 15 or (x.get("ls") or 0) < 0.5):
        return False  # eyebrow labels are small and letter-spaced; big display type or plain titles are design, not decoration
    return (x.get("up") and LETTERS.search(t) and 1 <= len(words) <= 5 and len(t) <= 40
            and not x.get("btn") and not re.fullmatch(r"[A-Z]{2,5}", t))  # skip acronyms like "FAQ", "BPM"


@rule(id="TXT-01", title="장식용 대문자 라벨 남발 (eyebrow·마이크로 라벨)", category="copy", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=1,
      why="제목 위·패널 위마다 'NEXT-GEN PUZZLE', 'MISSION', 'STAGE SELECT'처럼 자간을 벌린 작은 대문자 라벨이 붙어 있다. 정보는 거의 없고 '세련돼 보이게' 하려는 장식인데, "
          "AI가 만든 랜딩 페이지·게임 UI에서 가장 흔한 문법이라 화면 곳곳에 반복되면 사람들은 바로 템플릿으로 느낀다. 한국어 화면에 영어 대문자 라벨이 섞이면 더 두드러진다.",
      fix={"summary": "정보가 없는 라벨은 지우고, 꼭 필요한 구분은 크기·굵기·여백으로 한다. 남길 라벨은 1화면 1개, 사용자 언어로.",
           "steps": ["화면별 대문자 라벨을 나열하고 '지우면 정보가 사라지는가?'를 확인한다.", "사라지지 않는 라벨은 삭제한다.",
                     "남길 라벨은 한국어로 바꾸고, 제목과 위계를 크기·굵기로 만든다."],
           "example": "<!-- 제거 --> <small class=\"eyebrow\">NEXT-GEN PUZZLE</small>\n<h1>게임 제목</h1>",
           "effort": "S", "directive": "제목 위 장식용 대문자 라벨(eyebrow)·자간 넓힌 마이크로 라벨 금지. 위계는 크기·굵기·여백으로."})
def txt_caps(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    labels = [x for x in T if _is_caps_label(x)]
    words = [x for x in T if LETTERS.search(x["t"])]
    share = len(labels) / max(1, len(words))
    if len(labels) >= 5 and share >= 0.2:
        return Result(1, E(labels, 6), f"화면 문구 {len(words)}개 중 대문자 라벨 {len(labels)}개 ({share:.0%})", strength=min(1.0, 0.4 + share))
    hangul = [x for x in T if HANGUL.search(x["t"])]
    if len(hangul) >= len(T) * 0.5 and len(labels) >= 2:
        # Korean screens with decorative English caps labels stand out even more
        return Result(1, E(labels, 6), f"한국어 화면({len(hangul)}/{len(T)})에 영어 대문자 장식 라벨 {len(labels)}개", strength=min(1.0, 0.5 + 0.1 * len(labels)))
    return CLEAN


ARROW_WORD = re.compile(r"([↑↓←→⬆⬇⬅➡▲▼◀▶]\s*(위|아래|왼쪽|오른쪽|up|down|left|right|이전|다음|prev|next)\b|"
                        r"\b(위|아래|왼쪽|오른쪽|up|down|left|right)\s*[↑↓←→⬆⬇⬅➡▲▼◀▶])", re.I)


@rule(id="TXT-02", title="아이콘·기호에 같은 뜻의 글자 중복 (↑ 위, ← 왼쪽)", category="copy", kind="fingerprint", source="perceive",
      weight=2, drivers=["P1", "P2"], applies=["web", "game"], threshold=2, saturation=4,
      why="화살표·기호 옆에 같은 뜻의 글자를 또 붙였다(↑ 위, ← 왼쪽, ▶ 다음). 기호만으로 충분한 곳에 설명을 덧붙이는 것은 AI가 '친절하게' 만들 때의 습관이고, 화면을 지저분하게 만든다.",
      fix={"summary": "기호만 남기거나, 글자만 남긴다. 조작 안내는 첫 1회만 보여준다.", "steps": ["중복 라벨을 찾아 하나를 지운다.", "접근성용 설명은 aria-label로 옮긴다."],
           "example": "<button aria-label=\"위로 이동\">↑</button>", "effort": "S", "directive": "기호·아이콘에 같은 뜻의 글자를 중복으로 붙이지 말 것."})
def txt_redundant(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    hits = [x for x in T if ARROW_WORD.search(x["t"])]
    return Result(len(hits), E(hits), f"기호+글자 중복 {len(hits)}곳") if hits else CLEAN


INSTRUCT = re.compile(r"(하세요|하십시오|해 ?보세요|해주세요|눌러|누르면|선택하세요|이동하세요|사용하세요|\bpress\b|\bclick\b|\btap\b|\bselect\b.*\bthen\b|\buse\b.*\bto\b|"
                      r"\bhold\b|\bdrag\b|\bswipe\b|then press)", re.I)


KO_IMPERATIVE = re.compile(r"(보세요|하세요|주세요|세요)[.!]?\s*$|(보세요|하세요|세요)[.,!]")
OPERATE = re.compile(r"(눌러|누르면|누르세요|클릭하|탭하|선택하세요|이동하세요|드래그|스와이프|\bpress\b|\bclick\b|\btap\b|\bhold\b|\bdrag\b|\bswipe\b)", re.I)
KO_EXPLAIN = re.compile(r"(합니다|됩니다|않습니다|있습니다)[.]?\s*$")


@rule(id="TXT-03", title="설명·안내문 과잉", category="copy", kind="quality", source="perceive",
      weight=2, drivers=["P2"], applies=["web", "game"], threshold=1, saturation=1,
      why="한 화면에 '~하세요', 'press ~', 'select ~ then ~' 같은 안내문이 여러 개 붙어 있다. 화면이 스스로 설명되지 않아서 글로 메운 것이고, 읽을 것이 많아 피로하다. "
          "게임에서는 '해보며 배우는' 경험을 막는다.",
      fix={"summary": "안내문을 1~2개로 줄이고, 나머지는 화면 구성(강조, 하이라이트, 첫 판 튜토리얼)으로 대신한다.",
           "steps": ["안내문을 모두 나열한다.", "첫 행동을 유도하는 1개만 남긴다.", "필요한 조작은 처음 시도할 때만 짧게 띄우고 사라지게 한다."],
           "example": "", "effort": "M", "directive": "화면마다 안내문을 붙이지 말 것. 화면 구성으로 설명하고 안내는 첫 1회만."})
def txt_instruct(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    if ctx.kind == "web":  # marketing CTAs ("~해 보세요") are normal web copy; only operating instructions count
        hits = [x for x in T if OPERATE.search(x["t"]) and len(x["t"]) >= 6]
    else:
        hits = [x for x in T if (INSTRUCT.search(x["t"]) or KO_IMPERATIVE.search(x["t"])) and len(x["t"]) >= 6]
    if ctx.kind == "game":  # rule-explaining sentences on the play screen also count (web copy normally ends in ~합니다)
        hits += [x for x in T if x not in hits and KO_EXPLAIN.search(x["t"]) and len(x["t"]) >= 15]
    if len(hits) >= 4:
        return Result(1, E(hits), f"안내문 {len(hits)}개", strength=min(1.0, 0.3 + len(hits) * 0.1))
    return CLEAN


KEYHINT = re.compile(r"\b(ENTER|ESC|SPACE|TAB|SHIFT|ARROWS?|WASD|CTRL|[A-Z])\b\s*[:\-·]?\s*(KEY\s+)?(NAVIGATE|CONFIRM|BACK|SELECT|PAUSE|MOVE|JUMP|RESTART|UNDO|CANCEL|"
                     r"이동|확인|뒤로|선택|일시정지|점프|다시|되돌리기|취소)|\((Z|R|ESC|ENTER|SPACE)\)", re.I)


@rule(id="TXT-04", title="단축키·조작 힌트 나열", category="copy", kind="quality", source="perceive",
      weight=2, drivers=["P2"], applies=["web", "game"], threshold=2, saturation=5,
      why="'ARROWS NAVIGATE · ENTER CONFIRM', '되돌리기 (Z)', '다시 시작 (R)'처럼 조작 키가 화면 곳곳에 상시 표시된다. 개발 중 디버그 안내를 그대로 둔 것 같은 인상을 준다.",
      fix={"summary": "조작 힌트는 처음 한 번 또는 설정/도움말로 옮기고, 버튼에는 동작 이름만 남긴다.", "steps": [], "example": "",
           "effort": "S", "directive": "단축키 힌트를 화면에 상시 나열하지 말 것."})
def txt_keyhint(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    hits = [x for x in T if KEYHINT.search(x["t"])]
    return Result(len(hits), E(hits), f"조작 힌트 {len(hits)}곳") if hits else CLEAN


DEVSTR = re.compile(r"\b(unknown|technical verification|verification|debug|placeholder|lorem|sample|test(ing)?|dummy|undefined|null|nan|"
                    r"not implemented|coming soon)\b|\bN/A\b|\{\w+\}|미정|임시|테스트|샘플", re.I)
DEVCAPS = re.compile(r"\b(TODO|TBD|WIP|FIXME)\b")
# a dash standing in for a missing VALUE ("BPM — TIME —", "ACCURACY --", "—"), not a dash used as punctuation in a sentence
BLANKSLOT = re.compile(r"(^|\s)(—|–|--|-)\s*$|(^|\s)(—|–|--)\s+(?=[A-Z][A-Z]{1,}\b)|^\s*[—–-]{1,2}\s*$")


@rule(id="TXT-05", title="개발용·임시 문구가 화면에 노출", category="copy", kind="quality", source="perceive",
      weight=4, drivers=["P3"], applies=["web", "game"], threshold=1, saturation=4,
      why="'Unknown (Test)', 'BPM —', 'COVER —', 'undefined' 같은 개발용 값·빈칸 표시가 그대로 화면에 보인다. "
          "사람은 이것을 '아직 아무도 완성하지 않은 화면'으로 읽고, 나머지가 아무리 정돈돼 보여도 껍데기로 느낀다.",
      fix={"summary": "모든 화면 값을 실제 데이터로 연결하고, 값이 없으면 해당 줄을 숨기거나 의미 있는 기본값을 보여준다.",
           "steps": ["화면에 보이는 '—', Unknown, Test 값을 모두 찾는다.", "데이터를 연결하거나 행을 숨긴다.", "빌드 전 개발용 메타데이터를 제거한다."],
           "example": "bpmLabel.gameObject.SetActive(song.Bpm > 0);", "effort": "S",
           "directive": "개발용·임시 값(Unknown, Test, —, undefined)을 화면에 노출하지 말 것."})
def txt_dev(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    hits = [x for x in T if (DEVSTR.search(x["t"]) or DEVCAPS.search(x["t"]) or BLANKSLOT.search(x["t"])) and len(x["t"]) <= 80]
    return Result(len(hits), E(hits), f"개발용·빈칸 문구 {len(hits)}곳") if hits else CLEAN


TAGLINE = re.compile(r"\b(a|an) (\w+ ){0,2}(game|experience|adventure|journey)\b|\bin motion\b|\bembark\b|\bunleash\b|\bmaster the\b|"
                     r"\bget ready\b|\bare you ready\b|\byour (adventure|journey) (begins|awaits)\b|\blet'?s (go|play)\b|\bwelcome to\b|"
                     r"모험을 (시작|떠나)|당신의 (실력|모험)|준비되셨나요|새로운 (모험|경험)|한계를 넘|도전해 ?보세요", re.I)
_CLICHE = re.compile(r"\b(?:" + "|".join(CLICHE_EN) + r")\b|(?:" + "|".join(CLICHE_KO) + r")", re.I)


@rule(id="TXT-06", title="범용 태그라인·UI 상투 문구 (화면 기준)", category="copy", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1", "P2"], applies=["web", "game"], threshold=1, saturation=3,
      why="'An adventure in motion', 'Your adventure begins', '지금 바로 도전해 보세요'처럼 어떤 게임·서비스에도 붙는 문장이 화면에 있다. "
          "제목을 바꿔도 그대로 성립하는 문장은 아무 정보도 주지 않고, AI가 빈칸을 채운 흔적으로 읽힌다.",
      fix={"summary": "이 작품에만 해당하는 구체적인 한 문장으로 바꾼다 (무엇을 하는지 + 무엇이 다른지).",
           "steps": ["태그라인에 다른 게임 이름을 넣어도 말이 되는지 확인한다.", "말이 되면 고유 메카닉·장면을 넣어 다시 쓴다."],
           "example": "'An adventure in motion' → '무너지는 탑을 밧줄 하나로 오르는 클라이밍 퍼즐'", "effort": "S",
           "directive": "어떤 작품에도 붙는 범용 태그라인·상투 문구 금지. 이 작품만의 구체적인 문장으로."})
def txt_tagline(ctx):
    T = _texts(ctx)
    if T is None:
        return None
    hits = [x for x in T if TAGLINE.search(x["t"]) or _CLICHE.search(x["t"])]
    # a big real web page can carry one stock phrase; only repeated use reads as filler
    if ctx.kind == "web" and (len(hits) < 2 or len(hits) < 0.02 * len(T)):
        return CLEAN
    return Result(len(hits), E(hits), f"범용 태그라인·상투 문구 {len(hits)}곳") if hits else CLEAN
