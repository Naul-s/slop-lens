"""Render a ScanResult as Markdown (for agents/terminals), JSON, or standalone HTML."""
import html
import json

from .model import CATEGORIES, DRIVERS


def _bar(score, width=10):
    n = int(round(score / 100 * width))
    return "█" * n + "░" * (width - n)


def _kind_label(k):
    return "게임" if k == "game" else "웹사이트"


def why_section(res, d):
    """'Why does it feel like AI slop?' — the core of the report: feeling → evidence → fix, per sense."""
    from .review import CATEGORY_SENSE, LEVEL_WORDS, RULE_SENSE, title_of
    held = (d.get("verdict") or {}).get("code") == "UNDECIDED"
    L = ["## 측정이 가리키는 마감 결함 (슬롭 여부는 리뷰로 판정)" if held else "## 왜 AI 슬롭으로 느껴지나", ""]
    by_sense = {}
    for f in res.findings:
        if f.rule.source == "visual":
            continue
        by_sense.setdefault(RULE_SENSE.get(f.rule.id) or CATEGORY_SENSE.get(f.rule.category, "S8"), []).append(f)
    review = {it["id"]: it for it in (d.get("review") or []) if it.get("level") is not None}
    order = []
    for sid, it in review.items():
        if sid != "C1" and it["level"] >= 2:
            order.append((it["level"] * 10 + 5, sid))
    for sid, fs in by_sense.items():
        if sid not in review:
            order.append((max(f.impact for f in fs) * 8, sid))
    order.sort(reverse=True)
    if not order:
        L += ["사람이 슬롭으로 느낄 만한 뚜렷한 원인이 발견되지 않았습니다.", ""]
    for n, (_, sid) in enumerate(order[:6], 1):
        it = review.get(sid)
        fs = sorted(by_sense.get(sid, []), key=lambda f: -f.impact)[:3]
        head = f"### {n}. {title_of(sid)}"
        if it:
            head += f" — 리뷰 레벨 {it['level']} ({LEVEL_WORDS[it['level']]})"
        L += [head, ""]
        if it and it.get("why"):
            L.append(f"- **느낌**: {it['why']}")
        elif fs:
            L.append(f"- **느낌**: {fs[0].rule.why}")
        if it and it.get("evidence"):
            L.append(f"- **보이는/들리는 근거**: {it['evidence']}")
        for f in fs:
            ev = "; ".join((f"{e.file}: " if e.file and not e.file.startswith("(") else "") + e.snippet for e in f.evidence[:2])
            L.append(f"- **측정 근거** [{f.rule.id}] {f.detail}" + (f" — {ev}" if ev else ""))
        if it and it.get("fix"):
            L.append(f"- **해결**: {it['fix']}")
        for f in fs[:2]:
            L.append(f"- **해결** [{f.rule.id}]: {f.rule.fix.get('summary', '')}")
        L.append("")
    notes = d.get("frame_notes") or []
    if notes:
        L.append(f"### 프레임별 관찰 (원본 {len(notes)}장 확인)")
        L += [f"- `{n['file']}` — {n['note']}" for n in notes]
        L.append("")
    craft = d.get("craft") or {}
    c1 = review.get("C1")
    if craft.get("evidence") or c1:
        L.append("### 공들인 흔적 (반대 증거)")
        if craft.get("evidence"):
            L.append(f"- 실측 {craft['score']:.0f}/100: " + ", ".join(craft["evidence"]) +
                     (f" → AI 지문 신호를 {round((1 - craft['fingerprint_factor']) * 100)}% 낮춰 반영" if craft.get("fingerprint_factor", 1) < 1 else ""))
        if c1:
            L.append(f"- 리뷰어 판단 레벨 {c1['level']}/4: {c1.get('evidence', '')}")
        L.append("")
    return L


