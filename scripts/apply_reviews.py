#!/usr/bin/env python3
"""Re-scan each target and apply its review → <final_dir>/<name>-final.json

  python scripts/apply_reviews.py <targets.json> <reviews_dir> <final_dir> [--shots DIR]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from slop_lens import scan  # noqa: E402


def longpath(p):
    p = os.path.abspath(p)
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def main():
    a = sys.argv[1:]
    targets = json.load(open(a[0], encoding="utf-8"))
    rdir, fdir = longpath(a[1]), longpath(a[2])
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    os.makedirs(fdir, exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
    for t in targets:
        rp = os.path.join(rdir, t["name"] + "-review.json")
        if not os.path.exists(rp):
            print(t["name"], "리뷰 없음 — 건너뜀")
            continue
        try:
            r = scan(t["target"], t.get("kind", "auto"), t.get("render", "auto"), os.path.join(shots, t["name"]) if shots else None)
            rv = json.load(open(rp, encoding="utf-8"))
            r.add_review(rv.get("review", []), rv.get("frames"), rv.get("meta"))
            with open(os.path.join(fdir, t["name"] + "-final.json"), "w", encoding="utf-8") as f:
                json.dump(r.to_dict(), f, ensure_ascii=False, indent=1)
            print(t["name"], "ok")
        except Exception as e:
            print(t["name"], "ERR", type(e).__name__, str(e)[:120])


if __name__ == "__main__":
    main()
