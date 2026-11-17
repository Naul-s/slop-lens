#!/usr/bin/env python3
"""Summarize validation/results: per-target scores and which rules fire on professional sites
(a rule that fires on most corporate sites is a false-positive suspect)."""
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "validation", "results")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

summary = json.load(open(os.path.join(RES, "summary.json"), encoding="utf-8"))
groups = {r["name"]: r.get("group") for r in summary}
print(f"{'target':24} {'group':10} {'index':>5} {'G':>4} {'E':>4}  verdict / conf / rendered")
for r in summary:
    if "error" in r:
        print(f"{r['name']:24} {r['group']:10} ERROR {r['error'][:90]}")
        continue
    print(f"{r['name']:24} {r['group']:10} {r['index']:5.0f} {r['G']:4.0f} {r['E']:4.0f}  {r['verdict']} / {r['conf']} / {r['rendered']}")

fires = collections.defaultdict(lambda: collections.Counter())
details = collections.defaultdict(list)
for p in glob.glob(os.path.join(RES, "*.json")):
    name = os.path.basename(p)[:-5]
    if name == "summary" or name not in groups:
        continue
    d = json.load(open(p, encoding="utf-8"))
    for f in d["findings"]:
        fires[f["rule_id"]][groups[name]] += 1
        details[f["rule_id"]].append((name, f["impact"], f["detail"][:90]))

n_corp = sum(1 for g in groups.values() if g == "corporate")
print(f"\nRules firing on corporate sites (n={n_corp}) — false-positive suspects first:")
for rid, c in sorted(fires.items(), key=lambda x: -x[1]["corporate"]):
    if c["corporate"]:
        print(f"  {rid:8} corporate {c['corporate']}/{n_corp}  others {sum(v for k, v in c.items() if k != 'corporate')}")
        for name, imp, det in details[rid]:
            if groups[name] == "corporate":
                print(f"      - {name}: {imp} · {det}")
