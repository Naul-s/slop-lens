"""Perception layer: collect what people SEE and HEAR, measure it, and build review sheets.

Sources
  - project assets (icons, sprites, UI art, sound effects, music)
  - render probe output (screenshots, gameplay frames, the recorded Web Audio mix and synth usage)
  - Unity capture output (frames, recorded mix, sound events, on-screen text/fonts)
Output goes to ctx.perception and feeds the AUD-/ART-/UNI- rules and the perception review.
"""
import glob
import json
import os
import re
import subprocess
import tempfile

from . import render as _render

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
AUD_EXT = (".wav", ".mp3", ".ogg", ".m4a")
SKIP = re.compile(r"[\\/](node_modules|Library|Temp|Logs|obj|Builds?|dist|\.git|TextMesh Pro|TutorialInfo|Plugins|_Recovery|"
                  r"ThirdParty|AssetStore|Samples|Packages|coverage|e2e|tests?|docs?|screenshots?|captures?|verification|evidence|"
                  r"reviews?|mockups?|SlopLensCapture|SlopLensBuild)[\\/]", re.I)
PRIORITY = re.compile(r"icon|ui|hud|sprite|character|player|hero|enemy|monster|boss|item|weapon|skill|card|portrait|jacket|"
                      r"cover|background|bg|tile|effect|vfx|logo|title|button|아이콘|캐릭터", re.I)
NOT_ART = re.compile(r"(_n|_normal|_mask|_metal|_rough|_ao|_height|lightmap|noise|gradient|lut|splat|reflection)\.", re.I)
AI_AUDIO = [(b"suno", "Suno"), (b"udio", "Udio"), (b"aiva", "AIVA"), (b"soundraw", "Soundraw"), (b"mubert", "Mubert"),
            (b"elevenlabs", "ElevenLabs"), (b"stable audio", "Stable Audio"), (b"musicgen", "MusicGen"),
            (b"riffusion", "Riffusion"), (b"boomy", "Boomy"), (b"beatoven", "Beatoven")]


def _walk(root, exts, limit=4000):
    out = []
    for dp, dn, fn in os.walk(root):
        if SKIP.search(dp + os.sep):
            dn[:] = []
            continue
        for f in fn:
            if f.lower().endswith(exts):
                out.append(os.path.join(dp, f))
                if len(out) >= limit:
                    return out
    return out


def pick_images(root, cap=48):
    # Unity: only what ships (Assets/), never docs or captures next to it
    if os.path.isdir(os.path.join(root, "Assets")) and os.path.isdir(os.path.join(root, "ProjectSettings")):
        root = os.path.join(root, "Assets")
    files = [p for p in _walk(root, IMG_EXT) if not NOT_ART.search(os.path.basename(p))]
    sized = []
    for p in files:
        try:
            s = os.path.getsize(p)
        except OSError:
            continue
        if 2_000 <= s <= 12_000_000:
            sized.append((0 if PRIORITY.search(p) else 1, -s, p))
    sized.sort()
    # keep folder variety: at most 8 per folder
    per, out = {}, []
    for _, _, p in sized:
        d = os.path.dirname(p)
        if per.get(d, 0) >= 8:
            continue
        per[d] = per.get(d, 0) + 1
        out.append(p)
        if len(out) >= cap:
            break
    return out


def pick_audio(root, cap=40):
    files = _walk(root, AUD_EXT)
    per, out = {}, []
    for p in sorted(files):
        d = os.path.dirname(p)
        if per.get(d, 0) >= 4:
            continue
        per[d] = per.get(d, 0) + 1
        out.append(p)
        if len(out) >= cap:
            break
    return out, len(files)


def audio_provenance(paths):
    hits = []
    for p in paths:
        try:
            with open(p, "rb") as f:
                head = f.read(400_000).lower()
        except OSError:
            continue
        found = [name for marker, name in AI_AUDIO if marker in head]
        if found:
            hits.append({"path": p, "generators": found})
    return hits


