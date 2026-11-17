"""Perception review — the judgment layer.

Whether something *is* AI slop is a human call. Measurements explain *why* it feels that way.
A multimodal agent (or a person) looks at the sheets SlopLens produced — screens, gameplay frames,
asset sheet, recorded sound analysis — and answers each sense with:

  level 0–4   0 = 공들인 결과물, 1 = 사소함, 2 = 눈에 띔, 3 = 슬롭으로 느껴짐, 4 = 명백한 슬롭
  evidence    which sheet / frame / asset / sound shows it (be concrete: "frame-sheet 2번 오른쪽 패널")
  why         why a person feels it (one sentence, in terms of perception, not code)
  fix         the most effective fix

C1 is the counter-evidence: how much deliberate craft is visible (0 = none … 4 = clearly crafted).
"""
import os

from .scoring import craft_score

SENSES = [
    # id, title, question, weight web, weight game
    ("S1", "첫인상 (3초)", "처음 3초에 '어디서 본 AI 생성물' 느낌이 드는가? 무엇 때문인가?", 1.5, 1.5),
    ("S2", "시각 정체성·아트 디렉션", "이 작품만의 결정(팔레트, 형태 언어, 일러스트, 화면 구성)이 보이는가, 장르/템플릿의 평균값인가?", 1.3, 1.3),
    ("S3", "에셋 품질·일관성", "에셋 시트에서 생성 아티팩트(가짜 픽셀아트, 뭉개진 디테일), 스타일 혼재, 해상도 불일치가 보이는가?", 1.0, 1.3),
    ("S4", "UI·타이포 기본값", "엔진/프레임워크 기본 폰트·UI 스킨·컴포넌트가 그대로 보이는가? 정보 위계가 설계돼 있는가?", 1.0, 1.0),
    ("S5", "사운드", "효과음이 행동마다 다른 질감인가, 단음 비프·반복인가? 음악이 상황과 맞물리는가? (웹은 보통 na)", 0.2, 1.3),
    ("S6", "움직임·피드백 (게임필)", "입력에 대한 반응·연출(타격감, 전환, 마이크로인터랙션)이 있는가, 숫자만 바뀌는가?", 0.7, 1.3),
    ("S7", "카피·목소리·내용", "글이 구체적이고 누가 썼는지 느껴지는가, 상투어·설명 과잉인가?", 1.0, 0.6),
    ("S8", "실체·동작", "보이는 것이 실제로 동작하고 실제 내용인가 (죽은 버튼, 가짜 데이터, 미완성 화면)?", 1.0, 1.0),
    ("S9", "AI 생성 이미지 처리", "AI 생성 그림이 보인다면 생성기 출력 그대로인가(매끈한 광택, 구석까지 고르게 깔린 과한 디테일, 의미 없는 장식·뭉개진 글자, "
           "장마다 다른 조명·색감, 다른 에셋과 안 맞는 화풍), 아니면 화풍·팔레트·조명을 맞춰 다듬었나? "
           "4 = 원본 그대로의 이질감, 2 = 일부 다듬음, 0 = 한 아트 방향으로 통합됨. AI 그림이 없으면 na.", 0.8, 1.3),
]
CRAFT = ("C1", "공들인 흔적 (반대 증거)", "사람이 의도적으로 결정했다고 느껴지는 디테일이 얼마나 보이는가? (0 없음 … 4 매우 많음)")
LEVEL_WORDS = {0: "공들인 결과물", 1: "사소함", 2: "눈에 띔", 3: "슬롭으로 느껴짐", 4: "명백한 슬롭"}
WORD_TO_LEVEL = {"yes": 3, "partial": 2, "no": 0}

# which measured categories explain which sense (for the "why it feels like slop" report)
# generated-art handling has its own sense (raw vs. worked-over), not general asset quality
RULE_SENSE = {"ART-03": "S9", "ART-04": "S9", "IMG-01": "S9", "IMG-03": "S9"}
CATEGORY_SENSE = {"visual": "S2", "layout": "S2", "imagery": "S3", "audio": "S5", "game": "S6", "gametech": "S6",
                  "copy": "S7", "ux": "S8", "a11y": "S8", "code": "S8"}


def review_frames(res):
    """Every frame / slice the reviewer should open at original size."""
    ctx = res.ctx
    p = getattr(ctx, "perception", None) or {}
    r = ctx.render if ctx.render and ctx.render.get("ok") else {}
    cap = (getattr(ctx, "unity", None) or {}).get("capture") or {}
    sh = (r or {}).get("screenshots") or {}
    frames = [sh[k] for k in ("desktop", "mobile") if sh.get(k)] + list(sh.get("game") or []) + list(cap.get("frames") or [])
    return frames + [x["file"] for x in (p.get("slices") or [])]


