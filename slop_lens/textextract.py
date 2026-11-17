"""Extract human-visible copy, headings, buttons and images from markup/scripts."""
import re
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "code", "pre"}
SECTION_TAGS = {"section", "header", "footer", "nav", "main", "article", "div", "aside"}


class _HTMLExtract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts = []
        self.skip = 0
        self.title = None
        self._in_title = False
        self.lang = None
        self.has_html_tag = False
        self.headings = []      # (level, text, line)
        self._h = None
        self.imgs = []          # (line, src, alt|None)
        self.metas = {}
        self.links = []         # attr dicts of <link>
        self.markers = []       # section ids / aria-labels / classes (line, text)
        self.buttons = []       # (text, line)
        self._btn = None
        self.scripts_src = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        line = self.getpos()[0]
        if self.skip:
            if tag in SKIP_TAGS:
                self.skip += 1
            return
        if tag == "html":
            self.has_html_tag = True
            self.lang = a.get("lang") or None
        if tag == "script" and a.get("src"):
            self.scripts_src.append(a["src"])
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag == "title":
            self._in_title = True
            self.title = ""
        if tag in ("h1", "h2", "h3"):
            self._h = [int(tag[1]), [], line]
        if tag == "img":
            self.imgs.append((line, a.get("src", ""), a.get("alt") if "alt" in a else None))
        if tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.metas[key] = a.get("content", "")
            if a.get("charset"):
                self.metas["charset"] = a["charset"]
        if tag == "link":
            self.links.append(a)
        if tag in SECTION_TAGS:
            parts = [a.get("id", ""), a.get("aria-label", "")]
            if tag != "div":
                parts.append(a.get("class", ""))
            txt = " ".join(p for p in parts if p).strip()
            if txt:
                self.markers.append((line, txt))
        if tag in ("button", "a"):
            self._btn = [tag, [], line]

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3") and self._h:
            self.headings.append((self._h[0], " ".join(self._h[1]).strip(), self._h[2]))
            self._h = None
        if tag in ("button", "a") and self._btn:
            self.buttons.append((" ".join(self._btn[1]).strip(), self._btn[2]))
            self._btn = None

    def handle_data(self, data):
        if self._in_title and self.title is not None:
            self.title += data
            return
        if self.skip:
            return
        t = data.strip()
        if not t:
            return
        self.texts.append(t)
        if self._h:
            self._h[1].append(t)
        if self._btn:
            self._btn[1].append(t)


def extract_html(text):
    p = _HTMLExtract()
    try:
        p.feed(text)
        p.close()
    except Exception:
        pass
    inline_scripts = re.findall(r"<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", text, re.I)
    return {
        "texts": p.texts,
        "title": (p.title or "").strip() if p.title is not None else None,
        "lang": p.lang,
        "has_html_tag": p.has_html_tag,
        "headings": p.headings,
        "imgs": p.imgs,
        "metas": p.metas,
        "links": p.links,
        "markers": p.markers,
        "buttons": p.buttons,
        "inline_scripts": inline_scripts,
        "scripts_src": p.scripts_src,
    }


_TAG = re.compile(r"<[^>]+>")
_BRACES = re.compile(r"\{[^{}]*\}")
_JSX_TEXT = re.compile(r">\s*([^<>{}]*[A-Za-z가-힣][^<>{}]*?)\s*<")
_JSX_HEAD = re.compile(r"<h([1-3])\b[^>]*>([\s\S]*?)</h\1>", re.I)
_JSX_BTN = re.compile(r"<(button|a|Link|Button|NavLink)\b[^>]*>([\s\S]{0,240}?)</\1>")
_JSX_IMG = re.compile(r"<(img|Image)\b([^>]*?)/?>")
_JSX_MARK = re.compile(r"<(section|header|footer|nav|main|article)\b[^>]*?(?:id|aria-label|className|class)\s*=\s*[\"'{`]([^\"'`}]+)", re.I)
_STR = re.compile(r"([\"'`])((?:\\.|(?!\1)[^\\\n]){8,280})\1")
_CLASSY = re.compile(r"[!\-]?[a-z0-9]+(?:[:\-/\[\].#%][a-z0-9\-\[\]#%./_]*)+")


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _clean(s):
    s = _BRACES.sub(" ", s)
    s = _TAG.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def looks_like_copy(s):
    """Heuristic: is a string literal human-facing copy (not classes/urls/code)?"""
    s = s.strip()
    if len(s) < 8 or " " not in s:
        return False
    if re.search(r"https?://|^[./@~]|\.(js|css|png|jpg|svg|json)\b|=>|function\s*\(|;\s*$|^\s*<", s):
        return False
    if not re.search(r"[A-Za-z가-힣]{3,}", s):
        return False
    tokens = s.split()
    classy = sum(1 for t in tokens if _CLASSY.fullmatch(t))
    if classy / max(1, len(tokens)) > 0.45:
        return False
    return True


def extract_jsx(text):
    """Very forgiving extraction for JSX/TSX/Vue/Svelte/Astro templates."""
    texts = []
    for m in _JSX_TEXT.finditer(text):
        t = m.group(1).strip()
        if t and not re.search(r"[;=]\s*$|^\s*(const|let|var|return|import|export)\b", t):
            texts.append(t)
    headings = []
    for m in _JSX_HEAD.finditer(text):
        t = _clean(m.group(2))
        if t:
            headings.append((int(m.group(1)), t, _line(text, m.start())))
    buttons = []
    for m in _JSX_BTN.finditer(text):
        t = _clean(m.group(2))
        if t:
            buttons.append((t, _line(text, m.start())))
    imgs = []
    for m in _JSX_IMG.finditer(text):
        attrs = m.group(2)
        src = re.search(r"src\s*=\s*[{\"']+([^\"'}]+)", attrs)
        alt = re.search(r"alt\s*=\s*[{\"'`]+([^\"'`}]*)", attrs)
        imgs.append((_line(text, m.start()), src.group(1) if src else "",
                     alt.group(1) if alt else None))
    markers = [(_line(text, m.start()), m.group(2)) for m in _JSX_MARK.finditer(text)]
    return {"texts": texts, "headings": headings, "buttons": buttons, "imgs": imgs, "markers": markers}


def extract_script_strings(text):
    out = []
    for m in _STR.finditer(text):
        s = re.sub(r"\$\{[^}]*\}", " ", m.group(2))
        if looks_like_copy(s):
            out.append(s.strip())
    return out


WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?|[가-힣]+")


def count_words(text):
    return len(WORD.findall(text))
