"""What kind of game this is, and whether automatic play actually reached it.

Held-out validation (2026-11-17) showed game rules penalising human-made games for two non-AI reasons:
  1. the probe never got past the start menu, and "no reaction / no sound / no juice" was read as a defect;
  2. action-game expectations (juice, pause, difficulty curve, rAF loop) were applied to turn-based, idle and text games.
Rules call these helpers to return None (unmeasured / not applicable) instead of a finding.
"""
import re


def _g(ctx):
    r = ctx.render if ctx.render and ctx.render.get("ok") else None
    return (r or {}).get("game")


def play_reached(ctx):
    """True/False when measured, None when there was no runtime play at all."""
    g = _g(ctx)
    if g is None:
        return None
    return bool(g.get("changedDuringPlay") or g.get("audioCalls") or any((g.get("juice") or {}).values())
                or ((g.get("sound") or {}).get("samplePlays") or 0) or ((g.get("sound") or {}).get("oscillatorPlays") or 0))


RT_CODE = re.compile(r"requestAnimationFrame|new\s+Phaser\.Game|PIXI\.Application|THREE\.WebGLRenderer|kaboom\(|"
                     r"getContext\(\s*[\"'](?:2d|webgl2?)[\"']", re.I)


ENGINE_BUILD = re.compile(r"createUnityInstance|UnityLoader\.instantiate|\.unityweb\b|GODOT_CONFIG|godot\.(?:js|wasm|pck)", re.I)


def compiled_build(ctx):
    """A web export of a compiled engine (Unity WebGL, Godot): the game logic ships as wasm/data, not readable
    source. Rules that flag a feature because it is *absent from the code* must not run on these."""
    if any(f.ext in (".cs", ".gd") for f in getattr(ctx, "files", [])):
        return False  # the project source is here, so code checks are meaningful
    code = ctx.joined("script", "engine", "markup") if hasattr(ctx, "joined") else ""
    return bool(ENGINE_BUILD.search(code))


def realtime(ctx):
    """Real-time (action) game: a large canvas driven by a frame loop. Turn-based / idle / DOM games are not."""
    if getattr(ctx, "unity", None):
        return True  # Unity scenes run a frame loop; genre is judged by the reviewer
    g = _g(ctx)
    if g is not None and "hasCanvas" in g:
        return bool(g.get("hasCanvas")) and (g.get("rafFrames", 0) > 30 or bool((g.get("draw") or {}).get("webgl")))
    code = ctx.joined("script", "engine", "markup") if hasattr(ctx, "joined") else ""
    return bool(RT_CODE.search(code))