def to_markdown(res, max_findings=20, include_plan=True, include_brief=True):
    d = res.to_dict()
    c = d["context"]
    L = []
    L.append("# SlopLens 판정 리포트")
    L.append("")
    L.append(f"대상 `{d['target']}` · 유형 **{_kind_label(d['kind'])}** ({c['kind_reason']}) · 파일 {c['files']}개 · 이미지 {c['images']}개 · "
             f"보이는 텍스트 {c['words']}단어 · scan_id `{d['scan_id']}`")
    L.append("")
    v = d["verdict"]
    status = d.get("status", "잠정")
    L.append(f"## 판정: {v['label']} ({status}) — Slop Index **{d['slop_index']:.0f}/100**")
    L.append("")
    L.append(f"> {v['description']}")
    if status == "잠정":
        L.append(">")
        L.append("> **잠정 판정**입니다. 슬롭인지는 화면과 소리를 직접 보고 듣는 사람이 가장 잘 판단합니다. "
                 "아래 원인 목록은 측정에서 나온 근거이며, `slop_review_protocol`로 지각 리뷰를 하면 확정됩니다.")
    ag = d.get("agreement")
    rm = d.get("review_meta") or {}
    if d.get("perception_index") is not None:
        L.append("")
        L.append(f"> 리뷰 {d['perception_index']:.0f} · 측정 {d['evidence_index'] if 'evidence_index' in d else d['static_index']:.0f} → {ag['note'] if ag else ''}"
                 + (f" · 리뷰어 {rm['reviewer']}" if rm.get("reviewer") else "")
                 + (" · 블라인드 리뷰" if rm.get("blind") else
                    " · 블라인드로 제출됐지만 측정이 먼저 공개돼 블라인드 아님으로 처리" if rm.get("blind_overridden") else " · 측정을 본 뒤 리뷰")
                 + (" · **리뷰어가 기대 판정을 알고 있었음(독립 판정 아님)**" if rm.get("knew_expected") else "")
                 + (f" · 직접 첨부한 화면 {len(d['attachments'])}장 포함" if d.get("attachments") else ""))
        if ag and ag.get("conflict"):
            L.append(">")
            L.append(f"> ⚠ **리뷰와 측정이 {abs(ag['gap']):.0f}점 차이**납니다. 어느 한쪽이 틀렸을 수 있으니 아래 근거를 직접 확인하세요.")
    L.append("")
    L += why_section(res, d)
    ax = d["axes"]
    L.append("| 축 | 점수 | 의미 |")
    L.append("|---|---:|---|")
    L.append(f"| AI 지문 (Genericness) | {ax['genericness']:.0f} | 기본값·평균값 패턴이 얼마나 많은가 |")
    L.append(f"| 완성도 결함 (Effort deficit) | {ax['effort_deficit']:.0f} | 겉보기와 달리 동작·마무리가 비어 있는가 |")
    L.append("")
    L.append(f"**유형: {ax['quadrant']['label']}** — {ax['quadrant']['description']}")
    L.append("")
    extra = []
    if d["visual_index"] is not None:
        extra.append(f"정적 {d['static_index']:.0f} + 시각 검토 {d['visual_index']:.0f} (반영 비율 {d['visual_blend']:.0%})")
    if d["convergence_bonus"]:
        extra.append(f"여러 영역 동시 발생 가산 +{d['convergence_bonus']:.0f}")
    conf = d["confidence"]
    extra.append(f"신뢰도 {conf['label']}" + (f" ({'; '.join(conf['limits'])})" if conf["limits"] else ""))
    L.append("· ".join(extra))
    L.append("")

    rs = d.get("render")
    L.append("## 측정 방식")
    L.append("")
    if rs:
        parts = [f"실제 브라우저({rs['browser']})로 렌더링해 측정 ({(rs.get('elapsed_ms') or 0) / 1000:.0f}초)"]
        if rs.get("clicks"):
            parts.append(f"클릭 테스트 {rs['clicks']['tested']}개 중 죽은 클릭 {rs['clicks']['dead']}개")
        if rs.get("contrast_low_share") is not None:
            parts.append(f"대비 미달 텍스트 {rs['contrast_low_share']:.0%}")
        if rs.get("mobile"):
            mm = rs["mobile"]
            parts.append("모바일: " + ("viewport 없음" if mm.get("no_viewport") else "가로 넘침" if mm.get("overflow") else "정상"))
        if rs.get("game"):
            gg = rs["game"]
            parts.append(f"게임: 오디오 호출 {gg.get('audioCalls')}회, 이모지 그리기 {gg.get('emojiText')}회, 새로고침 {gg.get('navigations')}회")
        L.append("- " + " · ".join(parts))
        if d.get("superseded_by_measurement"):
            L.append(f"- 실측으로 대체된 정적 추정 규칙: {', '.join(d['superseded_by_measurement'])}")
        sh = rs.get("screenshots") or {}
        shots = [v for k, v in sh.items() if k != "game" and v] + list(sh.get("game") or [])
        if shots:
            L.append("- 스크린샷: " + ", ".join(f"`{p}`" for p in shots))
    else:
        L.append("- 정적 분석만 수행 (렌더 측정 없음). Node.js를 설치하고 SlopLens 폴더에서 `npm install`을 실행하면 실제 색·대비·클릭·모바일·게임 런타임을 측정합니다.")
    L.append("")

    L.append("## 영역별 점수")
    L.append("")
    L.append("| 영역 | 점수 | |")
    L.append("|---|---:|---|")
    for k, cat in sorted(d["categories"].items(), key=lambda x: -x[1]["score"]):
        L.append(f"| {cat['label']} | {cat['score']:.0f} | `{_bar(cat['score'])}` |")
    L.append("")

    L.append("## 사람이 슬롭으로 느끼는 이유 (지각 요인)")
    L.append("")
    L.append("| 요인 | 점수 | 설명 |")
    L.append("|---|---:|---|")
    for k, dr in sorted(d["drivers"].items(), key=lambda x: -x[1]["score"]):
        L.append(f"| {k} {dr['name']} ({dr['en']}) | {dr['score']:.0f} | {DRIVERS[k]['desc']} |")
    L.append("")

    fs = d["findings"]
    L.append(f"## 주요 발견 ({len(fs)}건, 영향도 순)")
    L.append("")
    if not fs:
        L.append("발견된 슬롭 신호가 없습니다.")
    for i, f in enumerate(fs[:max_findings], 1):
        src = " · 시각 검토" if f["source"] == "visual" else ""
        L.append(f"### {i}. [{f['rule_id']}] {f['title']}")
        L.append(f"**{f['severity']}** · 영향 {f['impact']} · {f['category_label']} · "
                 f"{'AI 지문' if f['kind'] == 'fingerprint' else '완성도 결함'} · {', '.join(f['drivers'])}{src}")
        L.append("")
        if f["detail"]:
            L.append(f"- **탐지**: {f['detail']}")
        if f["note"]:
            L.append(f"- **검토 메모**: {f['note']}")
        for e in f["evidence"][:4]:
            loc = f"{e['file']}:{e['line']}" if e["line"] else e["file"]
            snip = e["snippet"].replace("`", "'")[:110]
            L.append(f"- `{loc}` — `{snip}`")
        L.append(f"- **왜 슬롭으로 보이나**: {f['why']}")
        fx = f["fix"]
        L.append(f"- **해결**: {fx.get('summary', '')}")
        for j, s in enumerate(fx.get("steps", []), 1):
            L.append(f"  {j}. {s}")
        if fx.get("example"):
            L.append("")
            L.append("  ```")
            for ln in fx["example"].splitlines():
                L.append("  " + ln)
            L.append("  ```")
        L.append("")
    if len(fs) > max_findings:
        L.append("기타 발견: " + ", ".join(f"[{f['rule_id']}] {f['title']}" for f in fs[max_findings:]))
        L.append("")

    if include_plan and fs:
        plan = d["fix_plan"]
        L.append("## 수정 계획 (우선순위 = 영향 ÷ 노력)")
        L.append("")
        L.append(f"현재 Slop Index **{d['slop_index']:.0f}**")
        for ph, pj in zip(plan["phases"], plan["projections"]):
            if not ph["items"]:
                continue
            L.append("")
            L.append(f"### {ph['label']} → 완료 시 예상 Index **{pj['index']:.0f}**")
            for it in ph["items"]:
                where = f" ({', '.join(it['where'][:2])})" if it["where"] else ""
                L.append(f"- [ ] **[{it['rule_id']}] {it['title']}** — {it['summary']}{where}")
        L.append("")
    if include_brief and fs:
        L.append("## Anti-Slop 리디자인 브리프")
        L.append("")
        L.append("아래 블록을 그대로 코딩 에이전트(Claude Code, Codex, Gemini CLI 등)에 붙여 넣으면 같은 문제를 반복하지 않고 수정합니다.")
        L.append("")
        L.append("````markdown")
        L.append(d["fix_plan"]["brief"])
        L.append("````")
        L.append("")
    if d["visual_index"] is None:
        L.append("## 다음 단계: 시각 검토")
        L.append("")
        has_shots = bool(rs and (rs.get("screenshots") or {}).get("desktop"))
        L.append(("렌더 프로브가 스크린샷을 찍어 두었습니다('측정 방식' 참고). 이미지를 열어 볼 수 있는 에이전트라면 " if has_shots else
                  "정적 분석은 이미지 품질·레이아웃 감각·실제 클릭 경험을 볼 수 없습니다. 스크린샷을 볼 수 있는 에이전트라면 ") +
                 f"`slop_visual_rubric`(kind={d['kind']})로 체크리스트를 받아 판정한 뒤 `slop_submit_visual_review`에 "
                 f"scan_id `{d['scan_id']}`와 함께 제출하세요. 최종 점수와 신뢰도가 갱신됩니다.")
        L.append("")
    if d["errors"]:
        L.append("<details><summary>규칙 실행 오류</summary>\n\n" + "\n".join(f"- {e}" for e in d["errors"]) + "\n</details>")
    for n in c.get("notes", []):
        L.append(f"> 참고: {n}")
    return "\n".join(L)


