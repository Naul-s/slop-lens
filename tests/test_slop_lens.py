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


class _Ctx:
    """Minimal scan context for calling one rule directly."""
    def __init__(self, code="", sound=None, exts=(), webgl=True):
        self._code = code
        self.files = [type("F", (), {"ext": e})() for e in exts]
        game = {"hasCanvas": True, "rafFrames": 600, "draw": {"webgl": 1000 if webgl else 0}, "changedDuringPlay": True}
        if sound is not None:
            game["sound"] = sound
        self.render = {"ok": True, "game": game}
        self.unity = None
        self.perception = None

    def joined(self, *roles):
        return self._code


class RegressionFalsePositives(unittest.TestCase):
    """Cases a human reviewer overturned (2026-11-18, a Unity WebGL jam game)."""

    def test_many_different_samples_are_not_repetition(self):
        from slop_lens.model import CLEAN
        from slop_lens.rules.perception import aud_repeat
        varied = {"samplePlays": 38, "distinctSamples": 9, "sampleRateVariety": 1, "oscillatorPlays": 0, "mediaPlays": 0}
        self.assertIs(aud_repeat(_Ctx(sound=varied)), CLEAN)
        same = dict(varied, distinctSamples=1)
        self.assertIsNotNone(getattr(aud_repeat(_Ctx(sound=same)), "count", None))
        old_probe = {k: v for k, v in varied.items() if k != "distinctSamples"}
        self.assertIsNone(aud_repeat(_Ctx(sound=old_probe)))

    def test_compiled_engine_build_skips_code_absence_rules(self):
        from slop_lens.rules.game import gam_audio, gam_juice
        unity_web = "<script src='Build/x.loader.js'></script><script>createUnityInstance(canvas, config)</script>"
        self.assertIsNone(gam_juice(_Ctx(code=unity_web)))
        self.assertIsNone(gam_audio(_Ctx(code=unity_web)))
        # plain hand-written canvas game without juice code is still flagged
        self.assertIsNotNone(gam_juice(_Ctx(code="requestAnimationFrame(loop); ctx.fillRect(0,0,10,10)")))
        # Unity *project* source present → code checks still apply
        self.assertIsNotNone(gam_juice(_Ctx(code=unity_web + " void Update(){}", exts=(".cs",))))


class BlindGameFlow(unittest.TestCase):
    """Games: measurements stay hidden until a review is in, and the record says honestly whether it was blind."""

    def test_unreviewed_game_is_held_and_blind(self):
        from slop_lens import mcp_server
        r = s("crafted-game", render="off")
        self.assertEqual(r.verdict["code"], "UNDECIDED")  # even with a low score
        mcp_server._SCANS[r.id] = r
        out = mcp_server.call_tool("slop_fix_plan", {"scan_id": r.id})["content"][0]["text"]
        self.assertIn("reveal", out)
        self.assertNotIn("Anti-Slop", out)
        from slop_lens import report
        self.assertTrue(report.needs_blind(r))
        self.assertNotIn("rule_id", report.blind_summary(r, as_json=True))

    def test_revealed_measurements_make_review_non_blind_and_cap_confidence(self):
        from slop_lens.review import protocol_markdown
        r = s("sloppy-game", render="off")
        protocol_markdown(r, blind=False)  # shows measured suspicions
        r.add_review([{"id": k, "level": 2} for k in ("S1", "S2", "S3", "S4", "S6", "S7", "S8")],
                     meta={"reviewer": "t", "blind": True, "knew_expected": False})
        self.assertFalse(r.review_meta["blind"])
        self.assertTrue(r.review_meta.get("blind_overridden"))
        self.assertNotEqual(r.to_dict()["confidence"]["level"], "high")

    def test_engine_template_page_not_flagged(self):
        from slop_lens.rules.a11y import a11y_meta
        from slop_lens.rules.visual import vis_hex

        class C(_Ctx):
            platform = "web"
            def displayed_docs(self):
                return [{"has_html_tag": True, "metas": {}}]
        unity = C(code="<script>createUnityInstance(c, cfg)</script> #aaaaaa #bbbbbb")
        self.assertIsNone(a11y_meta(unity))
        self.assertIsNone(vis_hex(unity))


