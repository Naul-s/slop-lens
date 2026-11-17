#!/usr/bin/env python3
"""Run SlopLens over a list of real targets and save results for validation.

  python scripts/validate.py targets.json [--out validation/results]

targets.json: [{"name": "...", "target": "path-or-url", "group": "...", "kind": "auto", "render": "auto"}, ...]
Writes <out>/<name>.json (full report) and <out>/summary.json, prints one line per target.
"""
import json
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from slop_lens import scan  # noqa: E402


def main():
    targets = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "validation", "results")
    out = os.path.abspath(out)
    shots_root = os.path.join(os.path.dirname(out), "shots")
    if os.name == "nt" and not out.startswith("\\\\?\\"):
        out = "\\\\?\\" + out  # long scratch paths exceed Windows MAX_PATH
    os.makedirs(out, exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    summary = []
    for t in targets:
        t0 = time.time()
        shots = os.path.join(shots_root, t["name"])
        try:
            r = scan(t["target"], t.get("kind", "auto"), t.get("render", "auto"), os.path.abspath(shots))
            d = r.to_dict()
            with open(os.path.join(out, t["name"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            row = {"name": t["name"], "group": t.get("group"), "index": d["slop_index"], "verdict": d["verdict"]["label"],
                   "kind": d["kind"], "G": d["axes"]["genericness"], "E": d["axes"]["effort_deficit"],
                   "rendered": d["context"].get("rendered"), "conf": d["confidence"]["label"],
                   "top": [(f["rule_id"], f["impact"]) for f in d["findings"][:8]], "notes": d["context"]["notes"],
                   "files": d["context"]["files"], "words": d["context"]["words"], "secs": round(time.time() - t0, 1)}
        except Exception as e:
            row = {"name": t["name"], "group": t.get("group"), "error": f"{e.__class__.__name__}: {e}", "trace": traceback.format_exc()[-600:]}
        summary.append(row)
        print(json.dumps(row, ensure_ascii=False))
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
