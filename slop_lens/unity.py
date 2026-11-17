"""Unity adapter: static scene/prefab analysis + runtime capture through the Unity CLI.

Runtime capture never touches the user's project:
  1. mirror the project to a cache folder (Library/Temp/Logs/Builds excluded)
  2. add the com.sloplens.capture package to the COPY's Packages/manifest.json
  3. Unity.exe -batchmode -executeMethod SlopLens.Capture.Editor.BuildForCapture.Run  → Windows player
  4. run the player with -sloplens-out: it presses start buttons, plays with simulated input, records
     frames, the audio mix (speakers muted), sound events, on-screen text/fonts, frame times, errors.
If a Unity MCP server is connected instead, the agent can capture the same artifacts (see SKILL.md).
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "unity", "com.sloplens.capture")
CACHE = os.path.join(tempfile.gettempdir(), "slop-lens", "unity")
EXCLUDE_DIRS = ["Library", "Temp", "Logs", "obj", "Builds", "Build", "UserSettings", ".git", ".vs", ".idea", "SlopLensBuild"]


def is_unity_project(path):
    return os.path.isfile(os.path.join(path, "ProjectSettings", "ProjectVersion.txt")) and os.path.isdir(os.path.join(path, "Assets"))


def project_version(path):
    try:
        txt = open(os.path.join(path, "ProjectSettings", "ProjectVersion.txt"), encoding="utf-8").read()
        m = re.search(r"m_EditorVersion:\s*(\S+)", txt)
        return m.group(1) if m else None
    except OSError:
        return None


def installed_editors():
    roots = [r"C:\Program Files\Unity\Hub\Editor", "/Applications/Unity/Hub/Editor", os.path.expanduser("~/Unity/Hub/Editor")]
    try:
        sec = json.load(open(os.path.join(os.environ.get("APPDATA", ""), "UnityHub", "secondaryInstallPath.json"), encoding="utf-8"))
        if isinstance(sec, str) and sec:
            roots.append(sec)
    except Exception:
        pass
    out = {}
    for r in roots:
        for d in glob.glob(os.path.join(r, "*")):
            exe = os.path.join(d, "Editor", "Unity.exe")
            if not os.path.isfile(exe):
                exe = os.path.join(d, "Unity.app", "Contents", "MacOS", "Unity")
            if os.path.isfile(exe):
                out[os.path.basename(d)] = exe
    return out


def pick_editor(version):
    eds = installed_editors()
    if version in eds:
        return version, eds[version], "exact"
    mm = ".".join((version or "").split(".")[:2])
    same = sorted([v for v in eds if v.startswith(mm + ".")], key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r"[.a-z]+", v) if x])
    if same:
        return same[-1], eds[same[-1]], "same-minor"
    return None, None, "missing"


def _mirror(src, dst):
    os.makedirs(dst, exist_ok=True)
    if os.name == "nt" and shutil.which("robocopy"):
        cmd = ["robocopy", src, dst, "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/MT:16", "/XD"] + EXCLUDE_DIRS
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode >= 8:
            raise RuntimeError("robocopy 실패: " + r.stdout.decode("cp949", "replace")[-300:])
    else:
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*EXCLUDE_DIRS))


def _inject_package(copy):
    mf = os.path.join(copy, "Packages", "manifest.json")
    data = json.load(open(mf, encoding="utf-8"))
    data.setdefault("dependencies", {})["com.sloplens.capture"] = "file:" + PACKAGE.replace("\\", "/")
    json.dump(data, open(mf, "w", encoding="utf-8"), indent=2)


def capture(project, seconds=30, timeout_build=3600, log=print):
    """Mirror → build → play. Returns the capture dict (frames, mix.wav, events …) or {'ok': False, 'error': …}."""
    project = os.path.abspath(project)
    if not is_unity_project(project):
        return {"ok": False, "error": "Unity 프로젝트가 아님"}
    ver = project_version(project)
    use, exe, how = pick_editor(ver)
    if not exe:
        return {"ok": False, "error": f"Unity {ver} 에디터가 설치되어 있지 않음 (Unity Hub에서 설치 필요)", "version": ver}
    key = hashlib.sha1(project.encode("utf-8")).hexdigest()[:10]
    copy = os.path.join(CACHE, f"{os.path.basename(project).replace(' ', '_')}-{key}")
    build_dir = os.path.join(copy, "SlopLensBuild")
    out = os.path.join(copy, "SlopLensCapture", time.strftime("%Y%m%d-%H%M%S"))
    t0 = time.time()
    log(f"[1/3] 원본을 건드리지 않도록 복사본 동기화: {copy}")
    _mirror(project, copy)
    _inject_package(copy)
    log(f"[2/3] Unity {use} ({how})로 Windows 빌드 (첫 실행은 에셋 임포트 때문에 오래 걸림)")
    blog = os.path.join(copy, "sloplens-build.log")
    r = subprocess.run([exe, "-batchmode", "-quit", "-projectPath", copy, "-executeMethod",
                        "SlopLens.Capture.Editor.BuildForCapture.Run", "-sloplensBuild", build_dir, "-logFile", blog],
                       capture_output=True, timeout=timeout_build)
    player = os.path.join(build_dir, "Game.exe")
    if r.returncode != 0 or not os.path.isfile(player):
        tail = ""
        try:
            tail = "\n".join(l for l in open(blog, encoding="utf-8", errors="replace").read().splitlines() if re.search(r"error|Error|failed", l))[-1500:]
        except OSError:
            pass
        return {"ok": False, "error": "Unity 빌드 실패", "editor": use, "log": blog, "log_errors": tail}
    log(f"[3/3] {seconds}초 자동 플레이 캡처 (스피커는 음소거)")
    os.makedirs(out, exist_ok=True)
    proc = subprocess.Popen([player, "-sloplens-out", out, "-sloplens-seconds", str(seconds), "-screen-fullscreen", "0",
                             "-screen-width", "1280", "-screen-height", "720", "-logFile", os.path.join(out, "player.log")])
    time.sleep(3)
    os_input = _drive_os_input(proc, seconds)  # legacy-Input games need real key presses (foreground-only)
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
    cj = os.path.join(out, "capture.json")
    if not os.path.isfile(cj):
        return {"ok": False, "error": "플레이 캡처 결과 없음 (player.log 확인)", "log": os.path.join(out, "player.log")}
    data = json.load(open(cj, encoding="utf-8"))
    data.update({"editor": use, "editor_match": how, "copy": copy, "out": out, "elapsed_s": round(time.time() - t0), "os_input": os_input})
    json.dump(data, open(os.path.join(copy, "SlopLensCapture", "latest.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return data


def latest_capture(project):
    project = os.path.abspath(project)
    key = hashlib.sha1(project.encode("utf-8")).hexdigest()[:10]
    p = os.path.join(CACHE, f"{os.path.basename(project).replace(' ', '_')}-{key}", "SlopLensCapture", "latest.json")
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


# ------------------------------------------------------------------ static YAML analysis
TMP_DEFAULT_FONT = "8f586378b4e144a9851e7b34d9b748ee"                       # LiberationSans SDF
BUILTIN_EXTRA = "0000000000000000f000000000000000"                          # unity_builtin_extra
BUILTIN_DEFAULT = "0000000000000000e000000000000000"                        # unity default resources
DEFAULT_UI_SPRITES = {"10905": "UISprite", "10907": "Background", "10911": "InputFieldBackground", "10913": "Knob",
                      "10901": "Checkmark", "10915": "DropdownArrow", "10917": "UIMask"}
PRIMITIVES = {"10202": "Cube", "10206": "Cylinder", "10207": "Sphere", "10208": "Capsule", "10209": "Plane", "10210": "Quad"}
VENDOR = re.compile(r"[\\/](TextMesh Pro|TutorialInfo|Plugins|_Recovery|ThirdParty|AssetStore|Samples)[\\/]", re.I)


def scan_yaml(project, max_files=600, max_bytes=8_000_000):
    """Count editor defaults that end up on screen: TMP default font, legacy Arial, default UI sprites, primitives."""
    files = [p for p in glob.glob(os.path.join(project, "Assets", "**", "*.unity"), recursive=True) +
             glob.glob(os.path.join(project, "Assets", "**", "*.prefab"), recursive=True) if not VENDOR.search(p)][:max_files]
    res = {"files": len(files), "tmp_total": 0, "tmp_default": 0, "legacy_text_total": 0, "legacy_arial": 0,
           "ui_sprites": {}, "primitives": {}, "default_texts": 0, "examples": {}}
    rx_font = re.compile(r"m_fontAsset: \{fileID: \d+, guid: ([0-9a-f]{32})")
    rx_legacy = re.compile(r"m_Font: \{fileID: (\d+), guid: ([0-9a-f]{32})")
    rx_sprite = re.compile(r"m_Sprite: \{fileID: (\d+), guid: " + BUILTIN_EXTRA)
    rx_mesh = re.compile(r"m_Mesh: \{fileID: (\d+), guid: " + BUILTIN_DEFAULT)
    rx_dtext = re.compile(r"m_[tT]ext: (New Text|Button|Text \(TMP\))\s*$", re.M)
    for f in files:
        try:
            with open(f, "rb") as fh:
                t = fh.read(max_bytes).decode("utf-8", "replace")
        except OSError:
            continue
        rel = os.path.relpath(f, project).replace("\\", "/")
        for g in rx_font.findall(t):
            res["tmp_total"] += 1
            if g == TMP_DEFAULT_FONT:
                res["tmp_default"] += 1
                res["examples"].setdefault("tmp_default", rel)
        for fid, g in rx_legacy.findall(t):
            res["legacy_text_total"] += 1
            if g == BUILTIN_DEFAULT and fid == "10102":
                res["legacy_arial"] += 1
                res["examples"].setdefault("legacy_arial", rel)
        for fid in rx_sprite.findall(t):
            if fid in DEFAULT_UI_SPRITES:
                n = DEFAULT_UI_SPRITES[fid]
                res["ui_sprites"][n] = res["ui_sprites"].get(n, 0) + 1
                res["examples"].setdefault("ui_sprite", rel)
        for fid in rx_mesh.findall(t):
            if fid in PRIMITIVES:
                n = PRIMITIVES[fid]
                res["primitives"][n] = res["primitives"].get(n, 0) + 1
                res["examples"].setdefault("primitive", rel)
        c = len(rx_dtext.findall(t))
        if c:
            res["default_texts"] += c
            res["examples"].setdefault("default_text", rel)
    return res


def fmod_inventory(project):
    """FMOD Studio projects keep events/audio outside Unity's audio system: read the .fspro metadata."""
    out = {"projects": 0, "events": 0, "audio_files": 0, "event_names": [], "banks": 0}
    for fs in glob.glob(os.path.join(project, "**", "*.fspro"), recursive=True):
        if re.search(r"[\/](Library|Builds?|Temp)[\/]", fs):
            continue
        meta = os.path.join(os.path.dirname(fs), "Metadata")
        out["projects"] += 1
        evs = glob.glob(os.path.join(meta, "Event", "*.xml"))
        out["events"] += len(evs)
        out["audio_files"] += len(glob.glob(os.path.join(meta, "AudioFile", "*.xml")))
        for e in evs[:20]:
            try:
                m = re.search(r'<property name="name">\s*<value>([^<]+)', open(e, encoding="utf-8", errors="replace").read())
                if m:
                    out["event_names"].append(m.group(1))
            except OSError:
                pass
    out["banks"] = len([b for b in glob.glob(os.path.join(project, "Assets", "**", "*.bank"), recursive=True)])
    return out


