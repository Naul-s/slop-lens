"""Scan orchestration: context → rules → findings → scores → fix plan."""
import datetime as _dt
import glob
import uuid
import os
import re

from . import scoring
from .context import build_context
from .model import CLEAN, EFFORT_COST, EFFORT_LABEL, VERSION, Finding
from .rubric import RUBRIC
from .rules import get_rules

ANSWER_VALUE = {"yes": 1.0, "y": 1.0, "true": 1.0, "partial": 0.5, "some": 0.5, "no": 0.0, "n": 0.0, "false": 0.0,
                "na": None, "n/a": None, "skip": None}


class ScanResult:
    def __init__(self, ctx, findings, errors):
        self.ctx = ctx
        self.kind = ctx.kind
        self.static_findings = findings
        self.visual_findings = []
        self.visual_answers = []  # (rule, value, note)  — legacy yes/no rubric
        self.review = []          # perception review items (see review.py)
        self.revealed = False     # measurements were shown: a later review cannot count as blind
        self.attachments = []     # screenshots the reviewer took by hand (review.attach_images)
        self.errors = errors
        self.created = _dt.datetime.now().isoformat(timespec="seconds")
        self.id = f"sl-{uuid.uuid4().hex[:8]}"
        self.recompute()

    # ------------------------------------------------------------------
    @property
    def findings(self):
        return sorted(self.static_findings + self.visual_findings, key=lambda f: -f.impact)

    def recompute(self):
        from . import review as _rv
        self.craft, self.craft_evidence = scoring.craft_score(self.ctx)
        fpf = scoring.attenuation(self.craft) if self.kind == "web" else 1.0
        self.fp_factor = round(fpf, 2)
        self.categories = scoring.category_scores(self.static_findings, self.kind, fpf)
        self.evidence_index, self.convergence_bonus = scoring.static_index(self.categories, self.kind)
        self.static_index = self.evidence_index
        self.axes = scoring.axes(self.findings, fpf)
        self.drivers = scoring.driver_scores(self.findings)
        vals = [(r, v) for r, v, _ in self.visual_answers]
        self.visual_index = scoring.visual_score(vals)
        self.perception_index, self.review_craft = _rv.perception_index(self.review, self.kind)
        self.review_missing = _rv.missing_for_verdict(self.review) if self.review else []
        if self.review_missing:
            self.perception_index = self.review_craft = None  # an incomplete review neither scores nor confirms
        self.review_unsupported = _rv.unsupported(self.review)
        if self.perception_index is not None:
            # the reviewer's senses also define the two axes (sameness vs. unfinished)
            lv = {it["id"]: it["level"] for it in self.review if it["level"] is not None}
            g = [lv[k] for k in ("S1", "S2", "S4") if k in lv]
            e = [lv[k] for k in ("S3", "S5", "S6", "S8", "S9") if k in lv]
            G = round(0.65 * sum(g) / len(g) * 25 + 0.35 * self.axes["genericness"], 1) if g else self.axes["genericness"]
            E = round(0.65 * sum(e) / len(e) * 25 + 0.35 * self.axes["effort_deficit"], 1) if e else self.axes["effort_deficit"]
            if self.review_craft and self.review_craft >= 3:
                G = round(G * (1 - 0.15 * self.review_craft), 1)
            self.axes = scoring.axes_from(G, E)
        if self.perception_index is not None:
            # people judge slop by what they see and hear: the review leads, measurements support
            self.index = round(0.65 * self.perception_index + 0.35 * self.evidence_index, 1)
            self.status = "확정"
            self.visual_blend = 0.65
        elif self.visual_index is not None and self.kind != "game":  # a game is confirmed only by the perception review
            answered = sum(1 for _, v in vals if v is not None)
            total = len([1 for r, _, _ in RUBRIC.values() if self.kind in r.applies])
            a = 0.45 * min(1.0, answered / max(1, total))
            self.index = round((1 - a) * self.evidence_index + a * self.visual_index, 1)
            self.visual_blend = round(a, 2)
            self.status = "확정" if a >= 0.3 else "잠정"
        else:
            self.index = self.evidence_index
            self.visual_blend = 0.0
            self.status = "잠정"
        self.verdict = scoring.verdict_for(self.index)
        if self.kind == "game" and self.status == "잠정":
            # held-out validation: measurements alone could not separate AI-made from human-made games (AUC ≈ 0.5),
            # because jam-scale human games share the same missing-polish signals. Don't label a game slop without eyes on it.
            self.verdict = {"code": "UNDECIDED", "label": "판정 보류 (게임: 지각 리뷰 필요)",
                            "description": f"측정 점수 {self.index:.0f}는 높든 낮든 마감 결함(사운드·피드백·상태 흐름 등)의 양이지 AI 여부가 아닙니다. "
                                           "검증에서 게임은 측정만으로 AI 제작물과 사람 제작물을 가르지 못했습니다(AUC 0.48). "
                                           "화면을 직접 보는 지각 리뷰로 판정을 확정하세요."}
        # where the reviewer's eyes and the measurements disagree, neither should be trusted blindly
        self.agreement = None
        if self.perception_index is not None:
            gap = round(self.perception_index - self.evidence_index, 1)
            self.agreement = {"gap": gap, "conflict": abs(gap) >= 35,
                              "note": ("리뷰가 측정보다 훨씬 나쁘게 봄 — 측정이 못 잡는 문제가 있거나 리뷰가 과함" if gap >= 35 else
                                       "리뷰가 측정보다 훨씬 좋게 봄 — 공들인 결과물이 AI 패턴을 공유하거나 리뷰가 문제를 놓침" if gap <= -35 else
                                       "리뷰와 측정이 대체로 일치")}
        avail = _rv.review_frames(self)
        noted = {n["file"] for n in (getattr(self, "frame_notes", None) or [])}
        cov = (len({os.path.basename(f) for f in avail} & noted) / len(avail)) if (avail and self.perception_index is not None) else None
        self.frame_coverage = None if cov is None else round(cov, 2)
        self.confidence = scoring.confidence(self.ctx, (self.visual_blend / 0.45) if self.visual_index is not None else 0.0,
                                             reviewed=self.perception_index is not None,
                                             review_meta=getattr(self, "review_meta", None), agreement=self.agreement,
                                             frame_coverage=self.frame_coverage, index=self.index,
                                             unsupported=self.review_unsupported)

    def attach(self, paths):
        """Add hand-taken screenshots to the review material. Returns (added, rejected)."""
        from . import review as _rv
        return _rv.attach_images(self, paths)

    def add_review(self, items, frames=None, meta=None, attach=None):
        from . import review as _rv
        # frame notes that point at an image outside the capture are hand-taken screenshots too
        self.attach(list(attach or []) + [f.get("file") for f in (frames or []) if isinstance(f, dict) and f.get("file")
                                          and os.path.isabs(str(f["file"])) and os.path.isfile(str(f["file"]))])
        self.review, unknown = _rv.normalize(items, self.kind)
        self.frame_notes = _rv.normalize_frames(frames)
        self.review_meta = _rv.normalize_meta(meta)
        if getattr(self, "revealed", False) and self.review_meta.get("blind"):
            self.review_meta["blind"] = False
            self.review_meta["blind_overridden"] = True  # measurements were shown before this review
        self.recompute()
        if self.perception_index is not None:
            self.revealed = True  # this submission publishes the measurements
        return unknown

    def add_visual_answers(self, answers):
        self.visual_answers, self.visual_findings, unknown = [], [], []
        for a in answers:
            rid = str(a.get("id", "")).upper().strip()
            if rid not in RUBRIC:
                unknown.append(rid)
                continue
            r = RUBRIC[rid][0]
            raw = str(a.get("answer", "na")).lower().strip()
            v = ANSWER_VALUE.get(raw, None)
            note = str(a.get("note", ""))[:400]
            self.visual_answers.append((r, v, note))
            if v:
                self.visual_findings.append(Finding(rule=r, count=1, strength=v, evidence=[], detail="시각 검토: " + raw, note=note))
        self.recompute()
        return unknown

    # ------------------------------------------------------------------
    def _index_without(self, removed_ids):
        """The index if these rules stopped firing. A reviewer's impression is left as it is: no one has looked again."""
        keep = [f for f in self.static_findings if f.rule.id not in removed_ids]
        cats = scoring.category_scores(keep, self.kind, self.fp_factor)
        s, _ = scoring.static_index(cats, self.kind)
        if self.perception_index is not None:
            return round(0.65 * self.perception_index + 0.35 * s, 1)
        if self.visual_blend and self.visual_index is not None:
            vals = [(r, (0.0 if r.id in removed_ids else v)) for r, v, _ in self.visual_answers]
            vi = scoring.visual_score(vals)
            return round((1 - self.visual_blend) * s + self.visual_blend * vi, 1)
        return s

    def fix_plan(self):
        buckets = {"S": [], "M": [], "L": []}
        for f in self.findings:
            eff = f.rule.fix.get("effort", "M")
            pr = f.impact / EFFORT_COST.get(eff, 2.0)
            buckets.setdefault(eff, []).append((pr, f))
        plan, removed = [], set()
        projections = []
        for eff in ("S", "M", "L"):
            items = sorted(buckets.get(eff, []), key=lambda x: -x[0])
            for _, f in items:
                removed.add(f.rule.id)
            projections.append({"after": EFFORT_LABEL[eff], "effort": eff, "index": self._index_without(set(removed))})
            plan.append({
                "effort": eff, "label": EFFORT_LABEL[eff],
                "items": [{"rule_id": f.rule.id, "title": f.rule.title, "severity": f.severity, "impact": f.impact,
                           "priority": round(p, 2), "summary": f.rule.fix.get("summary", ""),
                           "steps": f.rule.fix.get("steps", []), "example": f.rule.fix.get("example", ""),
                           "where": [f"{e.file}:{e.line}" if e.line else e.file for e in f.evidence[:4]]}
                          for p, f in items],
            })
        return {"phases": plan, "projections": projections, "brief": self.brief()}

    def brief(self):
        """A paste-ready 'anti-slop' redesign brief for any coding agent."""
        directives, seen = [], set()
        for f in self.findings:
            d = f.rule.fix.get("directive")
            if d and d not in seen:
                seen.add(d)
                directives.append(f"- [{f.rule.id}] {d}")
        kind = "게임" if self.kind == "game" else "웹사이트"
        head = [
            f"# Anti-Slop 리디자인 브리프 ({kind})",
            "",
            "아래 결과물을 개선한다. 목표는 '어디서 본 AI 기본값'이 아니라 '누군가 의도를 가지고 결정한 결과물'이다.",
            "",
            "## 0. 먼저 결정할 것 (코드 작성 전에 답을 적을 것)",
        ]
        if self.kind == "game":
            head += ["- 이 게임의 고유 메카닉 비틀기를 한 문장으로: \"___ 하는 게임인데, ___ 하다\"",
                     "- 핵심 동사 1개와 그 동사의 손맛(피드백 5겹)을 어떻게 만들지",
                     "- 아트 방향 1문장 (팔레트 색 수, 해상도, 외곽선 규칙, 참고작 2개)",
                     "- 플레이어가 다시 할 이유 1개 (기록·해금·변주)"]
        else:
            head += ["- 타깃 사용자 1명을 구체적으로 (직업·상황·지금 쓰는 대안)",
                     "- 브랜드 성격 형용사 3개와, 의도적으로 '하지 않을' 것 3개",
                     "- 시그니처 시각 요소 1개 (반복해서 쓸 고유 장치)",
                     "- 방문자가 이 페이지에서 답을 얻어야 할 질문 3~5개 (섹션 순서의 근거)"]
        head += ["", "## 1. 금지/필수 규칙 (이번 검사에서 발견된 문제 기반)"]
        tail = ["", "## 2. 완료 기준",
                "- 모든 링크·버튼·폼이 실제로 동작한다 (또는 노출하지 않는다).",
                "- 더미 텍스트·가짜 후기·가짜 통계·플레이스홀더 이미지가 0개다.",
                "- 로고/이름을 다른 브랜드로 바꾸면 어색해진다 (브랜드 교체 테스트 통과).",
                "- 모바일 390px 폭에서 깨지지 않는다.",
                "- 수정 후 `slop_scan`을 다시 실행해 Slop Index 30 미만을 확인한다."]
        return "\n".join(head + (directives or ["- (발견된 문제 없음)"]) + tail)

    def to_dict(self, max_findings=None):
        fs = self.findings
        return {
            "tool": "SlopLens", "version": VERSION, "scan_id": self.id, "created": self.created,
            "target": self.ctx.target, "kind": self.kind, "context": self.ctx.summary(),
            "slop_index": self.index, "status": self.status, "static_index": self.static_index, "visual_index": self.visual_index,
            "perception_index": self.perception_index, "craft": {"score": self.craft, "evidence": self.craft_evidence, "fingerprint_factor": self.fp_factor},
            "review": self.review, "frame_notes": getattr(self, "frame_notes", []), "review_meta": getattr(self, "review_meta", None),
            "review_missing": self.review_missing, "review_unsupported": self.review_unsupported,
            "attachments": list(getattr(self, "attachments", []) or []),
            "agreement": self.agreement, "frame_coverage": self.frame_coverage,
            "visual_blend": self.visual_blend, "convergence_bonus": self.convergence_bonus,
            "verdict": self.verdict, "axes": self.axes, "confidence": self.confidence,
            "categories": {c: {"label": scoring.category_labels()[c], "score": s} for c, s in self.categories.items()},
            "drivers": self.drivers,
            "findings": [f.to_dict() for f in (fs[:max_findings] if max_findings else fs)],
            "findings_total": len(fs),
            "visual_review": [{"id": r.id, "title": r.title, "answer": v, "note": n} for r, v, n in self.visual_answers],
            "fix_plan": self.fix_plan(),
            "errors": self.errors,
            "render": render_summary(self.ctx.render),
            "superseded_by_measurement": getattr(self, "superseded", []),
        }


