"""Scoring model.

1. Each finding contributes  evidence = weight(1..5) × strength(0..1).
2. Category score  = 100 · (1 − e^(−Σevidence / K_CAT))        — saturating: many weak
   signals add up, but no single category can exceed 100.
3. Slop Index      = 0.3 · weighted-mean(categories) + 0.4 · mean(top-3) + 0.3 · max(category)
                     + convergence bonus (+4 per extra category ≥ 45 beyond two, max +12)
   People judge slop by the *worst* things they notice and by signals *converging*
   across dimensions, so the index leans on the top categories and rewards co-occurrence.
4. Two axes (reported separately):
     Genericness   (fingerprint rules) — "looks like every other AI output"
     Effort deficit(quality rules)     — "looks finished but isn't"
   AI slop = high on both.
5. Optional visual review (rubric answered by a multimodal agent) is blended in:
     final = (1 − a) · static + a · visual,  a = 0.45 × answered_ratio
"""
import math
from collections import defaultdict

from .model import CATEGORIES, DRIVERS

K_CAT = 6.0
K_AXIS = 12.0

CAT_WEIGHTS = {
    "web": {"visual": 1.2, "layout": 1.0, "copy": 1.2, "imagery": 0.9, "ux": 1.0, "code": 0.5, "a11y": 0.6, "audio": 0.3},
    "game": {"visual": 1.0, "copy": 0.4, "imagery": 1.2, "ux": 0.5, "code": 0.4, "game": 1.4, "gametech": 0.8, "a11y": 0.3, "audio": 1.3},
}

VERDICTS = [
    (0, 20, "CRAFTED", "의도가 보이는 결과물", "사람의 결정이 곳곳에 보입니다. 슬롭 신호가 거의 없습니다."),
    (20, 40, "MOSTLY_CLEAN", "경미한 슬롭 신호", "대체로 괜찮지만 기본값 흔적이 일부 남아 있습니다. 빠른 수정만으로 충분합니다."),
    (40, 60, "SLOP_LEANING", "슬롭 경향", "여러 영역에서 AI 기본값이 보입니다. 사용자는 '어디서 본 듯하다'고 느낄 가능성이 큽니다."),
    (60, 80, "AI_SLOP", "AI 슬롭", "생성 결과를 거의 그대로 쓴 것으로 인식됩니다. 핵심 영역의 재설계가 필요합니다."),
    (80, 101, "HEAVY_SLOP", "심각한 AI 슬롭", "거의 모든 영역이 AI 기본값과 가짜 완성도로 채워져 있습니다. 방향 설정부터 다시 시작하세요."),
]


def verdict_for(score):
    for lo, hi, code, label, desc in VERDICTS:
        if lo <= score < hi:
            return {"code": code, "label": label, "description": desc}
    return {"code": "HEAVY_SLOP", "label": VERDICTS[-1][3], "description": VERDICTS[-1][4]}


def _sat(raw, k):
    return 100.0 * (1.0 - math.exp(-raw / k))


def category_scores(findings, kind, fp_factor=1.0):
    raw = defaultdict(float)
    for f in findings:
        if f.rule.source != "visual":
            raw[f.rule.category] += f.rule.weight * f.strength * (fp_factor if f.rule.kind == "fingerprint" else 1.0)
    cats = CAT_WEIGHTS[kind].keys()
    return {c: round(_sat(raw[c], K_CAT), 1) for c in cats}


def static_index(cat_scores, kind):
    w = CAT_WEIGHTS[kind]
    mean = sum(w[c] * cat_scores[c] for c in w) / sum(w.values())
    top = sorted(cat_scores.values(), reverse=True)[:3]
    topmean = sum(top) / max(1, len(top))
    hot = sum(1 for v in cat_scores.values() if v >= 45)
    bonus = min(12.0, max(0, hot - 2) * 4.0)
    peak = max(cat_scores.values()) if cat_scores else 0.0
    return round(min(100.0, 0.3 * mean + 0.4 * topmean + 0.3 * peak + bonus), 1), round(bonus, 1)


def axes(findings, fp_factor=1.0):
    g = sum(f.rule.weight * f.strength for f in findings if f.rule.kind == "fingerprint") * fp_factor
    e = sum(f.rule.weight * f.strength for f in findings if f.rule.kind == "quality")
    return axes_from(round(_sat(g, K_AXIS), 1), round(_sat(e, K_AXIS), 1))


def axes_from(G, E):
    if G >= 45 and E >= 45:
        q = ("TYPICAL_SLOP", "전형적 AI 슬롭", "흔한 기본값 + 덜 만든 완성도. 둘 다 고쳐야 합니다.")
    elif G >= 45:
        q = ("POLISHED_TEMPLATE", "세련된 템플릿", "완성도 결함보다 '어디서 본 듯한' 기본값 문제가 큽니다. 브랜드·디자인 결정이 필요합니다.")
    elif E >= 45:
        q = ("ROUGH_ORIGINAL", "덜 만든 결과물", "기본값 흔적보다 '동작·마무리가 비어 있는' 문제가 큽니다. 완성도부터 채우세요.")
    else:
        q = ("INTENTIONAL", "의도된 결과물", "기본값과 가짜 완성도가 적습니다.")
    return {"genericness": G, "effort_deficit": E, "quadrant": {"code": q[0], "label": q[1], "description": q[2]}}