# ------------------------------------------------------------------ OS-level input (legacy UnityEngine.Input games)
def _drive_os_input(proc, seconds, seed=7):
    """Send real key presses / clicks to the player window — ONLY while that window is in the foreground,
    so keystrokes can never land in another application. Windows only; silently does nothing elsewhere."""
    if os.name != "nt":
        return {"sent": 0, "skipped": "non-windows"}
    import ctypes
    import random
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    rnd = random.Random(seed)
    VK = [0x57, 0x41, 0x53, 0x44, 0x20, 0x25, 0x26, 0x27, 0x28, 0x4A, 0x4B, 0x45, 0x46, 0x51, 0x52, 0x31, 0x32, 0x0D, 0xA0]  # WASD Space arrows J K E F Q R 1 2 Enter LShift

    def window_of(pid):
        found = []
        CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(h, _):
            p = wintypes.DWORD()
            u32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid and u32.IsWindowVisible(h):
                found.append(h)
                return False
            return True
        u32.EnumWindows(CB(cb), 0)
        return found[0] if found else None

    def foreground_is(pid):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(p))
        return p.value == pid

    sent, t_end = 0, time.time() + seconds
    hwnd = None
    while proc.poll() is None and time.time() < t_end:
        if hwnd is None:
            hwnd = window_of(proc.pid)
            if hwnd:
                u32.SetForegroundWindow(hwnd)
        if hwnd and foreground_is(proc.pid):
            vk = rnd.choice(VK)
            u32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.08 + rnd.random() * 0.25)
            u32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            sent += 1
            if rnd.random() < 0.3:
                r = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(r))
                x = r.left + int((r.right - r.left) * (0.3 + 0.4 * rnd.random()))
                y = r.top + int((r.bottom - r.top) * (0.3 + 0.4 * rnd.random()))
                if foreground_is(proc.pid):
                    u32.SetCursorPos(x, y)
                    u32.mouse_event(0x0002, 0, 0, 0, 0)
                    u32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.12)
    return {"sent": sent}
