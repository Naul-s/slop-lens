"""Collect a project (folder, single file or URL) into an analyzable Context."""
import bisect
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

from .images import ImageInfo, analyze_bytes, analyze_file
from .model import Evidence
from .textextract import count_words, extract_html, extract_jsx, extract_script_strings

SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit",
    ".output", ".vercel", ".turbo", ".cache", "coverage", "__pycache__", ".venv", "venv", "env",
    "vendor", "Library", "Temp", "Logs", "obj", ".godot", ".import", "target", ".idea", ".vscode",
    ".slop-lens", "Packages", "bower_components",
    # vendored third-party code (Unity add-ons, asset-store packs) is not the author's work
    "Build", "Builds", "TextMesh Pro", "TutorialInfo", "Plugins", "ThirdParty", "Third Party", "AssetStore", "_Recovery",
    # tests are not user-facing
    "e2e", "test", "tests", "__tests__", "spec", "cypress", "playwright-report",
}
TEST_FILE = re.compile(r"\.(test|spec|stories)\.[jt]sx?$|Tests?\.cs$", re.I)
HTML_EXT = {".html", ".htm"}
TEMPLATE_EXT = {".jsx", ".tsx", ".vue", ".svelte", ".astro", ".php", ".erb", ".hbs", ".njk", ".liquid", ".ejs", ".mdx"}
STYLE_EXT = {".css", ".scss", ".sass", ".less", ".styl", ".pcss"}
SCRIPT_EXT = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
GAME_EXT = {".gd", ".cs", ".lua", ".gml", ".hx"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
CONFIG_NAMES = re.compile(r"^(tailwind\.config|theme|tokens|design-tokens)\.", re.I)
MAX_TEXT = 1_500_000
MAX_FILES = 3000
MAX_IMAGES = 400
UA = "SlopLens/0.1 (static design analyzer)"


class SourceFile:
    def __init__(self, path: str, text: str, ext: str, roles: set):
        self.path = path
        self.text = text
        self.ext = ext
        self.roles = roles
        self._nl = None

    def line_of(self, pos: int) -> int:
        if self._nl is None:
            self._nl = [m.start() for m in re.finditer("\n", self.text)]
        return bisect.bisect_right(self._nl, pos - 1) + 1

    def snippet(self, pos: int, end: int, width: int = 110) -> str:
        ls = self.text.rfind("\n", 0, pos) + 1
        le = self.text.find("\n", end)
        le = len(self.text) if le == -1 else le
        line = self.text[ls:le].strip()
        if len(line) > width:
            rel = pos - ls - (len(self.text[ls:le]) - len(self.text[ls:le].lstrip()))
            start = max(0, rel - width // 3)
            line = ("…" if start else "") + line[start:start + width] + "…"
        return line


def _roles_for(name: str, ext: str) -> set:
    roles = set()
    if ext in HTML_EXT:
        roles |= {"markup", "html", "style", "script"}
    if ext in TEMPLATE_EXT:
        roles |= {"markup", "template"}
    if ext in STYLE_EXT:
        roles.add("style")
    if ext in SCRIPT_EXT:
        roles.add("script")
    if ext in (".vue", ".svelte", ".astro"):
        roles.add("style")
    if ext in GAME_EXT:
        roles |= {"script", "engine"}
    if CONFIG_NAMES.match(name):
        roles.add("config")
    return roles


class Context:
    def __init__(self, target: str, source: str):
        self.target = target
        self.source = source  # dir | file | url
        self.files: List[SourceFile] = []
        self.images: List[ImageInfo] = []
        self.kind = "web"
        self.kind_reason = ""
        self.visible_parts: List[str] = []
        self.headings: List[Tuple[int, str, str, int]] = []  # level, text, file, line
        self.buttons: List[Tuple[str, str, int]] = []        # text, file, line
        self.imgs: List[Tuple[str, int, str, Optional[str]]] = []  # file, line, src, alt
        self.markers: List[Tuple[str, int, str]] = []        # file, line, text
        self.html_docs: List[dict] = []                      # per html file meta
        self.notes: List[str] = []
        self._joined: Dict[tuple, str] = {}
        self.render: Optional[dict] = None   # measurements from the Node render probe
        self.platform = "site"                # site | extension
        self.rendered_dom = False             # True when markup is the browser's rendered DOM (URL mode)

    def displayed_docs(self):
        """HTML documents a person actually sees (excludes extension offscreen/background pages)."""
        return [d for d in self.html_docs if not re.search(r"(^|/)(offscreen|background)\.html$", d["file"])]

    def _reset_derived(self):
        self.files, self.visible_parts, self.headings, self.buttons = [], [], [], []
        self.imgs, self.markers, self.html_docs, self._joined = [], [], [], {}

    def ingest_rendered(self, html: str):
        """URL mode: replace server HTML with the rendered DOM (handles SPAs).
        Local mode: only borrow visible copy when the source itself has almost none (SPA bundles)."""
        if not html:
            return
        if self.source == "url":
            keep = [f for f in self.files if f.path != "index.html"]
            self._reset_derived()
            self.add_text_file("index.html", html)
            self.rendered_dom = True
            for f in keep:
                self.add_text_file(f.path, f.text)
                if self.files and self.files[-1].path == f.path:
                    self.files[-1].roles = f.roles
            self.notes = [n for n in self.notes if not n.startswith("URL 모드: 서버가") and not n.startswith("자산 로드 실패")]
            self.notes.append("URL 모드: 브라우저가 렌더링한 DOM 기준으로 분석했습니다 (SPA 포함).")
        elif self.word_count < 80:
            d = extract_html(html)
            if count_words(" ".join(d["texts"])) >= 120:
                self.visible_parts.extend(d["texts"])
                for lvl, t, ln in d["headings"]:
                    self.headings.append((lvl, t, "(rendered)", ln))
                for t, ln in d["buttons"]:
                    self.buttons.append((t, "(rendered)", ln))
                self.notes.append("소스에 보이는 문구가 거의 없어 렌더링된 화면의 문구를 카피 분석에 사용했습니다.")

    # ---------- helpers used by rules ----------
    def by_role(self, *roles) -> Iterable[SourceFile]:
        rs = set(roles)
        return [f for f in self.files if f.roles & rs]

    def joined(self, *roles) -> str:
        key = tuple(sorted(roles))
        if key not in self._joined:
            self._joined[key] = "\n".join(f.text for f in self.by_role(*roles))
        return self._joined[key]

    def has(self, pattern, *roles, flags=re.I) -> bool:
        rx = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
        return any(rx.search(f.text) for f in self.by_role(*roles))

    def grep(self, pattern, *roles, flags=re.I, max_ev=6, files=None, group=0, skip_comments=False):
        rx = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
        count = 0
        ev: List[Evidence] = []
        for f in (files if files is not None else self.by_role(*roles)):
            for m in rx.finditer(f.text):
                if skip_comments:
                    ls = f.text.rfind("\n", 0, m.start()) + 1
                    if re.search(r"//|^\s*\*|<!--", f.text[ls:m.start()]):
                        continue
                count += 1
                if len(ev) < max_ev:
                    ev.append(Evidence(f.path, f.line_of(m.start()), f.snippet(m.start(), m.end())))
        return count, ev

    def class_strings(self):
        """Yield (file, pos, class_string) for class/className attributes."""
        rx = re.compile(r"\bclass(?:Name)?\s*=\s*(?:\{\s*)?[\"'`]([^\"'`]{3,})[\"'`]")
        for f in self.by_role("markup"):
            for m in rx.finditer(f.text):
                yield f, m.start(), m.group(1)
        # clsx/cn() helpers and @apply
        rx2 = re.compile(r"(?:cn|clsx|cva|twMerge|classNames)\(\s*[\"'`]([^\"'`]{3,})[\"'`]")
        rx3 = re.compile(r"@apply\s+([^;]+);")
        for f in self.by_role("script", "markup"):
            for m in rx2.finditer(f.text):
                yield f, m.start(), m.group(1)
        for f in self.by_role("style"):
            for m in rx3.finditer(f.text):
                yield f, m.start(), m.group(1)

    @property
    def visible_text(self) -> str:
        return "\n".join(self.visible_parts)

    @property
    def word_count(self) -> int:
        return count_words(self.visible_text)

    def summary(self):
        roles = {}
        for f in self.files:
            for r in f.roles:
                roles[r] = roles.get(r, 0) + 1
        return {
            "target": self.target, "source": self.source, "kind": self.kind,
            "kind_reason": self.kind_reason, "files": len(self.files), "roles": roles,
            "images": len(self.images), "words": self.word_count,
            "headings": len(self.headings), "notes": self.notes,
            "rendered": bool(self.render and self.render.get("ok")),
        }

    # ---------- ingestion ----------
    def add_text_file(self, rel: str, text: str):
        name = rel.replace("\\", "/").rsplit("/", 1)[-1]
        ext = os.path.splitext(name)[1].lower()
        roles = _roles_for(name, ext)
        if not roles:
            return
        if re.search(r"\.min\.(js|css)$", name) or len(text) > MAX_TEXT:
            return
        sf = SourceFile(rel.replace("\\", "/"), text, ext, roles)
        self.files.append(sf)
        if "html" in roles:
            d = extract_html(text)
            self.visible_parts.extend(d["texts"])
            for lvl, t, ln in d["headings"]:
                self.headings.append((lvl, t, sf.path, ln))
            for t, ln in d["buttons"]:
                self.buttons.append((t, sf.path, ln))
            for ln, src, alt in d["imgs"]:
                self.imgs.append((sf.path, ln, src, alt))
            for ln, t in d["markers"]:
                self.markers.append((sf.path, ln, t))
            for s in d["inline_scripts"]:
                self.visible_parts.extend(extract_script_strings(s))
            d["file"] = sf.path
            self.html_docs.append(d)
        elif "template" in roles:
            d = extract_jsx(text)
            self.visible_parts.extend(d["texts"])
            for lvl, t, ln in d["headings"]:
                self.headings.append((lvl, t, sf.path, ln))
            for t, ln in d["buttons"]:
                self.buttons.append((t, sf.path, ln))
            for ln, src, alt in d["imgs"]:
                self.imgs.append((sf.path, ln, src, alt))
            for ln, t in d["markers"]:
                self.markers.append((sf.path, ln, t))
        if "script" in roles and "html" not in roles:
            self.visible_parts.extend(extract_script_strings(text))

    def detect_platform(self):
        root = self.target if os.path.isdir(self.target) else os.path.dirname(self.target)
        for cand in ("manifest.json", "public/manifest.json", "src/manifest.json", "dist/manifest.json"):
            p = os.path.join(root, cand)
            if os.path.isfile(p):
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read(20000)
                except OSError:
                    continue
                if '"manifest_version"' in txt:
                    self.platform = "extension"
                    self.notes.append("브라우저 확장 프로그램으로 판단: 공유 메타데이터·반응형·viewport 규칙은 적용하지 않습니다.")
                    return

    def detect_kind(self, forced: str = "auto"):
        if forced in ("web", "game"):
            self.kind, self.kind_reason = forced, "사용자 지정"
            return
        allcode = self.joined("script", "markup", "engine")
        signals, pts = [], 0
        pats = [
            (r"getContext\(\s*[\"'](?:2d|webgl2?)", "canvas 렌더링", 2),
            (r"requestAnimationFrame", "애니메이션 루프", 1),
            (r"\b(Phaser|PIXI|kaboom|kontra|excalibur|Babylon|littlejs|melonJS)\b", "게임 프레임워크", 3),
            (r"\bnew\s+THREE\.|from\s+[\"']three[\"']", "Three.js", 1),
            (r"MonoBehaviour|extends\s+(Node2D|Node3D|CharacterBody2D|KinematicBody2D|Area2D)|love\.update", "게임 엔진 스크립트", 3),
            (r"game\s*over|gameover|\bgameLoop\b|\bspawn(?:Enemy|Enemies)?\b|\benemies\b|\bcollision\b", "게임 로직 키워드", 1),
            (r"\b(?:let|var|const|this\.)\s*(?:score|lives|hp|health)\b|\bplayer\s*[=:.]", "점수/플레이어 상태", 1),
            (r"ArrowLeft|ArrowRight|KeyW|keys\[|keyCode\s*===?\s*3[2789]", "실시간 키 입력", 1),
        ]
        for p, label, w in pats:
            if re.search(p, allcode, re.I if w < 3 else 0):
                signals.append(label)
                pts += w
        playable = "실시간 키 입력" in signals or "게임 로직 키워드" in signals and "점수/플레이어 상태" in signals
        if (pts >= 4 and "canvas 렌더링" in signals and playable) or any(s in signals for s in ("게임 프레임워크", "게임 엔진 스크립트")):
            self.kind = "game"
        else:
            self.kind = "web"
        self.kind_reason = ", ".join(signals) if signals else "게임 신호 없음 → 웹"


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT + 1)
        if b"\x00" in raw[:4000]:
            return None
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return None


def from_path(target: str) -> Context:
    target = os.path.abspath(target)
    if os.path.isfile(target):
        ctx = Context(target, "file")
        root = os.path.dirname(target)
        name = os.path.basename(target)
        text = _read_text(target)
        if text is not None:
            ctx.add_text_file(name, text)
        # images referenced from this file that exist locally
        for f in ctx.files:
            for m in re.finditer(r"(?:src|href)\s*=\s*[\"']([^\"'#?]+\.(?:png|jpe?g|webp|gif|avif))", f.text, re.I):
                p = os.path.normpath(os.path.join(root, m.group(1)))
                if os.path.isfile(p) and len(ctx.images) < MAX_IMAGES:
                    ctx.images.append(analyze_file(p, os.path.relpath(p, root).replace("\\", "/")))
        return ctx
    if not os.path.isdir(target):
        raise FileNotFoundError(f"대상이 존재하지 않습니다: {target}")
    ctx = Context(target, "dir")
    real_root = os.path.realpath(target)
    n = 0
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ap = os.path.join(dirpath, fn)
            rel = os.path.relpath(ap, target).replace("\\", "/")
            ext = os.path.splitext(fn)[1].lower()
            if os.path.islink(ap):  # a link could pull files from outside the project into the report
                real = os.path.realpath(ap)
                if not real.startswith(os.path.join(real_root, "")):
                    continue
            if ext in IMAGE_EXT:
                if len(ctx.images) < MAX_IMAGES:
                    try:
                        ctx.images.append(analyze_file(ap, rel))
                    except OSError:
                        pass
                continue
            if not _roles_for(fn, ext) or TEST_FILE.search(fn):
                continue
            n += 1
            if n > MAX_FILES:
                ctx.notes.append(f"파일이 {MAX_FILES}개를 넘어 일부만 분석했습니다.")
                break
            text = _read_text(ap)
            if text is not None:
                ctx.add_text_file(rel, text)
    return ctx


def _fetch(url: str, limit: int) -> Tuple[bytes, str]:
    import time as _time
    import urllib.error as _ue
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    for wait in (2, 6, None):  # rate-limited hosts (429/503) usually answer after a short pause
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                ctype = r.headers.get("Content-Type", "")
                return r.read(limit), ctype
        except _ue.HTTPError as e:
            if e.code not in (429, 503) or wait is None:
                raise
            _time.sleep(wait)


def from_url(url: str) -> Context:
    ctx = Context(url, "url")
    try:
        data, _ = _fetch(url, 3_000_000)
        html = data.decode("utf-8", errors="replace")
    except Exception as e:  # the browser may still load it (bot walls, odd TLS) — render results take over
        ctx.notes.append(f"서버 HTML을 직접 받지 못함({e.__class__.__name__}: {str(e)[:80]}) → 브라우저 렌더 결과만으로 분석")
        html = "<!doctype html><html><head></head><body></body></html>"
    ctx.add_text_file("index.html", html)
    host = urllib.parse.urlparse(url).netloc
    d = ctx.html_docs[0] if ctx.html_docs else {"links": [], "scripts_src": [], "imgs": []}
    assets = []
    for l in d["links"]:
        if "stylesheet" in (l.get("rel") or "").lower() and l.get("href"):
            assets.append(("css", l["href"]))
    for s in d["scripts_src"]:
        assets.append(("js", s))
    fetched = 0
    for kind, href in assets:
        full = urllib.parse.urljoin(url, href)
        if urllib.parse.urlparse(full).netloc != host or fetched >= 20:
            continue
        try:
            body, _ = _fetch(full, 1_500_000)
            name = urllib.parse.urlparse(full).path.rsplit("/", 1)[-1] or f"asset.{kind}"
            if not name.endswith("." + kind):
                name += "." + kind
            ctx.add_text_file(f"remote/{name}", body.decode("utf-8", errors="replace"))
            if kind == "js" and ctx.files and ctx.files[-1].path == f"remote/{name}":
                ctx.files[-1].roles = {"bundle"}  # minified app + library code: not the author's handwriting
            fetched += 1
        except Exception as e:  # noqa
            ctx.notes.append(f"자산 로드 실패: {full} ({e.__class__.__name__})")
    imgs = 0
    for _file, _ln, src, _alt in list(ctx.imgs):
        if not src or src.startswith("data:") or imgs >= 15:
            continue
        full = urllib.parse.urljoin(url, src)
        if urllib.parse.urlparse(full).netloc != host:
            continue
        try:
            body, _ = _fetch(full, 6_000_000)
            ctx.images.append(analyze_bytes(urllib.parse.urlparse(full).path, body))
            imgs += 1
        except Exception:
            pass
    ctx.notes.append("URL 모드: 서버가 내려준 HTML 기준 분석입니다. JS로 렌더링되는 SPA는 소스 폴더로 검사하면 더 정확합니다.")
    return ctx


def build_context(target: str, kind: str = "auto") -> Context:
    if re.match(r"^https?://", target, re.I):
        ctx = from_url(target)
    else:
        ctx = from_path(target)
    if ctx.source != "url":
        ctx.detect_platform()
    ctx.detect_kind(kind)
    return ctx
