"""Zero-dependency image inspection: dimensions + AI-generator provenance markers."""
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Output sizes that image generators emit by default (DALL·E 3, gpt-image, SD/SDXL, MJ, Flux…)
AI_SIZES = {
    (1024, 1024), (1792, 1024), (1024, 1792), (1536, 1024), (1024, 1536),
    (2048, 2048), (1344, 768), (768, 1344),
    (1216, 832), (832, 1216), (1152, 896), (896, 1152), (1456, 816), (816, 1456),
    (1232, 928), (928, 1232), (1664, 928), (928, 1664), (1408, 768), (768, 1408),
}

# (marker bytes lowercased, label, strong?)  strong=False means "could also be a camera/editor"
MARKERS: List[Tuple[bytes, str, bool]] = [
    (b"trainedalgorithmicmedia", "IPTC DigitalSourceType=AI 생성", True),
    (b"compositewithtrainedalgorithmicmedia", "IPTC: AI 합성", True),
    (b"dall-e", "DALL·E", True),
    (b"dall\xc2\xb7e", "DALL·E", True),
    (b"openai", "OpenAI (gpt-image / DALL·E)", True),
    (b"chatgpt", "ChatGPT 이미지", True),
    (b"midjourney", "Midjourney", True),
    (b"stable diffusion", "Stable Diffusion", True),
    (b"stablediffusion", "Stable Diffusion", True),
    (b"negative prompt:", "Stable Diffusion 프롬프트 파라미터", True),
    (b"comfyui", "ComfyUI", True),
    (b"novelai", "NovelAI", True),
    (b"adobe firefly", "Adobe Firefly", True),
    (b"made with google ai", "Google AI (Imagen/Gemini)", True),
    (b"leonardo.ai", "Leonardo.ai", True),
    (b"ideogram", "Ideogram", True),
    (b"black-forest-labs", "FLUX (Black Forest Labs)", True),
    (b"dreamstudio", "DreamStudio", True),
    (b"c2pa", "C2PA 콘텐츠 자격증명 (AI 또는 편집기)", False),
    (b"jumbf", "JUMBF/C2PA 매니페스트", False),
]

AI_FILENAME = re.compile(
    r"(dall[\s·_\-]?e|chatgpt[\s_\-]?image|gemini[_\-\s]generated|midjourney|\bmj[_\-]|"
    r"stable[_\-\s]?diffusion|sdxl|comfyui[_\-]|firefly|leonardo|ideogram|imagen|image[_\-]?fx|"
    r"generated[_\-\s]image|ai[_\-]generated|_upscaled|upscayl|"
    r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)


@dataclass
class ImageInfo:
    path: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    fmt: str = ""
    generators: List[Tuple[str, bool]] = field(default_factory=list)
    text_chunks: List[str] = field(default_factory=list)
    ai_filename: bool = False

    @property
    def ai_size(self):
        return self.width is not None and (self.width, self.height) in AI_SIZES


def _dims(data: bytes):
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return "png", w, h
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return "gif", w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            n = len(data)
            while i + 9 < n:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
                    i += 1 if marker == 0xFF else 2
                    continue
                seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return "jpeg", w, h
                i += 2 + seglen
            return "jpeg", None, None
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8 ":
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return "webp", w, h
            if chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b"VP8X":
                return "webp", int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
            return "webp", None, None
    except Exception:
        pass
    return "", None, None


def _png_text_chunks(data: bytes):
    out = []
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return out
    i = 8
    n = len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + length]
        i += 12 + length
        try:
            if ctype == b"tEXt":
                k, _, v = body.partition(b"\x00")
                out.append(f"{k.decode('latin-1')}: {v.decode('latin-1', 'replace')[:400]}")
            elif ctype == b"zTXt":
                k, _, rest = body.partition(b"\x00")
                v = zlib.decompress(rest[1:])
                out.append(f"{k.decode('latin-1')}: {v.decode('utf-8', 'replace')[:400]}")
            elif ctype == b"iTXt":
                k, _, rest = body.partition(b"\x00")
                comp_flag = rest[0]
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _tk, _, txt = rest.partition(b"\x00")
                if comp_flag:
                    txt = zlib.decompress(txt)
                out.append(f"{k.decode('latin-1')}: {txt.decode('utf-8', 'replace')[:400]}")
            elif ctype == b"caBX":
                out.append("caBX: C2PA manifest chunk")
            elif ctype == b"IEND":
                break
        except Exception:
            continue
    return out


def analyze_bytes(path: str, data: bytes, total_size: Optional[int] = None) -> ImageInfo:
    fmt, w, h = _dims(data)
    info = ImageInfo(path=path, size_bytes=total_size or len(data), width=w, height=h, fmt=fmt)
    info.text_chunks = _png_text_chunks(data)
    hay = data.lower() + "\n".join(info.text_chunks).lower().encode("utf-8", "ignore")
    seen = set()
    for marker, label, strong in MARKERS:
        if marker in hay and label not in seen:
            seen.add(label)
            info.generators.append((label, strong))
    # A1111 'parameters' chunk with Steps/Sampler is definitive
    for t in info.text_chunks:
        tl = t.lower()
        if (tl.startswith("parameters:") or tl.startswith("prompt:") or tl.startswith("workflow:")) and \
                "Stable Diffusion 프롬프트 파라미터" not in seen:
            seen.add("Stable Diffusion 프롬프트 파라미터")
            info.generators.append(("Stable Diffusion/ComfyUI 프롬프트 파라미터", True))
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    info.ai_filename = bool(AI_FILENAME.search(name)) or bool(re.match(r"ComfyUI_\d+", name))
    return info


def analyze_file(abs_path: str, rel_path: str, max_bytes: int = 12_000_000) -> ImageInfo:
    import os
    size = os.path.getsize(abs_path)
    with open(abs_path, "rb") as f:
        if size <= max_bytes:
            data = f.read()
        else:
            head = f.read(4_000_000)
            f.seek(max(0, size - 1_000_000))
            data = head + f.read()
    return analyze_bytes(rel_path, data, size)