def needs_blind(res):
    """Games are judged by a review first; until then the measured findings stay hidden so they can't anchor it."""
    return res.kind == "game" and not res.review


def blind_summary(res, as_json=False):
    """What an unreviewed game scan returns: enough to start the review, nothing that hints at the verdict."""
    ctx = res.ctx
    r = ctx.render if ctx.render and ctx.render.get("ok") else None
    p = getattr(ctx, "perception", None) or {}
    from .rules._genre import play_reached
    captured = {
        "rendered": bool(r),
        "screenshots": sum(len(v) if isinstance(v, list) else 1 for v in ((r or {}).get("screenshots") or {}).values()),
        "frame_sheet": bool((p.get("sheets") or {}).get("frames")),
        "play_reached": play_reached(ctx),
        "sound_recorded": bool(((r or {}).get("game") or {}).get("sound")) or bool((getattr(ctx, "unity", None) or {}).get("capture")),
    }
    from .review import autoplay_lines
    route = autoplay_lines(((r or {}).get("game")) or None)
    captured["autoplay"] = [x[2:] for x in route]
    nxt = [f"slop_review_protocol {{scan_id: \"{res.id}\", blind: true}} 로 리뷰 자료를 받는다 (CLI: scan <대상> --protocol --blind)",
           "원본 프레임을 한 장씩 열어 보고 감각별로 답한다. 자동 캡처가 못 본 화면은 직접 찍어 attach로 추가한다",
           f"slop_submit_review {{scan_id: \"{res.id}\", ..., meta: {{blind: true}}}} 로 제출하면 판정과 측정 결과가 함께 공개된다"]
    if as_json:
        return json.dumps({"tool": "SlopLens", "scan_id": res.id, "target": res.ctx.target, "kind": "game", "blind": True,
                           "verdict": {"code": "UNDECIDED", "label": "판정 보류 (게임: 지각 리뷰 필요)"},
                           "captured": captured, "next": nxt,
                           "note": "측정 결과는 리뷰가 그것에 끌려가지 않도록 리뷰 제출 전까지 숨깁니다. 바로 보려면 reveal=true (이후 리뷰는 블라인드가 아님)."},
                          ensure_ascii=False, indent=2)
    yn = lambda v: "예" if v else ("확인 못 함" if v is None else "아니요")
    L = ["# SlopLens — 게임 측정 완료 (블라인드)", "",
         f"대상 `{res.ctx.target}` · scan_id `{res.id}`", "",
         "## 판정: 보류 — 지각 리뷰가 필요합니다", "",
         "게임은 측정만으로 AI 슬롭 여부를 가를 수 없어서(검증 AUC 0.48) 화면을 직접 본 리뷰로 판정합니다.",
         "**측정 결과(의심 규칙·점수)는 리뷰가 거기에 끌려가지 않도록 리뷰를 제출할 때까지 숨깁니다.**", "",
         "## 수집한 자료",
         f"- 실제 브라우저 실행: {yn(captured['rendered'])} · 스크린샷 {captured['screenshots']}장 · 화면 시트: {yn(captured['frame_sheet'])}",
         f"- 자동 플레이가 게임 화면까지 도달: {yn(captured['play_reached'])} · 소리 기록: {yn(captured['sound_recorded'])}"]
    L += route + ["", "## 다음 단계"] + [f"{i}. {s}" for i, s in enumerate(nxt, 1)] + [
         "", "> 측정 결과를 지금 보려면 `reveal: true`(CLI `--reveal`)로 다시 요청하세요. 그 뒤의 리뷰는 블라인드가 아닌 것으로 기록됩니다."]
    return "\n".join(L)


