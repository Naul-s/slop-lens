#!/usr/bin/env python3
"""Human ground truth: do people feel the same slop the tool reports?

People are asked to compare two works ("which feels more like AI slop?") instead of giving a 0–100 number:
absolute ratings drift between raters, forced comparisons need no shared scale (see docs/RESEARCH.md).

  python scripts/human_benchmark.py build items.json kit/ [--per-item 6] [--seed 7]
      items.json: [{"name": "game-a", "images": ["shot1.png", "shot2.png"]}, ...]
      → kit/            give this folder to each rater (open index.html, send back the downloaded JSON)
      → kit.key.json    keep it: it maps the anonymous ids back to names

  python scripts/human_benchmark.py score kit.key.json answers/ scores.json [--out report.md]
      answers/:    the raters' JSON files (3 or more people)
      scores.json: {"game-a": 63.5, ...}, the Slop Index (or any other score) to test against people

The kit holds only screenshots under random names, with no tool scores and no hint of who made what.
"""
import argparse
import glob
import json
import os
import random
import shutil
import sys
from collections import Counter

MIN_RATERS = 3
IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def make_pairs(ids, per_item, rnd):
    """Distinct pairs in which every item appears about per_item times, with random left/right."""
    ids = list(ids)
    rnd.shuffle(ids)
    n, pairs = len(ids), []
    for d in range(1, n // 2 + 1):  # circulant rounds: each one adds two appearances per item
        for i in range(n if d * 2 != n else n // 2):
            pair = [ids[i], ids[(i + d) % n]]
            rnd.shuffle(pair)
            pairs.append(pair)
        if d * 2 >= per_item:
            break
    rnd.shuffle(pairs)
    return pairs


def build(items, out, per_item=6, seed=7):
    """Write the rater kit into `out` and the key next to it. Returns the key path."""
    if len(items) < 3:
        raise ValueError("작품이 3개 이상 필요합니다")
    names = [it["name"] for it in items]
    if len(set(names)) != len(names):
        raise ValueError("name이 겹칩니다")
    out = os.path.abspath(out)
    if os.path.isdir(out) and os.listdir(out):
        raise ValueError(f"빈 폴더가 아닙니다: {out}")  # never mix two kits or overwrite someone's files
    for it in items:
        for src in it.get("images") or [None]:
            if not src or not os.path.isfile(src) or not src.lower().endswith(IMAGES):
                raise ValueError(f"{it['name']}: 이미지가 없거나 읽을 수 없음 ({src})")
    rnd = random.Random(seed)
    order = list(items)
    rnd.shuffle(order)
    os.makedirs(os.path.join(out, "img"), exist_ok=True)
    key, shown = {}, {}
    for n, it in enumerate(order, 1):
        iid = f"w{n:03d}"
        key[iid] = it["name"]
        shown[iid] = []
        for k, src in enumerate(it["images"], 1):
            name = f"{iid}-{k}{os.path.splitext(src)[1].lower()}"
            shutil.copyfile(src, os.path.join(out, "img", name))
            shown[iid].append("img/" + name)
    data = {"items": shown, "pairs": make_pairs(shown, per_item, rnd)}
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(data)))
    key_path = out + ".key.json"
    with open(key_path, "w", encoding="utf-8") as f:
        json.dump({"items": key, "pairs": data["pairs"]}, f, ensure_ascii=False, indent=1)
    return key_path


def krippendorff_alpha(units):
    """Nominal Krippendorff's alpha; units = one list of answers per pair. None when it is undefined."""
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    if n < 2:
        return None
    totals = Counter(v for u in units for v in u)
    expected = (n * n - sum(c * c for c in totals.values())) / (n * (n - 1))
    if not expected:
        return None  # everybody always gave the same answer: nothing to measure
    observed = sum((len(u) ** 2 - sum(c * c for c in Counter(u).values())) / (len(u) - 1) for u in units) / n
    return 1 - observed / expected


def agreement(judged, scores, weight=None):
    """Share of human-decided pairs the score orders the same way (a tie in the score counts half)."""
    hit = total = 0.0
    for winner, loser in judged:
        w = 1 if weight is None else weight[winner] * weight[loser]
        if not w:
            continue
        total += w
        hit += w * (1.0 if scores[winner] > scores[loser] else 0.5 if scores[winner] == scores[loser] else 0.0)
    return hit / total if total else None


def evaluate(key, answer_sets, scores_by_name, boot=2000, seed=7):
    names = key["items"]
    missing = sorted(n for n in names.values() if n not in scores_by_name)
    if missing:
        raise ValueError("점수가 없는 작품: " + ", ".join(missing))
    scores = {iid: float(scores_by_name[name]) for iid, name in names.items()}
    raters = {}
    for a in answer_sets:  # a rater who sent two files counts once
        raters[str(a.get("rater", "")).strip() or f"익명 {len(raters) + 1}"] = a.get("answers", {})
    units, judged = [], []
    for i, (left, right) in enumerate(key["pairs"]):
        got = [a.get(str(i)) for a in raters.values()]
        got = [v for v in got if v in (left, right, "same")]
        units.append(got)
        c = Counter(got)
        if c[left] != c[right] and max(c[left], c[right]) * 2 > len(got):
            judged.append((left, right) if c[left] > c[right] else (right, left))
    rnd, ids, vals = random.Random(seed), list(names), []
    for _ in range(boot if judged else 0):  # resample works, not pairs: pairs that share a work are not independent
        v = agreement(judged, scores, Counter(rnd.choice(ids) for _ in ids))
        if v is not None:
            vals.append(v)
    vals.sort()
    return {"raters": len(raters), "items": len(names), "pairs": len(key["pairs"]), "decided": len(judged),
            "alpha": krippendorff_alpha(units), "tool_agreement": agreement(judged, scores),
            "interval": (vals[int(0.05 * len(vals))], vals[int(0.95 * len(vals)) - 1]) if len(vals) >= 20 else None}