def normalize_meta(meta):
    m = meta if isinstance(meta, dict) else {}
    return {"reviewer": str(m.get("reviewer", ""))[:80], "blind": bool(m.get("blind", False)),
            "knew_expected": bool(m.get("knew_expected", False))}


def protocol_markdown(res, blind=False):
    """What the reviewing agent should look at, and how to answer.
    blind=True hides every measured interpretation so the reviewer judges from the screens first (no anchoring)."""
    ctx = res.ctx
    kind = ctx.kind
    p = getattr(ctx, "perception", None) or {}
    r = ctx.render if ctx.render and ctx.render.get("ok") else {}
    cap = (getattr(ctx, "unity", None) or {}).get("capture") or {}
    L = [f"# SlopLens 지각 리뷰 — {('게임' if kind == 'game' else '웹사이트')}", "",
         "AI 슬롭인지는 사람이 판단합니다. 당신(리뷰어)은 **사람의 눈과 귀를 대신**해 아래 자료를 직접 보고, 감각별로 왜 그렇게 느껴지는지 답하세요.",
         "측정값은 근거 후보일 뿐입니다. 화면이 실제로 공들여 보이면 측정값과 달라도 그렇게 답하세요.", ""]
    if blind:
        L += ["> **블라인드 리뷰**: 측정 결과(의심 규칙, 사운드 태그, 공들인 흔적 점수)를 숨겼습니다. 화면만 보고 먼저 판단하세요. "
              "제출 후 `--blind` 없이 프로토콜을 다시 열어 측정과 비교할 수 있습니다. 제출할 때 `meta.blind`를 true로 두세요.", ""]
    L += [
         "## 1. 볼 자료 — 반드시 한 장씩 원본으로 여세요",
         "시트(썸네일 모음)는 전체 흐름을 보는 용도입니다. **작은 글자·색·디테일은 시트에서 보이지 않으므로**, 아래 프레임과 조각 이미지를 "
         "**하나씩 원본 크기로 열어** 각각 무엇이 보이는지 `frames` 메모로 남긴 뒤 감각별 답을 쓰세요.", ""]
    sheets = p.get("sheets") or {}
    if sheets.get("frames"):
        L.append(f"- 개요: 화면 시트 `{sheets['frames']}`")
    if sheets.get("assets"):
        L.append(f"- 개요: 에셋 시트 `{sheets['assets']}` (아이콘·스프라이트 일관성)")
    sh = (r or {}).get("screenshots") or {}
    frames = [sh[k] for k in ("desktop", "mobile") if sh.get(k)] + list(sh.get("game") or []) + list(cap.get("frames") or [])
    slices = [x["file"] for x in (p.get("slices") or [])]
    fmeta = {os.path.basename(f.get("file", "")): f for f in (p.get("frames") or [])}
    L.append("")
    L.append(f"**원본 확인 목록 ({len(frames) + len(slices)}장)**")
    for i, f in enumerate(frames + slices, 1):
        m = fmeta.get(os.path.basename(f), {})
        size = f" · {m.get('w')}×{m.get('h')}" if m.get("w") else ""
        L.append(f"{i}. [ ] `{f}`{size}")
    if not frames and not slices:
        L.append("- (자동 수집된 화면이 없습니다 — 직접 스크린샷을 찍어 판단하세요)")
    texts = getattr(ctx, "screen_texts", None) or []
    if texts:
        L += ["", f"**화면에 보이는 문구 {len(texts)}개** (원본 프레임과 대조해 쓸데없는 문구·상투 문구·개발용 문구를 확인)"]
        L += [f"- {x['t'][:80]}" for x in texts[:40]]
    L += ["", "## 2. 들을 자료 (측정 요약)"]
    snd = ((r or {}).get("game") or {}).get("sound")
    if snd:
        L.append(f"- 웹 런타임: 오실레이터 {snd.get('oscillatorPlays')}회 {snd.get('oscillatorTypes')}, 샘플 {snd.get('samplePlays')}회, "
                 f"필터 {snd.get('filters')} · 리버브 {snd.get('reverbs')}, 음색 종류 {snd.get('distinctSynthVoices')}")
    if cap.get("soundEvents") is not None:
        ev = cap.get("soundEvents") or []
        clips = {}
        for e in ev:
            clips[e["clip"]] = clips.get(e["clip"], 0) + 1
        L.append(f"- Unity 런타임: 사운드 재생 {len(ev)}회, 클립별 {dict(sorted(clips.items(), key=lambda x: -x[1])[:8])}" + (" (FMOD 사용: Unity 녹음에 FMOD 소리는 포함 안 됨)" if cap.get("fmod") else ""))
    for a in (p.get("audio") or [])[:12]:
        if a.get("error"):
            continue
        tags = "" if blind else " · " + (", ".join(a.get("tags") or []) or "특이점 없음")
        L.append(f"- `{a.get('file')}` {a.get('duration')}s · 순음도 {a.get('tonalPurity')} · 피크 {a.get('spectralPeaks')}{tags}")
    if p.get("unity_mix"):
        m = p["unity_mix"]
        L.append(f"- Unity 플레이 녹음 믹스: {m.get('duration')}s · 무음 {m.get('silenceShare')} · {', '.join(m.get('tags') or [])}")
    if not snd and not p.get("audio") and not cap:
        L.append("- (분석된 사운드 없음)")
    craft, cev = craft_score(ctx)
    if blind:
        L += ["", "## 3. 측정이 가리키는 의심 지점", "- (블라인드 리뷰: 숨김)"]
    else:
        L += ["", "## 3. 측정이 가리키는 의심 지점 (확인용)"]
        for f in res.findings[:10]:
            L.append(f"- [{f.rule.id}] {f.rule.title} — {f.detail}")
        if cev:
            L.append(f"- 공들인 흔적(실측) {craft:.0f}/100: " + ", ".join(cev))
    senses = [s for s in SENSES if not (kind == "web" and s[0] == "S5")]
    L += ["", "## 4. 답할 항목", "", "레벨: 0 공들인 결과물 · 1 사소함 · 2 눈에 띔 · 3 슬롭으로 느껴짐 · 4 명백한 슬롭. 볼 수 없었던 항목은 `na`.", ""]
    for sid, title, q, *_ in senses:
        L.append(f"- **{sid} {title}** — {q}")
    L.append(f"- **{CRAFT[0]} {CRAFT[1]}** — {CRAFT[2]}")
    L += ["", "## 5. 제출 형식 (`slop_submit_review` 또는 CLI `scan … --review review.json`)", "```json", "{", f'  "scan_id": "{res.id}",', '  "review": [']
    L += [f'    {{"id": "{sid}", "level": 2, "evidence": "어떤 시트/프레임/에셋의 어디", "why": "사람이 왜 그렇게 느끼는지", "fix": "가장 효과적인 해결"}},' for sid, *_ in senses]
    L += [f'    {{"id": "C1", "level": 1, "evidence": "공들인 디테일 예시"}}', "  ],",
          '  "frames": [', '    {"file": "프레임 파일명", "note": "이 화면에서 실제로 보이는 것 (글자·색·빈칸·어색한 점·공들인 점)"}', "  ],",
          '  "meta": {"reviewer": "리뷰어 이름/모델", "blind": ' + ("true" if blind else "false") + ', "knew_expected": false}', "}", "```",
          "", "`knew_expected`: 리뷰 전에 이 작품이 슬롭인지 아닌지(제작자·사용자 판단)를 알고 있었다면 true. 리포트의 신뢰도에 반영됩니다."]
    return "\n".join(L)