def to_json(res, max_findings=None):
    return json.dumps(res.to_dict(max_findings), ensure_ascii=False, indent=2)


_CSS = """
:root{--paper:#f5f1ea;--card:#fffdf9;--ink:#1f1b16;--ink-2:#5b5348;--line:#e2dacd;--accent:#b4441f;--ok:#3d6b45;--warn:#a8741a;--bad:#b4441f;
--r:6px;--font-display:ui-serif,Georgia,'Iowan Old Style','Noto Serif KR',serif;--font-body:system-ui,-apple-system,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#171411;--card:#1f1b17;--ink:#ede5d8;--ink-2:#a99f90;--line:#36302a;--accent:#e07a50;--ok:#7fb08a;--warn:#d9a441;--bad:#e07a50}}
:root[data-theme=dark]{--paper:#171411;--card:#1f1b17;--ink:#ede5d8;--ink-2:#a99f90;--line:#36302a;--accent:#e07a50;--ok:#7fb08a;--warn:#d9a441;--bad:#e07a50}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 var(--font-body)}
main{max-width:980px;margin:0 auto;padding:40px 16px 80px}
h1,h2,h3{font-family:var(--font-display);line-height:1.2;letter-spacing:-.01em}
h1{font-size:clamp(1.8rem,4vw,2.6rem);margin:0 0 .3em}h2{font-size:1.4rem;margin:2.4em 0 .8em;padding-top:.8em;border-top:1px solid var(--line)}
h3{font-size:1.08rem;margin:0 0 .3em}
.meta{color:var(--ink-2);font-size:.9rem}
.verdict{display:grid;grid-template-columns:auto 1fr;gap:28px;align-items:center;margin:28px 0}
.score{font-family:var(--font-display);font-size:clamp(4rem,12vw,6.5rem);line-height:1;font-weight:600}
.score small{font-size:.28em;color:var(--ink-2);font-weight:400}
.verdict p{margin:.2em 0;color:var(--ink-2)}.verdict strong{color:var(--ink);font-size:1.25rem}
.axes{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px}
.axis{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.axis b{font-size:1.6rem;font-family:var(--font-display)}
.rows{display:grid;gap:6px}.row{display:grid;grid-template-columns:9rem 3rem 1fr;gap:12px;align-items:center;font-size:.95rem}
.track{height:8px;background:var(--line);border-radius:4px;overflow:hidden}.fill{height:100%;background:var(--ink)}
.fill.hi{background:var(--bad)}.fill.mid{background:var(--warn)}
.finding{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:var(--r);padding:16px 18px;margin:12px 0}
.finding.치명{border-left-color:var(--bad)}.finding.높음{border-left-color:var(--warn)}
.tag{display:inline-block;font-size:.78rem;padding:1px 8px;border:1px solid var(--line);border-radius:999px;color:var(--ink-2);margin-right:4px}
.finding ul{margin:.5em 0;padding-left:1.2em}.why{color:var(--ink-2)}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.85rem}
pre{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;overflow-x:auto;white-space:pre-wrap}
.loc{word-break:break-all}
.phase{margin:14px 0}.phase h3 span{color:var(--ink-2);font-family:var(--font-body);font-size:.9rem;font-weight:400}
.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px}
.shots img{width:100%;height:auto;border:1px solid var(--line);border-radius:var(--r)}.shots figure{margin:0}.shots figcaption{font-size:.8rem;color:var(--ink-2)}
details{margin:12px 0}summary{cursor:pointer;color:var(--accent)}
@media (max-width:560px){.verdict{grid-template-columns:1fr;gap:8px}.row{grid-template-columns:7rem 2.5rem 1fr}}
"""