class ReviewMaterial(unittest.TestCase):
    """Hand-taken screenshots join the review; the protocol says how far autoplay got and what the sound was."""

    def test_attached_screenshots_are_listed_and_counted(self):
        import tempfile
        from slop_lens.review import protocol_markdown, review_frames
        r = s("crafted-game", render="off")
        d = tempfile.mkdtemp()
        boss, ending, txt = (os.path.join(d, n) for n in ("boss.png", "ending.jpg", "notes.txt"))
        for p in (boss, ending, txt):
            with open(p, "wb") as f:
                f.write(b"x")
        out = protocol_markdown(r, blind=True, attach=[boss, txt, os.path.join(d, "missing.png"), boss])
        self.assertEqual(r.attachments, [os.path.abspath(boss)])
        self.assertIn("직접 첨부", out)
        self.assertIn("이미지 파일 아님", out)
        self.assertIn("파일 없음", out)
        # a frame note with an absolute path attaches that screenshot too, and counts toward coverage
        r.add_review([{"id": k, "level": 1} for k in ("S1", "S2", "S4", "S7", "S8")], frames=[{"file": ending, "note": "엔딩 화면"}, {"file": boss, "note": "보스"}],
                     meta={"blind": True})
        self.assertIn(os.path.abspath(ending), review_frames(r))
        self.assertEqual(len(r.to_dict()["attachments"]), 2)
        from slop_lens import report
        self.assertIn("직접 첨부한 화면 2장", report.to_markdown(r))

    def test_sound_line_names_distinct_samples(self):
        from slop_lens.review import sound_line
        line = sound_line({"oscillatorPlays": 0, "distinctSynthVoices": [], "samplePlays": 36, "distinctSamples": 8,
                           "mediaFiles": [], "filters": 0, "reverbs": 0, "mix": {"duration": 15.2, "silenceShare": 0.31}})
        self.assertIn("서로 다른 샘플 8종", line)
        self.assertIn("신스 음색 0종", line)
        self.assertNotIn("[]", line)

    def test_autoplay_route_is_reported(self):
        from slop_lens.review import autoplay_lines
        g = {"loadWaitMs": 4200, "menuSteps": ['버튼 "Start"', "Space"], "played_ms": 15000, "recoveries": ["가운데 클릭+Enter"]}
        text = "\n".join(autoplay_lines(g))
        self.assertIn('버튼 "Start" → Space', text)
        self.assertIn("15초", text)
        self.assertIn("멈춘 화면 넘기기", text)
        self.assertIn("못 넘김", "\n".join(autoplay_lines({"menuSteps": []})))
        self.assertEqual(autoplay_lines(None), [])


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
        g = self.r["sloppy-game"].ctx.render.get("game") or {}
        dbg = {k: g.get(k) for k in ("changedDuringPlay", "navigations", "navDuringPlay", "played_ms", "menuSteps")}
        dbg["sound"] = g.get("sound") is not None
        for rid in ["AUD-03", "RND-G3", "RND-G4", "RND-G7"]:  # no-sound is judged once, by AUD-03 (RND-G2 defers to it)
            self.assertIn(rid, game, (rid, dbg))
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
        # ping/list are answered while a tool call runs, so replies are matched by id and not by arrival order
        self.assertEqual(sorted(l["id"] for l in lines), [1, 2, 3, 4, 5])
        lines.sort(key=lambda l: l["id"])
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "slop-lens")
        names = {t["name"] for t in lines[1]["result"]["tools"]}
        self.assertTrue({"slop_scan", "slop_visual_rubric", "slop_submit_visual_review", "slop_fix_plan"} <= names)
        self.assertEqual(json.loads(lines[2]["result"]["content"][0]["text"])["kind"], "game")
        self.assertIn("RND-14", lines[4]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