def render_summary(r):
    if not r or not r.get("ok"):
        return None
    d, m, g, c = r.get("desktop") or {}, r.get("mobile") or {}, r.get("game"), r.get("clicks") or {}
    out = {"browser": r.get("browser"), "elapsed_ms": r.get("elapsed_ms"), "screenshots": r.get("screenshots"),
           "fonts": d.get("fonts"), "contrast_low_share": (d.get("contrast") or {}).get("lowShare"),
           "clicks": {"tested": c.get("tested", 0), "dead": len(c.get("dead", []))} if c else None,
           "mobile": {"no_viewport": m.get("noViewport"), "overflow": m.get("overflow")} if m else None}
    if g:
        out["game"] = {k: g.get(k) for k in ("fps", "longFrameShare", "audioCalls", "emojiText", "navigations", "juice", "draw")}
    return out


BOTWALL = re.compile(r"cf-turnstile|challenge-platform|Just a moment\.\.\.|Checking your browser|Attention Required! \| Cloudflare|"
                     r"보안 확인 수행 중|사람인지 확인|Verify you are human|g-recaptcha|hcaptcha\.com/1/api", re.I)


class BlockedPage(RuntimeError):
    pass


def _visible_words(html):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"<[^>]+>", " ", t).split()


def scan(target, kind="auto", render="auto", screenshots_dir=None, perception="auto"):
    """render: auto (use the Node probe if installed) | on (require it) | off."""
    from . import proc as _proc, render as _render
    ctx = build_context(target, kind)
    _proc.check_cancelled()
    if render != "off":
        data = _render.run(target, kind if kind in ("web", "game") else "auto", screenshots_dir)
        if data.get("ok") and BOTWALL.search((data.get("html") or "")[:200000]) and len(_visible_words(data.get("html") or "")) < 400:
            # judging a bot-check page as if it were the site would be a fabricated verdict
            raise BlockedPage("봇 차단·보안 확인 페이지가 떠서 실제 화면을 측정할 수 없습니다. "
                              "브라우저에서 직접 통과한 뒤 저장한 페이지/스크린샷으로 검사하거나, 로컬 빌드로 검사하세요.")
        if data.get("ok"):
            ctx.render = data
            if kind == "auto" and data.get("kindHint") and data["kindHint"] != ctx.kind:
                # kindHint is "game" only when the canvas dominates and the page has little copy
                ctx.kind = data["kindHint"]
                ctx.kind_reason += " → 렌더 결과로 정정: " + ("캔버스가 화면 대부분 차지" if ctx.kind == "game" else "캔버스가 주 화면이 아님")
            ctx.ingest_rendered(data.get("html", ""))
            ctx.notes.extend(data.get("notes", []))
            # images the page really loaded → provenance (C2PA / generator metadata / native generator size)
            from .images import analyze_file as _af
            have = {os.path.basename(i.path) for i in ctx.images}
            for a in (data.get("assets") or [])[:40]:
                if a.get("file") and os.path.isfile(a["file"]) and os.path.basename(a["file"]) not in have:
                    try:
                        ctx.images.append(_af(a["file"], "로드됨/" + os.path.basename(a["file"])))
                    except Exception:
                        pass
        elif render == "on" or not data.get("skipped"):
            ctx.notes.append("렌더 측정 실패: " + str(data.get("error")))
        else:
            ctx.notes.append("렌더 측정 생략: " + str(data.get("error")))
    # ---- perception layer: what people see and hear
    from . import perceive as _perc, unity as _unity
    ctx.perception, ctx.unity = None, None
    root = ctx.target if os.path.isdir(ctx.target) else None
    if root and _unity.is_unity_project(root):
        ctx.platform, ctx.kind = "unity", "game"
        cap = _unity.latest_capture(root)
        fm = _unity.fmod_inventory(root)
        ctx.unity = {"yaml": _unity.scan_yaml(root), "capture": cap, "fmod_banks": fm["banks"], "fmod": fm, "version": _unity.project_version(root)}
        if cap and cap.get("ok"):
            ctx.notes.append(f"Unity 캡처 결과 사용: {cap.get('out')} (Unity {cap.get('editor')})")
        else:
            ctx.notes.append("Unity 실행 캡처 없음 → `slop-lens unity-capture <프로젝트>`로 빌드·자동 플레이하면 화면·사운드까지 판독합니다.")
    if perception != "off":
        cap = (ctx.unity or {}).get("capture") or {}
        loaded = [a["file"] for a in ((ctx.render or {}).get("assets") or []) if a.get("file")]
        data = _perc.run(ctx, extra_frames=cap.get("frames") or [], extra_audio=[cap["mixWav"]] if cap.get("mixWav") else [],
                         extra_images=loaded)
        if data.get("ok"):
            ctx.perception = data
        elif data.get("error"):
            ctx.notes.append("지각 분석 생략: " + str(data["error"]))
    # ---- what a person reads on screen (rendered DOM, after play, Unity capture)
    st = []
    rr = ctx.render if ctx.render and ctx.render.get("ok") else None
    for x in ((rr or {}).get("desktop") or {}).get("uiTexts") or []:
        st.append(dict(x, src="화면(첫 화면)"))
    for x in ((rr or {}).get("game") or {}).get("uiTexts") or []:
        st.append(dict(x, src="화면(플레이 중)"))
    capu = ((ctx.unity or {}).get("capture") or {})
    for x in capu.get("texts") or []:
        t = x.get("text", "")
        st.append({"t": t, "up": bool(re.search(r"[A-Za-z]{2}", t)) and t == t.upper(), "btn": False,
                   "font": x.get("font"), "src": f"Unity 화면({x.get('object', '')})"})
    seen, ctx.screen_texts = set(), []
    for x in st:
        if x["t"] and x["t"] not in seen:
            seen.add(x["t"]); ctx.screen_texts.append(x)
    findings, errors, superseded = [], [], set()
    for r in get_rules(ctx.kind):
        _proc.check_cancelled()
        if r.source == "render" and not ctx.render:
            continue
        try:
            res = r.detect(ctx)
        except Exception as e:  # a broken rule must never break the scan
            errors.append(f"{r.id}: {e.__class__.__name__}: {e}")
            continue
        if res is CLEAN:
            if r.clean_supersedes:
                superseded.update(r.replaces)
            continue
        if not res or res.count < r.threshold:
            continue
        strength = res.strength if res.strength is not None else r.strength_for(res.count)
        if strength <= 0:
            continue
        superseded.update(r.replaces)
        findings.append(Finding(rule=r, count=res.count, strength=strength, evidence=res.evidence, detail=res.detail))
    findings = [f for f in findings if f.rule.id not in superseded]
    result = ScanResult(ctx, findings, errors)
    result.superseded = sorted(superseded)
    return result
