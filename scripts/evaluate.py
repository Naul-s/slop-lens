#!/usr/bin/env python3
"""Accuracy on a labeled set — how well SlopLens separates AI-made from human-made work.

  python scripts/evaluate.py <targets.json> <results_dir> [--final <dir_with_NAME-final.json>] [--out report.md]

targets.json entries need  "label": "ai" | "human"  (who made it — NOT whether it is slop).
Reports, for the measured (provisional) index and, if given, the reviewed (confirmed) index:
  AUC (chance a random AI item scores above a random human item, 0.5 = coin flip) with a bootstrap 90% interval,
  accuracy at the tool's own slop threshold (index ≥ 40 = "슬롭 경향" or worse),
  and per-rule discrimination: rules that fire as often on human work as on AI work are noise.
Small sets give wide intervals — the interval is the honest part of the result.
"""
import json
import os
import random
import sys

THRESHOLD = 40.0


def auc(pos, neg):
    if not pos or not neg:
        return None
    s = 0.0
    for p in pos:
        for n in neg:
            s += 1.0 if p > n else 0.5 if p == n else 0.0
    return s / (len(pos) * len(neg))


def boot_ci(pos, neg, n=2000, seed=7):
    if len(pos) < 2 or len(neg) < 2:
        return None
    rnd = random.Random(seed)
    vals = []
    for _ in range(n):
        a = [rnd.choice(pos) for _ in pos]
        b = [rnd.choice(neg) for _ in neg]
        vals.append(auc(a, b))
    vals.sort()
    return vals[int(0.05 * n)], vals[int(0.95 * n) - 1]


def acc_at(pos, neg, t):
    tp = sum(1 for p in pos if p >= t)
    tn = sum(1 for x in neg if x < t)
    return (tp + tn) / max(1, len(pos) + len(neg)), tp, tn


def block(title, rows):
    pos = [r["score"] for r in rows if r["label"] == "ai"]
    neg = [r["score"] for r in rows if r["label"] == "human"]
    a = auc(pos, neg)
    ci = boot_ci(pos, neg)
    acc, tp, tn = acc_at(pos, neg, THRESHOLD)
    out = [f"| {title} | {len(pos)} / {len(neg)} | " + (f"{a:.2f}" if a is not None else "-") +
           (f" ({ci[0]:.2f}–{ci[1]:.2f})" if ci else "") + f" | {acc:.0%} (AI {tp}/{len(pos)} 적중, 사람 {tn}/{len(neg)} 적중) | "
           + (f"{sum(pos) / len(pos):.1f} / {sum(neg) / len(neg):.1f}" if pos and neg else "-") + " |"]
    return out


def longpath(p):
    p = os.path.abspath(p)
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def main():
    a = sys.argv[1:]
    targets = json.load(open(a[0], encoding="utf-8"))
    res_dir = longpath(a[1])
    final_dir = longpath(a[a.index("--final") + 1]) if "--final" in a else None
    out_path = a[a.index("--out") + 1] if "--out" in a else None
    rows, fires = [], {}
    for t in targets:
        if t.get("label") not in ("ai", "human"):
            continue
        p = os.path.join(res_dir, t["name"] + ".json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        r = {"name": t["name"], "label": t["label"], "group": t.get("group", ""), "kind": d.get("kind"), "score": d["slop_index"],
             "rules": {f["rule_id"] for f in d.get("findings", [])}}
        if final_dir and os.path.exists(os.path.join(final_dir, t["name"] + "-final.json")):
            fd = json.load(open(os.path.join(final_dir, t["name"] + "-final.json"), encoding="utf-8"))
            r["final"], r["review"] = fd["slop_index"], fd.get("perception_index")
        rows.append(r)
        for rid in r["rules"]:
            fires.setdefault(rid, {"ai": 0, "human": 0})[t["label"]] += 1

    L = ["# SlopLens 정확도 평가", "",
         f"라벨 = 만든 방식(AI 제작 / 사람 제작). 슬롭 기준선 = Slop Index {THRESHOLD:.0f} 이상.", "",
         "| 구분 | AI / 사람 | AUC (90% 구간) | 기준선 정확도 | 평균 점수 AI / 사람 |", "|---|---|---|---|---|"]
    for kind, label in ((None, "전체 · 측정만"), ("web", "웹 · 측정만"), ("game", "게임 · 측정만")):
        sub = [r for r in rows if kind is None or r["kind"] == kind]
        L += block(label, sub)
    fin = [dict(r, score=r["final"]) for r in rows if "final" in r]
    if fin:
        for kind, label in ((None, "전체 · 리뷰 반영"), ("web", "웹 · 리뷰 반영"), ("game", "게임 · 리뷰 반영")):
            sub = [r for r in fin if kind is None or r["kind"] == kind]
            if sub:
                L += block(label, sub)
        rv = [dict(r, score=r["review"]) for r in fin if r.get("review") is not None]
        L += block("전체 · 리뷰만", rv)
    L += ["", "## 대상별", "", "| 대상 | 라벨 | 유형 | 측정 | 리뷰 반영 |", "|---|---|---|---:|---:|"]
    for r in sorted(rows, key=lambda x: (x["label"], x["kind"] or "", -x["score"])):
        L.append(f"| {r['name']} | {'AI' if r['label'] == 'ai' else '사람'} | {r['kind']} | {r['score']:.1f} | "
                 + (f"{r['final']:.1f}" if "final" in r else "-") + " |")
    n_ai = sum(1 for r in rows if r["label"] == "ai")
    n_h = sum(1 for r in rows if r["label"] == "human")
    L += ["", "## 규칙 변별력 (발동 비율 AI / 사람)", "",
          "사람 작품에서 AI 작품만큼 자주 걸리는 규칙은 판별에 도움이 안 되는 잡음입니다.", "",
          "| 규칙 | AI | 사람 | 판단 |", "|---|---:|---:|---|"]
    for rid, c in sorted(fires.items(), key=lambda x: -(x[1]["ai"] / max(1, n_ai) - x[1]["human"] / max(1, n_h))):
        ra, rh = c["ai"] / max(1, n_ai), c["human"] / max(1, n_h)
        tag = "변별력 높음" if ra - rh >= 0.3 else "잡음 의심 (사람에게도 자주)" if rh >= ra and rh >= 0.2 else "약함"
        L.append(f"| {rid} | {ra:.0%} | {rh:.0%} | {tag} |")
    text = "\n".join(L)
    if out_path:
        open(out_path, "w", encoding="utf-8").write(text)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(text)


if __name__ == "__main__":
    main()