def driver_scores(findings):
    raw = defaultdict(float)
    for f in findings:
        share = f.rule.weight * f.strength / max(1, len(f.rule.drivers))
        for d in f.rule.drivers:
            raw[d] += share
    return {d: {"name": DRIVERS[d]["name"], "en": DRIVERS[d]["en"], "score": round(_sat(raw[d], K_CAT), 1)} for d in DRIVERS}


def visual_score(answers):
    """answers: list of (Rule, value 0..1 or None)"""
    tot_w = sum(r.weight for r, v in answers if v is not None)
    if not tot_w:
        return None
    return round(100.0 * sum(r.weight * v for r, v in answers if v is not None) / tot_w, 1)


def confidence(ctx, visual_ratio=0.0, reviewed=False, review_meta=None, agreement=None, frame_coverage=None, index=None):
    pts, reasons = 0, []
    if reviewed:
        pts += 2.5
        m = review_meta or {}
        if m.get("knew_expected"):
            pts -= 1
            reasons.append("리뷰어가 기대 판정을 미리 알고 있었음 → 독립 판정 아님")
        if not m.get("blind"):
            pts -= 0.5
            reasons.append("측정 결과를 본 뒤 리뷰함(블라인드 아님) → 측정에 끌려갔을 수 있음")
        if frame_coverage is not None and frame_coverage < 0.5:
            pts -= 0.5
            reasons.append(f"원본 프레임 중 {frame_coverage:.0%}만 메모함")
        if agreement and agreement.get("conflict"):
            pts -= 1
            reasons.append(f"리뷰와 측정이 {abs(agreement['gap']):.0f}점 차이 → 근거 재확인 필요")
    else:
        reasons.append("지각 리뷰(사람·에이전트가 화면/소리를 보고 판단) 없음 → 점수는 잠정치")
    if getattr(ctx, "perception", None):
        pts += 1
    if ctx.by_role("markup"):
        pts += 1
    else:
        reasons.append("마크업 파일 없음")
    if ctx.word_count >= 150:
        pts += 1
    else:
        reasons.append(f"보이는 텍스트가 적음({ctx.word_count}단어)")
    if ctx.by_role("style") or ctx.has(r"class(Name)?=", "markup"):
        pts += 1
    if ctx.kind == "game" and ctx.by_role("script", "engine"):
        pts += 1
    if ctx.images:
        pts += 0.5
    if ctx.render and ctx.render.get("ok"):
        pts += 1.5
    else:
        reasons.append("렌더 측정 없음 → 실제 색·대비·클릭·모바일·게임 런타임은 추정치")
    if visual_ratio > 0:
        pts += 2 * min(1.0, visual_ratio / 0.6)
        if visual_ratio < 0.6:
            reasons.append(f"시각 검토 일부만 응답({visual_ratio:.0%})")
    else:
        reasons.append("시각 검토(스크린샷 루브릭) 미제출 → 이미지 품질·레이아웃 감각은 반영 안 됨")
    if index is not None and any(abs(index - b) < 4 for b in (20, 40, 60, 80)):
        reasons.append(f"점수 {index:.0f}가 판정 경계 근처 → 인접 판정과 구분이 약함")
    level = "high" if pts >= 4 else "medium" if pts >= 2.5 else "low"
    # coverage can't make up for a non-independent or contradicted judgment
    m = review_meta or {}
    if level == "high" and reviewed and (m.get("knew_expected") or (agreement and agreement.get("conflict"))):
        level = "medium"
    if level == "high" and not reviewed and ctx.kind == "game":
        level = "medium"  # game measurements alone did not separate AI from human work in validation
    return {"level": level, "label": {"high": "높음", "medium": "보통", "low": "낮음"}[level], "limits": reasons}


def category_labels():
    return CATEGORIES


def craft_score(ctx):
    """Measured counter-evidence: details that show deliberate human decisions (0–100) + readable evidence.
    Professional sites (e.g. Stripe) can share surface patterns with AI templates — the original that AI imitates —
    but they also carry bespoke fonts, motion curves, illustration and typographic detail that templates lack."""
    r = ctx.render if ctx.render and ctx.render.get("ok") else None
    c = ((r or {}).get("desktop") or {}).get("craft")
    if not c:
        return 0.0, []
    pts, ev = 0.0, []
    if c.get("customFonts"):
        pts += 20; ev.append("커스텀 폰트 " + ", ".join(c["customFonts"][:3]))
    if c.get("bespokeEasings"):
        pts += min(20, c["bespokeEasings"] * 4); ev.append(f"직접 정의한 모션 곡선 {c['bespokeEasings']}종")
    if c.get("gridSystems", 0) > 3:
        pts += min(15, (c["gridSystems"] - 3) * 2); ev.append(f"레이아웃 그리드 {c['gridSystems']}종")
    if c.get("typeFeatures"):
        pts += 15 if c["typeFeatures"] >= 50 else 8; ev.append(f"OpenType/가변폰트 설정 {c['typeFeatures']}곳")
    if c.get("svgIllustrations"):
        pts += min(20, c["svgIllustrations"] * 4); ev.append(f"SVG 일러스트 {c['svgIllustrations']}개")
    vis = (c.get("bigImages") or 0) + (c.get("videos") or 0)
    if vis:
        pts += min(10, vis * 3)
    return min(100.0, pts), ev


def attenuation(craft):
    """Fingerprint evidence counts less when deliberate craft is visible (max −60%)."""
    return 1.0 - 0.6 * craft / 100.0
