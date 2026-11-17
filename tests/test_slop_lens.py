"""Run:  python -m unittest discover -s tests -v   (from the repo root, no Python dependencies)

Static calibration always runs. Render tests run only when the Node probe is installed
(`npm install` in the repo root); otherwise they are skipped, never failed.
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slop_lens import scan  # noqa: E402
from slop_lens import render as render_mod  # noqa: E402
from slop_lens.rules import get_rules  # noqa: E402
from slop_lens.rubric import RUBRIC  # noqa: E402

EX = os.path.join(ROOT, "examples")
HAS_RENDER = render_mod.status()["available"]


def ids(res):
    return {f.rule.id for f in res.findings}


def s(name, **kw):
    return scan(os.path.join(EX, name), **kw)


class StaticCalibration(unittest.TestCase):
    """Without a browser the detector must still separate obvious slop from crafted work."""

    def test_sloppy_landing_is_heavy_slop(self):
        r = s("sloppy-landing", render="off")
        self.assertEqual(r.kind, "web")
        self.assertGreaterEqual(r.index, 80)
        for rid in ["VIS-01", "VIS-02", "VIS-09", "LAY-01", "CPY-01", "CPY-02", "CPY-03", "UX-01", "UX-02", "IMG-01", "IMG-03", "IMG-04", "COD-01"]:
            self.assertIn(rid, ids(r), rid)
        self.assertEqual(r.errors, [])

    def test_crafted_landing_is_clean(self):
        r = s("crafted-landing", render="off")
        self.assertLess(r.index, 20, [f.rule.id for f in r.findings])

    def test_sloppy_game(self):
        r = s("sloppy-game", render="off")
        self.assertEqual(r.kind, "game")
        self.assertGreaterEqual(r.index, 60)
        for rid in ["GAM-01", "GAM-03", "GAM-04", "GAM-05", "GAM-06", "GAM-09", "GAM-12"]:
            self.assertIn(rid, ids(r), rid)

    def test_crafted_game_is_clean(self):
        r = s("crafted-game", render="off")
        self.assertEqual(r.kind, "game")
        self.assertLess(r.index, 25, [(f.rule.id, f.detail) for f in r.findings])

    def test_fix_plan_lowers_projection(self):
        r = s("sloppy-landing", render="off")
        proj = [p["index"] for p in r.fix_plan()["projections"]]
        self.assertLessEqual(proj[0], r.index)
        self.assertLessEqual(proj[-1], proj[0])
        self.assertLess(proj[-1], 5)
        self.assertIn("Anti-Slop", r.fix_plan()["brief"])

    def test_real_site_false_positives_stay_fixed(self):
        """Patterns that misfired on real sites during validation (docs/VALIDATION.md)."""
        r = s("fp-regressions", render="off")
        for rid in ["VIS-10", "IMG-03", "VIS-02", "CPY-02", "UX-07", "UX-02"]:
            self.assertNotIn(rid, ids(r), (rid, [(f.rule.id, f.detail) for f in r.findings]))
        self.assertLess(r.index, 15)

    def test_visual_review_blends(self):
        r = s("crafted-landing", render="off")
        before = r.index
        unknown = r.add_visual_answers([{"id": i, "answer": "yes"} for i, (rr, _, _) in RUBRIC.items() if "web" in rr.applies])
        self.assertEqual(unknown, [])
        self.assertGreater(r.index, before + 30)


@unittest.skipUnless(HAS_RENDER, "render probe not installed (npm install)")
class RenderCalibration(unittest.TestCase):
    """With a real browser, measurements replace guesses and must keep (or improve) separation."""

    @classmethod
    def setUpClass(cls):
        cls.r = {n: s(n) for n in ("sloppy-landing", "sloppy-game", "crafted-landing", "crafted-game", "js-handled-links")}

    def test_all_rendered(self):
        for n, r in self.r.items():
            self.assertTrue(r.ctx.render and r.ctx.render.get("ok"), (n, r.ctx.notes))

    def test_separation(self):
        self.assertGreaterEqual(self.r["sloppy-landing"].index, 80)
        self.assertGreaterEqual(self.r["sloppy-game"].index, 60)
        self.assertLess(self.r["crafted-landing"].index, 20, [(f.rule.id, f.detail) for f in self.r["crafted-landing"].findings])
        self.assertLess(self.r["crafted-game"].index, 25, [(f.rule.id, f.detail) for f in self.r["crafted-game"].findings])

    def test_measured_findings_on_slop(self):
        web, game = ids(self.r["sloppy-landing"]), ids(self.r["sloppy-game"])
        for rid in ["RND-01", "RND-14", "RND-10", "RND-12"]:
            self.assertIn(rid, web, rid)
        for rid in ["AUD-03", "RND-G3", "RND-G4", "RND-G7"]:  # no-sound is judged once, by AUD-03 (RND-G2 defers to it)
            self.assertIn(rid, game, rid)
        self.assertNotIn("VIS-01", web)  # superseded by RND-01

    def test_js_handled_links_not_dead(self):
        """Static analysis sees href="#"; real clicks show they work. Measurement must win."""
        static = s("js-handled-links", render="off")
        self.assertIn("UX-01", ids(static))
        r = self.r["js-handled-links"]
        self.assertNotIn("UX-01", ids(r))
        self.assertNotIn("RND-14", ids(r))
        self.assertLess(r.index, 15)

    def test_screenshots_exist(self):
        sh = self.r["sloppy-game"].ctx.render["screenshots"]
        self.assertTrue(sh.get("game") and all(os.path.isfile(p) for p in sh["game"]))
        self.assertTrue(os.path.isfile(self.r["sloppy-landing"].ctx.render["screenshots"]["mobile"]))


class RuleHygiene(unittest.TestCase):
    def test_every_rule_is_complete(self):
        seen = set()
        all_ids = {r.id for r in get_rules()}
        for r in list(get_rules()) + [v[0] for v in RUBRIC.values()]:
            self.assertNotIn(r.id, seen)
            seen.add(r.id)
            self.assertIn(r.kind, ("fingerprint", "quality"))
            self.assertTrue(1 <= r.weight <= 5)
            self.assertTrue(r.why and r.fix.get("summary") and r.fix.get("directive"), r.id)
            self.assertIn(r.fix.get("effort"), ("S", "M", "L"), r.id)
            for rep in r.replaces:
                self.assertIn(rep, all_ids, f"{r.id} replaces unknown {rep}")


class MCPProtocol(unittest.TestCase):
    def test_stdio_roundtrip(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "slop_scan", "arguments": {"target": os.path.join(EX, "sloppy-game"), "format": "json", "render": "off"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "prompts/list"},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "slop_explain_rule", "arguments": {"rule_id": "rnd-14"}}},
        ]
        inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
        p = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "slop-lens-mcp.py")], input=inp.encode("utf-8"),
                           capture_output=True, timeout=120)
        lines = [json.loads(l) for l in p.stdout.decode("utf-8").splitlines() if l.strip()]
        self.assertEqual([l["id"] for l in lines], [1, 2, 3, 4, 5])
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "slop-lens")
        names = {t["name"] for t in lines[1]["result"]["tools"]}
        self.assertTrue({"slop_scan", "slop_visual_rubric", "slop_submit_visual_review", "slop_fix_plan"} <= names)
        self.assertEqual(json.loads(lines[2]["result"]["content"][0]["text"])["kind"], "game")
        self.assertIn("RND-14", lines[4]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