def _cls(s):
    return "hi" if s >= 60 else "mid" if s >= 35 else ""


def to_html(res, max_findings=40):
    d = res.to_dict()
    e = html.escape
    c = d["context"]
    v = d["verdict"]
    ax = d["axes"]
    out = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>SlopLens 리포트</title><style>{_CSS}</style></head><body><main>"]
    out.append(f"<p class='meta'>SlopLens {e(d['version'])} · {e(d['created'])} · scan_id {e(d['scan_id'])}</p>")
    out.append(f"<h1>{e(str(d['target']).replace(chr(92), '/').rsplit('/', 1)[-1] or d['target'])}</h1>")
    out.append(f"<p class='meta'>{_kind_label(d['kind'])} · 파일 {c['files']} · 이미지 {c['images']} · 텍스트 {c['words']}단어 · 신뢰도 {e(d['confidence']['label'])}</p>")
    out.append(f"<section class='verdict'><div class='score'>{d['slop_index']:.0f}<small>/100</small></div>"
               f"<div><strong>{e(v['label'])}</strong><p>{e(v['description'])}</p>"
               + (f"<p>정적 {d['static_index']:.0f} · 시각 검토 {d['visual_index']:.0f}</p>" if d['visual_index'] is not None else "<p>시각 검토 미반영</p>")
               + "</div></section>")
    out.append("<div class='axes'>"
               f"<div class='axis'><div class='meta'>AI 지문 (Genericness)</div><b>{ax['genericness']:.0f}</b></div>"
               f"<div class='axis'><div class='meta'>완성도 결함 (Effort deficit)</div><b>{ax['effort_deficit']:.0f}</b></div>"
               f"<div class='axis'><div class='meta'>유형</div><b style='font-size:1.15rem'>{e(ax['quadrant']['label'])}</b><div class='meta'>{e(ax['quadrant']['description'])}</div></div></div>")
    rs = d.get("render") or {}
    sh = rs.get("screenshots") or {}
    shots = [(k, v) for k, v in sh.items() if k not in ("game", "desktopFull") and v] + [("gameplay", v) for v in (sh.get("game") or [])]
    if shots:
        out.append("<h2>렌더 스크린샷</h2><div class='shots'>" + "".join(
            f"<figure><img src='file:///{e(v.replace(chr(92), '/'))}' alt='{e(k)} 스크린샷' loading='lazy'><figcaption>{e(k)}</figcaption></figure>"
            for k, v in shots) + "</div>")
    out.append("<h2>영역별 점수</h2><div class='rows'>")
    for k, cat in sorted(d["categories"].items(), key=lambda x: -x[1]["score"]):
        out.append(f"<div class='row'><span>{e(cat['label'])}</span><b>{cat['score']:.0f}</b><div class='track'><div class='fill {_cls(cat['score'])}' style='width:{cat['score']:.0f}%'></div></div></div>")
    out.append("</div><h2>지각 요인</h2><div class='rows'>")
    for k, dr in sorted(d["drivers"].items(), key=lambda x: -x[1]["score"]):
        out.append(f"<div class='row' title='{e(DRIVERS[k]['desc'])}'><span>{k} {e(dr['name'])}</span><b>{dr['score']:.0f}</b><div class='track'><div class='fill {_cls(dr['score'])}' style='width:{dr['score']:.0f}%'></div></div></div>")
    out.append("</div>")
    out.append(f"<h2>발견 {len(d['findings'])}건</h2>")
    for f in d["findings"][:max_findings]:
        fx = f["fix"]
        out.append(f"<article class='finding {e(f['severity'])}'><h3>[{e(f['rule_id'])}] {e(f['title'])}</h3>"
                   f"<span class='tag'>{e(f['severity'])}</span><span class='tag'>영향 {f['impact']}</span><span class='tag'>{e(f['category_label'])}</span>"
                   f"<span class='tag'>{'AI 지문' if f['kind'] == 'fingerprint' else '완성도 결함'}</span>")
        if f["detail"]:
            out.append(f"<p>{e(f['detail'])}</p>")
        if f["evidence"]:
            out.append("<ul>" + "".join(f"<li class='loc'><code>{e(x['file'])}{':' + str(x['line']) if x['line'] else ''}</code> — <code>{e(x['snippet'][:110])}</code></li>" for x in f["evidence"][:4]) + "</ul>")
        out.append(f"<p class='why'>{e(f['why'])}</p><p><b>해결</b> {e(fx.get('summary', ''))}</p>")
        if fx.get("steps"):
            out.append("<ol>" + "".join(f"<li>{e(s)}</li>" for s in fx["steps"]) + "</ol>")
        if fx.get("example"):
            out.append(f"<pre>{e(fx['example'])}</pre>")
        out.append("</article>")
    plan = d["fix_plan"]
    out.append("<h2>수정 계획</h2>")
    for ph, pj in zip(plan["phases"], plan["projections"]):
        if ph["items"]:
            out.append(f"<div class='phase'><h3>{e(ph['label'])} <span>완료 시 예상 {pj['index']:.0f}</span></h3><ul>"
                       + "".join(f"<li><b>[{e(i['rule_id'])}]</b> {e(i['summary'])}</li>" for i in ph["items"]) + "</ul></div>")
    out.append(f"<h2>Anti-Slop 리디자인 브리프</h2><pre>{e(plan['brief'])}</pre>")
    out.append("</main></body></html>")
    return "".join(out)