def run(ctx, out_dir=None, extra_frames=(), extra_audio=(), timeout=300, extra_images=()):
    """Analyze assets + frames for ctx. Returns perception dict (or {'ok': False, ...})."""
    st = _render.status()
    root = ctx.target if os.path.isdir(ctx.target) else os.path.dirname(ctx.target)
    if ctx.source == "url":
        root = None
    images = pick_images(root) if root else []
    audio, audio_total = pick_audio(root) if root else ([], 0)
    frames = list(extra_frames)
    if ctx.render and ctx.render.get("ok"):
        sh = ctx.render.get("screenshots") or {}
        frames = [v for k, v in sh.items() if k in ("desktop", "mobile", "desktopFull") and v] + list(sh.get("game") or []) + frames
    res = {"ok": False, "images_total": len(images) + len(extra_images), "audio_total": audio_total, "provenance": audio_provenance(audio)}
    if not st["available"]:
        res["error"] = st["reason"]
        return res
    out_dir = out_dir or os.path.join(tempfile.gettempdir(), "slop-lens", "perception", os.path.basename(root or "url"))
    os.makedirs(out_dir, exist_ok=True)
    roots, rel = {}, lambda key, base, p: f"{key}/" + os.path.relpath(p, base).replace("\\", "/")
    spec = {"roots": roots, "images": [], "audio": [], "frames": [], "out": out_dir}
    if root:
        roots["p"] = root
        spec["images"] = [rel("p", root, p) for p in images]
        spec["audio"] = [rel("p", root, p) for p in audio]
    for i, f in enumerate(frames):
        if f and os.path.isfile(f):
            roots[f"f{i}"] = os.path.dirname(f)
            spec["frames"].append(f"f{i}/" + os.path.basename(f))
    for i, f in enumerate(extra_images):  # art the rendered page actually loaded (URL targets)
        if f and os.path.isfile(f) and len(spec["images"]) < 48:
            roots[f"i{i}"] = os.path.dirname(f)
            spec["images"].append(f"i{i}/" + os.path.basename(f))
    for i, f in enumerate(extra_audio):
        if f and os.path.isfile(f):
            roots[f"x{i}"] = os.path.dirname(f)
            spec["audio"].append(f"x{i}/" + os.path.basename(f))
    sp = os.path.join(out_dir, "spec.json")
    with open(sp, "w", encoding="utf-8") as _f:
        json.dump(spec, _f, ensure_ascii=False)
    try:
        p = subprocess.run([st["node"], os.path.join(_render.PROBE_DIR, "perceive.mjs"), "--spec", sp], capture_output=True,
                           timeout=timeout, cwd=_render.PROBE_DIR)
        data = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except Exception as e:
        res["error"] = f"지각 분석 실패: {e.__class__.__name__}"
        return res
    data.update({k: v for k, v in res.items() if k not in data})
    # map served keys back to real paths for evidence
    fmap = {f"f{i}/" + os.path.basename(f): f for i, f in enumerate(frames) if f and os.path.isfile(f)}
    for fr in data.get("frames", []):
        fr["file"] = fmap.get(fr["path"], fr["path"])
    for item in data.get("images", []) + data.get("audio", []):
        key, _, r = item["path"].partition("/")
        item["file"] = os.path.relpath(os.path.join(roots.get(key, ""), r), root).replace("\\", "/") if root and key == "p" else r
        if key.startswith("i"):
            item["abs"] = os.path.join(roots.get(key, ""), r)
    # recorded mixes (e.g. Unity capture mix.wav) are reported separately from asset files
    mixes = [a for a in data.get("audio", []) if a["path"].startswith("x")]
    data["audio"] = [a for a in data.get("audio", []) if not a["path"].startswith("x")]
    if mixes:
        data["unity_mix"] = mixes[0]
    return data