def markdown(r):
    fmt = lambda v: "-" if v is None else f"{v:.2f}"
    L = ["# 사람 기준 검증", "",
         f"평가자 {r['raters']}명 · 작품 {r['items']}개 · 비교 {r['pairs']}쌍 (과반이 갈린 쌍 {r['decided']}개로 채점)", "",
         "| 항목 | 값 | 읽는 법 |", "|---|---:|---|",
         f"| 사람끼리 일치 (Krippendorff α) | {fmt(r['alpha'])} | 0 = 우연 수준, 0.67 이상이면 잠정 결론 가능 |",
         f"| 도구와 사람의 일치 | {fmt(r['tool_agreement'])}"
         + (f" ({fmt(r['interval'][0])}–{fmt(r['interval'][1])})" if r["interval"] else "")
         + " | 0.50 = 동전 던지기. 괄호는 작품 단위 재표집 90% 구간 |", ""]
    if r["raters"] < MIN_RATERS:
        L.append(f"> 평가자가 {MIN_RATERS}명 미만이라 기준 데이터로 쓸 수 없습니다.")
    if r["alpha"] is not None and r["alpha"] < 0.67:
        L.append("> 사람끼리의 일치가 낮습니다. 도구 일치도를 정확도로 읽지 마세요.")
    if r["interval"] and r["interval"][0] <= 0.5:
        L.append("> 구간이 0.50을 포함합니다. 도구가 우연보다 낫다고 말할 수 없습니다.")
    return "\n".join(L)


PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>비교 평가</title>
<style>
body{margin:0;font:16px/1.5 system-ui,sans-serif;background:#eee;color:#222}
main{max-width:1500px;margin:auto;padding:16px}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:16px}
.work{background:#fff;padding:8px;max-height:70vh;overflow:auto}
.work img{width:100%;display:block;margin-bottom:8px}
button,input{font:inherit;padding:8px 14px;margin:8px 4px 8px 0}
</style>
<main>
<h1>어느 쪽이 더 AI 슬롭처럼 느껴지나요?</h1>
<p>슬롭 = 성의 없이 찍어낸 느낌. AI로 만들었는지를 맞히는 것이 아닙니다. 다른 사람과 상의하지 말고 느낀 대로 고르세요.</p>
<label>평가자 별칭 <input id="who" autocomplete="off"></label> <span id="count"></span>
<div class="two"><div class="work" id="left"></div><div class="work" id="right"></div></div>
<button id="pickLeft">왼쪽이 더</button><button id="pickSame">비슷함 / 모르겠음</button><button id="pickRight">오른쪽이 더</button>
<button id="back">이전</button><button id="save">결과 파일 저장</button>
</main>
<script>
const D = __DATA__, answers = {};
let at = 0;
const el = id => document.getElementById(id);
function show() {
  const done = at >= D.pairs.length;
  el('count').textContent = done ? '끝났습니다. 결과 파일을 저장해 보내 주세요.' : (at + 1) + ' / ' + D.pairs.length;
  for (const [side, k] of [['left', 0], ['right', 1]]) {
    const box = el(side);
    box.replaceChildren();
    box.scrollTop = 0;
    if (!done) for (const src of D.items[D.pairs[at][k]]) { const i = new Image(); i.src = src; i.alt = ''; box.append(i); }
  }
}
function pick(k) {
  if (at >= D.pairs.length) return;
  answers[at] = k === null ? 'same' : D.pairs[at][k];
  at++;
  show();
}
el('pickLeft').onclick = () => pick(0);
el('pickRight').onclick = () => pick(1);
el('pickSame').onclick = () => pick(null);
el('back').onclick = () => { if (at) { at--; show(); } };
el('save').onclick = () => {
  const who = el('who').value.trim();
  if (!who) { el('who').focus(); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify({rater: who, answers})], {type: 'application/json'}));
  a.download = 'answers-' + who.replace(/[^\\p{L}\\p{N}_-]/gu, '_') + '.json';
  a.click();
};
show();
</script></html>
"""


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description="사람 기준 검증 키트")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("items")
    b.add_argument("out")
    b.add_argument("--per-item", type=int, default=6)
    b.add_argument("--seed", type=int, default=7)
    s = sub.add_parser("score")
    s.add_argument("key")
    s.add_argument("answers")
    s.add_argument("scores")
    s.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        if a.cmd == "build":
            print("키 파일(평가자에게 주지 말 것): " + build(_load(a.items), a.out, a.per_item, a.seed))
        else:
            answers = [_load(p) for p in sorted(glob.glob(os.path.join(a.answers, "*.json")))]
            text = markdown(evaluate(_load(a.key), answers, _load(a.scores)))
            if a.out:
                with open(a.out, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
            print(text)
    except (ValueError, OSError, KeyError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