def normalize_frames(frames):
    out = []
    for f in frames or []:
        if isinstance(f, dict) and f.get("note"):
            out.append({"file": os.path.basename(str(f.get("file", "")))[:120], "note": str(f["note"])[:500]})
    return out


def normalize(items, kind):
    """Accept {'id','level'|'answer','evidence','why','fix'} → list of clean dicts."""
    valid = {s[0] for s in SENSES} | {CRAFT[0]}
    out, unknown = [], []
    for it in items or []:
        sid = str(it.get("id", "")).upper().strip()
        if sid not in valid:
            unknown.append(sid)
            continue
        lv = it.get("level", it.get("answer"))
        if isinstance(lv, str):
            lv = lv.strip().lower()
            lv = None if lv in ("na", "n/a", "skip", "") else WORD_TO_LEVEL.get(lv, lv)
        try:
            lv = None if lv is None else max(0, min(4, int(float(lv))))
        except (TypeError, ValueError):
            lv = None
        out.append({"id": sid, "level": lv, "evidence": str(it.get("evidence", ""))[:300], "why": str(it.get("why", ""))[:400],
                    "fix": str(it.get("fix", ""))[:400]})
    return out, unknown


def perception_index(review, kind):
    """0–100 from the reviewer's levels, minus credit for visible craft. None if nothing answered."""
    w = {s[0]: (s[3] if kind == "web" else s[4]) for s in SENSES}
    num = den = 0.0
    craft = None
    for it in review:
        if it["level"] is None:
            continue
        if it["id"] == "C1":
            craft = it["level"]
            continue
        num += w.get(it["id"], 1.0) * it["level"] * 25
        den += w.get(it["id"], 1.0)
    if not den:
        return None, craft
    v = num / den - (craft or 0) * 4
    return round(max(0.0, min(100.0, v)), 1), craft


def title_of(sid):
    for s in SENSES + [CRAFT]:
        if s[0] == sid:
            return s[1]
    return sid
