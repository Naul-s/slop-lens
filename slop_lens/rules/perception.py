"""Perception rules — judged from what is SEEN and HEARD (assets, frames, recorded audio), not from code.

AUD-*  sound    : synthesized beeps, no variation, missing SFX, AI music provenance, silent play
ART-*  art      : fake pixel art, mixed styles inside one asset set
UNI-*  Unity UI : editor defaults that end up on screen (TMP default font, Arial, default UI skin, primitives)
"""
import collections
import re
import os

from ..model import CLEAN, Evidence, Result, rule
from ._genre import play_reached, realtime


def _p(ctx):
    p = getattr(ctx, "perception", None)
    return p if p and p.get("ok") else None


def _snd(ctx):
    """Runtime sound facts from the web probe or the Unity capture."""
    r = ctx.render if ctx.render and ctx.render.get("ok") else None
    g = (r or {}).get("game") or {}
    if g.get("sound"):
        return "web", g["sound"]
    cap = (getattr(ctx, "unity", None) or {}).get("capture")
    if cap and cap.get("ok"):
        return "unity", cap
    return None, None


def E(text, where="(지각)"):
    return Evidence(where, 0, str(text)[:140])


# ============================================================ sound
@rule(id="AUD-01", title="합성 단음 효과음 (오실레이터 비프)", category="audio", kind="quality", source="perceive",
      weight=4, drivers=["P2", "P1"], applies=["game", "web"], threshold=1, saturation=1,
      why="효과음이 녹음·디자인된 소리가 아니라 사인파/사각파 하나를 짧게 울린 '비프'다. 사람 귀에는 장난감·테스트 소리처럼 들려서 "
          "화면이 아무리 정돈돼 있어도 '코드로 대충 붙인 소리' = AI 슬롭으로 느껴진다. 행동마다 소리의 질감이 같아서 타격·획득·실패가 구별되지 않는다.",
      fix={"summary": "핵심 행동마다 질감이 다른 실제 효과음을 쓰고, 합성음을 쓴다면 레이어·엔벨로프·필터·변주를 설계한다.",
           "steps": ["게임 핵심 행동 4~6개(이동, 성공, 실패, UI 확인, 보상)를 정하고 각자 다른 재료(마찰음, 금속, 눈 밟는 소리 등)로 만든다.",
                     "효과음 라이브러리(Freesound CC0, Sonniss GDC 번들 등)나 직접 녹음한 소리를 편집해 쓴다.",
                     "합성으로 만든다면 노이즈+톤 레이어, ADSR 엔벨로프, 로우패스 필터 스윕, 짧은 리버브를 넣는다.",
                     "같은 소리라도 재생마다 피치 ±5%, 볼륨 ±2dB 무작위 변주를 준다."],
           "example": "// 눈 치우기 한 칸: 노이즈 버스트(눈) + 낮은 톤(삽) 레이어, 필터 스윕, 피치 변주\n"
                      "const n = noiseSource(ctx, 0.18); const f = ctx.createBiquadFilter(); f.type='lowpass';\n"
                      "f.frequency.setValueAtTime(3200, t); f.frequency.exponentialRampToValueAtTime(600, t+0.18);\n"
                      "n.playbackRate.value = 0.95 + Math.random()*0.1;",
           "effort": "M",
           "directive": "효과음을 오실레이터 단음(사인/사각파 비프)으로 만들지 말 것. 행동마다 질감이 다른 실제/디자인된 소리 + 재생마다 변주."})
def aud_synth(ctx):
    src, s = _snd(ctx)
    p = _p(ctx)
    if src == "web" and s:
        plays = s.get("oscillatorPlays", 0)
        if plays and not s.get("samplePlays") and s.get("mediaPlays", 0) <= 1 and not (s.get("filters") or s.get("reverbs")):
            types = ", ".join(f"{k}×{v}" for k, v in (s.get("oscillatorTypes") or {}).items())
            mix = (s.get("mix") or {})
            return Result(1, [E(f"플레이 중 효과음 {plays}회 모두 오실레이터({types}), 녹음 샘플 0개, 필터·리버브 0개"),
                              E(f"녹음된 믹스: 스펙트럼 피크 {mix.get('spectralPeaks')}개, 순음도 {mix.get('tonalPurity')}") if mix else E("믹스 녹음 없음")],
                          f"효과음이 전부 합성 단음 (음색 {len(s.get('distinctSynthVoices') or [])}종)")
        if s.get("samplePlays") or s.get("filters") or s.get("mediaPlays", 0) > 1:
            pass  # sample-based / processed sound: judge the files below
    if p:
        sfx = [a for a in p.get("audio", []) if not a.get("error") and a.get("duration", 9) < 3]
        syn = [a for a in sfx if a.get("synthetic")]
        if len(sfx) >= 3 and len(syn) / len(sfx) >= 0.5:
            return Result(len(syn), [E(f"{a['file']}: 순음도 {a.get('tonalPurity')}, 피크 {a.get('spectralPeaks')}개", a["file"]) for a in syn[:4]],
                          f"짧은 효과음 {len(sfx)}개 중 {len(syn)}개가 단일 음색")
        if sfx:
            return CLEAN
    return None


@rule(id="AUD-02", title="같은 소리의 기계적 반복 (변주 없음)", category="audio", kind="quality", source="perceive",
      weight=3, drivers=["P2"], applies=["game"], threshold=1, saturation=1,
      why="서로 다른 행동에 같은 소리가, 또는 같은 행동에 매번 완전히 똑같은 소리가 난다. 사람은 몇 번만 들어도 반복을 알아채고 '대충 붙인 소리'로 느낀다.",
      fix={"summary": "행동별로 소리를 나누고, 같은 행동은 2~4개 변형을 번갈아 쓰거나 피치·볼륨을 무작위로 바꾼다.",
           "steps": ["행동→소리 대응표를 만든다.", "자주 나는 소리는 변형 3개 이상 + 피치 ±5% 랜덤.", "연속 재생 시 같은 변형이 두 번 연속 나오지 않게 한다."],
           "example": "src.pitch = Random.Range(0.95f, 1.05f); src.PlayOneShot(clips[Random.Range(0, clips.Length)]);",
           "effort": "S", "directive": "같은 효과음을 변주 없이 반복하지 말 것 (변형 여러 개 + 피치/볼륨 랜덤)."})
def aud_repeat(ctx):
    src, s = _snd(ctx)
    if src == "web" and s:
        plays = s.get("oscillatorPlays", 0) + s.get("samplePlays", 0) + s.get("mediaPlays", 0)
        voices = len(s.get("distinctSynthVoices") or []) + (s.get("sampleRateVariety") or 0) + len(set(s.get("mediaFiles") or []))
        if plays >= 4 and voices <= 1:
            return Result(1, [E(f"{plays}회 재생이 모두 같은 음색 {s.get('distinctSynthVoices')}")], "모든 효과음이 같은 소리")
        return CLEAN if plays >= 4 else None
    if src == "unity" and s:
        ev = [e for e in s.get("soundEvents", []) if not e.get("loop")]
        if len(ev) < 4:
            return None
        by = collections.Counter(e["clip"] for e in ev)
        clip, n = by.most_common(1)[0]
        pitches = {e["pitch"] for e in ev if e["clip"] == clip}
        if n >= 5 and len(pitches) == 1:
            return Result(1, [E(f"'{clip}' {n}회 재생, 피치 항상 {next(iter(pitches))}")], f"효과음 {len(ev)}회 중 '{clip}'이 {n}회, 변주 없음")
        return CLEAN
    return None


@rule(id="AUD-03", title="효과음이 없거나 극히 빈약함", category="audio", kind="quality", source="perceive",
      weight=4, drivers=["P2", "P3"], applies=["game"], threshold=1, saturation=1,
      why="게임인데 행동에 반응하는 소리가 없고 배경음악만 흐른다. 입력에 소리 피드백이 없으면 손맛이 사라지고, '프로토타입을 그대로 낸' 인상이 된다.",
      fix={"summary": "입력·판정·보상·실패·UI에 반응하는 효과음 세트를 만든다.",
           "steps": ["리듬게임이라면 판정별 히트음(Perfect/Great/Miss)과 콤보·실패음을 따로 만든다.", "UI 이동·확인·취소음을 넣는다.",
                     "음악과 효과음의 음량 비율을 조정할 믹서 그룹을 둔다."],
           "example": "", "effort": "M", "directive": "입력·판정·보상·실패·UI마다 효과음 필수."})
def aud_missing(ctx):
    p = _p(ctx)
    src, s = _snd(ctx)
    if src == "web" and s:
        if not (s.get("oscillatorPlays") or s.get("samplePlays") or s.get("mediaPlays", 0) > 1):
            if not play_reached(ctx):
                return None  # auto-play never reached the game — silence is unmeasured, not a defect
            return Result(1, [E(f"플레이 중 효과음 0회, 재생된 것은 {s.get('mediaFiles') or '없음'}")], "효과음 0개 (배경음악만)",
                          strength=1.0 if realtime(ctx) else 0.5)
        return CLEAN
    if p is None:
        return None
    sfx = [a for a in p.get("audio", []) if not a.get("error") and a.get("duration", 9) < 3]
    longs = [a for a in p.get("audio", []) if not a.get("error") and a.get("duration", 0) >= 8]
    fm = (getattr(ctx, "unity", None) or {}).get("fmod") or {}
    if fm.get("projects"):
        names = ", ".join(dict.fromkeys(fm.get("event_names") or [])) or "?"
        if fm["events"] <= 2 and not sfx:
            return Result(1, [E(f"FMOD 프로젝트: 이벤트 {fm['events']}개({names}), 오디오 파일 {fm['audio_files']}개"),
                              E(f"Unity 사운드 파일 {p.get('audio_total', 0)}개 중 짧은 효과음 0개")],
                          f"효과음 없음 (FMOD 이벤트 {fm['events']}개: {names})")
        return CLEAN if fm["events"] > 2 else None
    if p.get("audio_total", 0) and not sfx:
        return Result(1, [E(f"사운드 파일 {p['audio_total']}개 모두 8초 이상 음악/환경음: " + ", ".join(a["file"].split('/')[-1] for a in longs[:3]))],
                      "짧은 효과음 파일 0개")
    return CLEAN if sfx else None


@rule(id="AUD-04", title="AI 음악 생성기 흔적", category="audio", kind="fingerprint", source="perceive",
      weight=2, drivers=["P4"], applies=["game", "web"], threshold=1, saturation=2,
      why="음악 파일 메타데이터에 Suno·Udio 같은 생성기 표기가 남아 있다. 생성 음악 자체가 문제는 아니지만, 다듬지 않은 원본은 구조가 평이하고 게임 상황과 맞물리지 않아 '배경에 깔린 무언가'로 들린다.",
      fix={"summary": "생성 음악은 게임 구간·템포·루프 지점에 맞게 편집하고, 핵심 테마는 직접 작곡하거나 편곡한다.",
           "steps": ["루프 지점·인트로·클라이맥스를 게임 흐름에 맞춰 자른다.", "상황별(평상·위기·보상) 변주를 만든다."], "example": "",
           "effort": "M", "directive": "생성 음악은 게임 흐름에 맞게 편집·변주해서 쓸 것."})
def aud_ai_music(ctx):
    p = _p(ctx)
    if p is None:
        return None
    hits = p.get("provenance") or []
    if hits:
        return Result(len(hits), [E(f"{os.path.basename(h['path'])}: {', '.join(h['generators'])}") for h in hits[:4]], f"생성기 표기 음악 {len(hits)}개")
    return CLEAN


@rule(id="AUD-05", title="플레이 대부분이 무음", category="audio", kind="quality", source="perceive",
      weight=2, drivers=["P2"], applies=["game"], threshold=1, saturation=1,
      why="자동 플레이 동안 녹음된 소리의 대부분이 무음이다. 배경음·환경음이 없으면 공간감이 없고 화면이 '비어 있는' 느낌이 든다.",
      fix={"summary": "배경음악 또는 환경음(바람, 군중, 기계음)을 깔고, 행동 효과음과 음량 균형을 맞춘다.", "steps": [], "example": "",
           "effort": "S", "directive": "플레이 중 배경음/환경음이 항상 흐르게 할 것."})
def aud_silent(ctx):
    src, s = _snd(ctx)
    mix = (s or {}).get("mix") if src == "web" else None
    if src == "unity":
        mix = (getattr(ctx, "perception", None) or {}).get("unity_mix")
    if not mix:
        return None
    if mix.get("silenceShare", 0) >= 0.8:
        return Result(1, [E(f"녹음된 {mix.get('duration')}초 중 무음 {round(mix['silenceShare'] * 100)}%")], "플레이 중 대부분 무음")
    return CLEAN


# ============================================================ art
@rule(id="ART-01", title="가짜 픽셀아트 (생성 이미지의 픽셀 흉내)", category="imagery", kind="fingerprint", source="perceive",
      weight=4, drivers=["P4", "P5"], applies=["game", "web"], threshold=1, saturation=4,
      why="멀리서 보면 픽셀아트지만 실제 픽셀 격자가 불규칙하고, 한 칸 안에 노이즈와 수만 가지 색이 섞여 있다. 이미지 생성기가 '픽셀아트 스타일'을 흉내 낸 전형적 결과라서, "
          "진짜 픽셀아트 옆에 두면 흐릿하고 지저분해 보이고 사람들은 'AI로 뽑은 아이콘'이라고 바로 알아챈다.",
      fix={"summary": "픽셀아트라면 목표 해상도(예: 32×32)로 다시 그리거나, 생성 이미지를 축소·팔레트 양자화한 뒤 손으로 정리한다.",
           "steps": ["아이콘 목표 해상도와 팔레트(16~32색)를 정한다.", "생성 이미지를 최근접 이웃으로 목표 해상도까지 줄이고 팔레트로 양자화한다.",
                     "윤곽선·하이라이트를 픽셀 단위로 손으로 정리한다(Aseprite).", "게임에서는 정수 배율 + Point 필터로 확대한다."],
           "example": "# Aseprite: Sprite > Sprite Size 32x32 (Nearest) → Sprite > Color Mode > Indexed (palette 24색)",
           "effort": "M", "directive": "생성 이미지를 '픽셀아트 풍'으로 쓰지 말 것. 실제 픽셀 격자·제한 팔레트로 다시 그릴 것."})
def art_fake_pixel(ctx):
    p = _p(ctx)
    if p is None:
        return None
    imgs = [i for i in p.get("images", []) if not i.get("error")]
    fake = [i for i in imgs if any("가짜 픽셀아트" in t for t in i.get("tags", []))]
    if fake:
        return Result(len(fake), [E(f"{i['file'].split('/')[-1]}: {i['tags'][0]}", i["file"]) for i in fake[:5]],
                      f"분석한 이미지 {len(imgs)}개 중 {len(fake)}개가 가짜 픽셀아트")
    return CLEAN if imgs else None


@rule(id="ART-02", title="한 세트 안에서 아트 스타일 혼재", category="imagery", kind="quality", source="perceive",
      weight=3, drivers=["P5"], applies=["game", "web"], threshold=1, saturation=3,
      why="같은 폴더(같은 용도)의 아이콘·스프라이트가 어떤 것은 픽셀아트, 어떤 것은 페인팅/글로우 스타일이다. 한 사람이 정한 아트 방향이 없다는 신호이고, "
          "여러 번 생성해서 잘 나온 것만 모아 붙인 결과로 보인다.",
      fix={"summary": "세트마다 아트 바이블(해상도, 팔레트, 외곽선, 조명 방향)을 정하고 기준에서 벗어난 에셋을 다시 만든다.",
           "steps": ["세트에서 가장 마음에 드는 1개를 기준으로 고른다.", "해상도·팔레트·테두리 규칙을 문서화한다.", "기준과 다른 에셋을 같은 규칙으로 다시 그린다."],
           "example": "", "effort": "L", "directive": "같은 용도의 에셋은 하나의 아트 바이블(해상도·팔레트·외곽선)로 통일."})
def art_mixed(ctx):
    p = _p(ctx)
    if p is None:
        return None
    groups = collections.defaultdict(list)
    for i in p.get("images", []):
        if i.get("error"):
            continue
        if i.get("abs") and ctx.kind == "web":
            continue  # a web page's photos + illustrations are not one asset set; only games share an art bible
        groups[os.path.dirname(i["file"])].append(i)
    mixed = []
    for d, items in groups.items():
        if len(items) < 4:
            continue
        pix = sum(1 for i in items if i.get("pixelLook"))
        share = pix / len(items)
        lights = [i.get("lightness", 0) for i in items]
        spread = max(lights) - min(lights)
        if 0.25 <= share <= 0.75 or spread > 0.45:
            mixed.append((d, len(items), pix, spread))
    if mixed:
        return Result(len(mixed), [E(f"{d or '(루트)'}: {n}개 중 픽셀풍 {pix}개 / 나머지 다른 화풍, 명도 차 {sp:.2f}", d) for d, n, pix, sp in mixed[:4]],
                      f"스타일이 섞인 에셋 세트 {len(mixed)}개")
    return CLEAN if groups else None


# ---- raw vs. worked-over generated art
# Players split AI-made games by whether the generated images were dropped in as they came out of the generator
# (glossy over-detail everywhere, every image lit differently, generator canvas size) or reworked into one art direction.
_POT = {(1024, 1024), (2048, 2048), (512, 512)}  # power-of-two squares are ordinary textures too
# material maps / tiling textures are not illustrations — their colour is data, not art direction
_MATERIAL = re.compile(r"normal|rough|metal|_ao\b|occlusion|height|disp|spec|bump|diffuse|albedo|basecolor|tile|texture|_tex\b|noise|lut", re.I)


def _rich(i):
    """Painterly / photographic raster (not pixel art, not flat UI, not a screenshot)."""
    return (i.get("colors", 0) >= 4000 and min(i.get("w", 0), i.get("h", 0)) >= 256
            and not i.get("pixelLook") and not i.get("screenLike"))


def _ai_evidence(ctx, i):
    from ..images import AI_SIZES
    prov = {os.path.basename(im.path): im for im in getattr(ctx, "images", [])}
    im = prov.get(os.path.basename(i.get("abs") or i.get("file", "")))
    why = []
    strong = [g for g, s in (im.generators if im else []) if s]
    if strong:
        why.append("생성기 메타데이터(" + ", ".join(dict.fromkeys(strong))[:40] + ")")
    if im and im.ai_filename:
        why.append("생성기 파일명")
    wh = (i.get("w"), i.get("h"))
    if wh in AI_SIZES and wh not in _POT:
        why.append(f"생성기 기본 캔버스 {wh[0]}×{wh[1]} 그대로")
    return why


@rule(id="ART-03", title="AI 생성 이미지를 다듬지 않고 그대로 사용", category="imagery", kind="fingerprint", source="perceive",
      weight=4, drivers=["P4", "P2"], applies=["game", "web"], threshold=1, saturation=4, replaces=["IMG-02"],
      why="생성기에서 나온 그림을 크기·색감·화풍을 손대지 않고 그대로 넣었다. 생성 이미지 특유의 매끈한 광택, 화면 구석까지 고르게 깔린 과한 디테일, "
          "의미 없는 장식이 그대로 남아서 사람들은 '프롬프트 한 번 돌려서 붙였다'는 이질감을 바로 느낀다. "
          "같은 AI 이미지라도 화풍을 맞추고 다듬으면 이 느낌이 크게 줄어든다 — 쓰느냐보다 '그대로 쓰느냐'가 문제다.",
      fix={"summary": "생성 이미지는 초안으로만 쓰고, 게임의 아트 방향(해상도·팔레트·외곽선·조명)에 맞춰 다시 그리거나 후보정한다.",
           "steps": ["아트 바이블을 먼저 정한다(팔레트 16~32색, 외곽선 두께, 광원 방향, 디테일 밀도).",
                     "생성 이미지를 그 기준으로 크롭·리사이즈하고 팔레트·색보정(LUT)을 한 번에 적용한다.",
                     "초점이 되는 부분만 디테일을 남기고 나머지는 단순화한다(실루엣이 읽히게).",
                     "의미 없는 장식·뭉개진 글자·손가락 같은 아티팩트를 손으로 지운다.",
                     "카드·배경처럼 반복되는 이미지는 같은 프레임·같은 조명으로 통일한다."],
           "example": "# 일괄 톤 맞춤: magick in.png -resize 640x -modulate 100,85 -posterize 24 -remap palette.png out.png",
           "effort": "M", "directive": "생성 이미지를 생성기 출력 그대로 쓰지 말 것. 아트 바이블에 맞춰 리사이즈·팔레트·보정·아티팩트 제거 후 사용."})
def art_raw(ctx):
    p = _p(ctx)
    if p is None:
        return None
    imgs = [i for i in p.get("images", []) if not i.get("error")]
    raw = []
    for i in imgs:
        if not _rich(i):
            continue
        why = _ai_evidence(ctx, i)
        if why:
            look = " · 디테일이 화면 전체에 고르게 퍼짐(초점 없음)" if i.get("detailEvenness", 0) >= 0.8 else ""
            raw.append((i, why, look))
    if raw:
        strong = sum(1 for _, w, _ in raw if any("메타데이터" in x or "파일명" in x for x in w))
        return Result(len(raw), [E(f"{os.path.basename(i['file'])}: {', '.join(w)}{lk}", i["file"]) for i, w, lk in raw[:5]],
                      f"그림 이미지 {sum(1 for i in imgs if _rich(i))}개 중 {len(raw)}개가 생성기 출력 그대로" + (f" (출처 표기 {strong}개)" if strong else ""),
                      strength=min(1.0, 0.5 + 0.15 * len(raw) + 0.15 * strong))
    return CLEAN if any(_rich(i) for i in imgs) else None


@rule(id="ART-04", title="이미지마다 조명·색감이 제각각 (톤 통일 안 됨)", category="imagery", kind="quality", source="perceive",
      weight=3, drivers=["P5", "P2"], applies=["game"], threshold=1, saturation=1,
      why="같은 게임 안의 그림들이 하나는 어둡고 채도 낮은 사진풍, 하나는 밝고 쨍한 일러스트처럼 장마다 조명과 색감이 다르다. "
          "프롬프트를 장마다 따로 돌리면 생기는 전형적 결과로, 한 세계의 그림이 아니라 '여러 번 뽑아 모은 그림'으로 보인다.",
      fix={"summary": "모든 그림에 같은 색보정(LUT)·같은 광원 방향·같은 채도 범위를 적용해 한 세계의 톤으로 묶는다.",
           "steps": ["기준 이미지 1장을 정하고 그 명도·채도·색온도를 수치로 기록한다.", "나머지 이미지를 같은 LUT로 보정한다.",
                     "보정해도 안 맞는 이미지는 다시 만든다."],
           "example": "", "effort": "M", "directive": "모든 일러스트를 하나의 LUT·광원·채도 범위로 통일."})
def art_tone(ctx):
    p = _p(ctx)
    if p is None:
        return None
    rich = [i for i in p.get("images", []) if not i.get("error") and _rich(i) and not _MATERIAL.search(os.path.basename(i.get("file", "")))]
    if len(rich) < 4:
        return None
    if not any(_ai_evidence(ctx, i) for i in rich) and sum(i.get("detailEvenness", 0) for i in rich) / len(rich) < 0.8:
        return CLEAN  # no sign these are generated; photos of a real catalogue may vary legitimately

    def sd(xs):
        m = sum(xs) / len(xs)
        return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
    L, S = [i.get("lightness", 0) for i in rich], [i.get("saturation", 0) for i in rich]
    if sd(L) >= 0.12 and sd(S) >= 0.10:
        ev = [E(f"{os.path.basename(i['file'])}: 명도 {i.get('lightness', 0):.2f} · 채도 {i.get('saturation', 0):.2f}", i["file"])
              for i in sorted(rich, key=lambda x: x.get("lightness", 0))[:: max(1, len(rich) // 5)][:5]]
        return Result(1, ev, f"그림 {len(rich)}개의 명도 편차 {sd(L):.2f}, 채도 편차 {sd(S):.2f}")
    return CLEAN


# ============================================================ Unity editor defaults on screen
def _uy(ctx):
    u = getattr(ctx, "unity", None) or {}
    return u.get("yaml")


@rule(id="UNI-01", title="TextMeshPro 기본 폰트(LiberationSans SDF) 그대로 사용", category="visual", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1"], applies=["game"], threshold=1, saturation=1,
      why="화면 글자 대부분이 TextMeshPro를 처음 추가하면 들어 있는 LiberationSans SDF다. 게임의 분위기와 상관없는 '엔진 기본 글꼴'이라서, "
          "사람들은 UI를 보자마자 템플릿·프로토타입으로 인식한다.",
      fix={"summary": "게임 아트 방향에 맞는 폰트(한글 포함)로 TMP 폰트 에셋을 만들어 기본값을 교체한다.",
           "steps": ["제목용·본문용 폰트를 고른다 (예: 픽셀풍이면 Galmuri/둥근모, 판타지면 세리프 계열).", "Window > TextMeshPro > Font Asset Creator로 SDF 에셋 생성.",
                     "Project Settings > TextMesh Pro > Default Font Asset을 교체하고, 기존 텍스트의 폰트를 일괄 변경."],
           "example": "", "effort": "S", "directive": "TextMeshPro 기본 폰트(LiberationSans SDF) 금지. 게임 아트 방향에 맞는 폰트 에셋 사용."})
def uni_tmp(ctx):
    y = _uy(ctx)
    if not y or not y.get("tmp_total"):
        return None
    share = y["tmp_default"] / y["tmp_total"]
    if share >= 0.4:
        return Result(1, [E(f"TMP 텍스트 {y['tmp_total']}개 중 {y['tmp_default']}개 ({share:.0%})가 LiberationSans SDF", y["examples"].get("tmp_default", ""))],
                      f"TMP 기본 폰트 {share:.0%}", strength=min(1.0, 0.4 + share * 0.6))
    return CLEAN


@rule(id="UNI-02", title="레거시 기본 폰트(Arial) UI 텍스트", category="visual", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1", "P3"], applies=["game"], threshold=10, saturation=60,
      why="uGUI Text의 기본 Arial이 그대로 쓰였다. 해상도에 따라 흐릿하고 모양도 엔진 기본값이라 '아직 UI를 만들지 않은' 화면처럼 보인다.",
      fix={"summary": "레거시 Text를 TextMeshPro로 바꾸고 게임 폰트를 지정한다.", "steps": ["Text → TextMeshProUGUI로 교체.", "공통 텍스트 스타일(프리셋)을 만든다."],
           "example": "", "effort": "M", "directive": "uGUI 기본 Arial 텍스트 금지."})
def uni_arial(ctx):
    y = _uy(ctx)
    if not y:
        return None
    n = y.get("legacy_arial", 0)
    return Result(n, [E(f"Arial(기본) 텍스트 {n}개", y["examples"].get("legacy_arial", ""))], f"기본 Arial 텍스트 {n}개") if n else CLEAN


@rule(id="UNI-03", title="Unity 기본 UI 스프라이트(Background·UISprite·Knob)", category="visual", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1"], applies=["game"], threshold=8, saturation=60,
      why="패널·버튼·슬라이더가 Unity를 설치하면 들어 있는 회색 둥근 사각형(Background/UISprite) 그대로다. 수많은 튜토리얼·프로토타입과 똑같은 모양이라 즉시 '기본 UI'로 보인다.",
      fix={"summary": "게임 아트와 같은 규칙으로 UI 스킨(9-slice 패널, 버튼 상태별 이미지)을 만든다.",
           "steps": ["패널·버튼·슬롯 3종부터 9-slice 스프라이트로 만든다.", "버튼 Normal/Hover/Pressed/Disabled 상태를 디자인한다.", "Sprite Atlas로 묶는다."],
           "example": "", "effort": "M", "directive": "Unity 기본 UI 스프라이트 금지. 게임 아트에 맞는 9-slice UI 스킨 사용."})
def uni_sprites(ctx):
    y = _uy(ctx)
    if not y:
        return None
    n = sum((y.get("ui_sprites") or {}).values())
    return Result(n, [E(", ".join(f"{k} {v}" for k, v in y["ui_sprites"].items()), y["examples"].get("ui_sprite", ""))], f"기본 UI 스프라이트 {n}곳") if n else CLEAN


@rule(id="UNI-04", title="기본 도형 메시(Cube·Sphere·Capsule)로 만든 오브젝트", category="game", kind="quality", source="perceive",
      weight=3, drivers=["P2", "P3"], applies=["game"], threshold=5, saturation=30,
      why="플레이어·적·지형이 Unity 기본 큐브/구/캡슐이다. 3D 프로그래머 아트의 대표 모습이라 '프로토타입'으로 보인다.",
      fix={"summary": "핵심 오브젝트부터 모델(직접 제작·에셋)로 교체하고, 도형을 유지한다면 의도된 로우폴리 스타일(머티리얼·윤곽·조명)을 설계한다.",
           "steps": [], "example": "", "effort": "L", "directive": "Unity 기본 도형 메시를 최종 비주얼로 쓰지 말 것."})
def uni_primitives(ctx):
    y = _uy(ctx)
    if not y:
        return None
    n = sum((y.get("primitives") or {}).values())
    return Result(n, [E(", ".join(f"{k} {v}" for k, v in y["primitives"].items()), y["examples"].get("primitive", ""))], f"기본 도형 {n}개") if n else CLEAN


@rule(id="UNI-05", title="기본 문구('New Text', 'Button') 잔존", category="a11y", kind="quality", source="perceive",
      weight=3, drivers=["P3"], applies=["game"], threshold=1, saturation=3,
      why="씬·프리팹에 'New Text', 'Button' 같은 생성 직후 기본 문구가 남아 있다. 화면에 노출되면 즉시 미완성으로 보인다.",
      fix={"summary": "기본 문구를 실제 문구로 바꾸거나 사용하지 않는 오브젝트를 지운다.", "steps": [], "example": "", "effort": "S",
           "directive": "'New Text'/'Button' 등 기본 문구 금지."})
def uni_default_text(ctx):
    y = _uy(ctx)
    if not y:
        return None
    n = y.get("default_texts", 0)
    return Result(n, [E(f"기본 문구 {n}곳", y["examples"].get("default_text", ""))], f"기본 문구 {n}곳") if n else CLEAN


# ============================================================ screen color schemes
FAMILIES = {
    "purple_tech": ("보라·남색 테크 톤", "어두운 바탕 위 보라·남색 그라디언트는 'AI·미래·테크'를 요청받은 생성물의 평균값이다.",
                    "브랜드·세계관에서 1차색을 도출하고(예: 실제 사진·소재에서 추출), 보라 계열은 의도가 있을 때만 쓴다."),
    "dark_teal": ("어두운 청록 시네마틱 톤", "검정에 가까운 청록 바탕에 시안 하이라이트는 생성 이미지·게임 UI에서 가장 흔한 '분위기 있어 보이는' 기본 배색이다. "
                  "어떤 장르에도 붙어서 작품의 정체성을 지운다.", "작품의 장면(시간대, 장소, 소재)에서 팔레트를 뽑고, 강조색 1개를 고유하게 정한다. 배경은 단색 어둠 대신 장면의 질감으로."),
    "pastel_sky": ("파스텔 하늘색 바탕", "화면 대부분이 옅은 하늘색 평면이다. '깔끔하고 아늑한' 느낌을 내려는 AI 게임·앱의 기본 배경이라 무엇을 하는 공간인지가 사라진다.",
                   "배경을 장면으로 채운다(땅·건물·하늘의 그라데이션과 소품). 평면 배경을 쓴다면 질감·조명 변화를 준다."),
    "neon_cyber": ("네온 마젠타·시안 사이버 톤", "어두운 바탕 위 마젠타+시안 네온은 '사이버' 프롬프트의 평균값이다.", "네온은 상호작용 피드백 1~2곳으로 제한하고 바탕 팔레트를 저채도로."),
    "cream_cozy": ("크림·베이지 '코지' 톤", "화면 대부분이 크림·베이지 평면이다. '따뜻하고 아늑한' 요청의 기본값이라 개성이 약하다.", "베이지 대신 소재(종이·나무·천)의 실제 질감과 고유 강조색을 쓴다."),
}


def _family(f):
    out = []
    tc = f.get("topColors") or []
    f = dict(f, primaryShare_top=(tc[0].get("share", 0) if tc else 0))
    if f.get("purpleBlue", 0) >= 0.15 and (f.get("darkShare", 0) >= 0.3 or f.get("purpleBlue", 0) >= 0.3):
        out.append("purple_tech")
    flat_brand = (f.get("primaryShare_top") or 0) >= 0.5  # one solid field = a flat brand colour, not the cinematic gradient
    if f.get("darkShare", 0) >= 0.4 and f.get("tealCyan", 0) >= 0.15 and f.get("tealCyan", 0) >= 3 * f.get("purpleBlue", 0) and not flat_brand:
        out.append("dark_teal")
    if f.get("skyLight", 0) >= 0.4:
        out.append("pastel_sky")
    if f.get("darkShare", 0) >= 0.4 and f.get("magenta", 0) >= 0.04 and f.get("tealCyan", 0) >= 0.04:
        out.append("neon_cyber")
    if f.get("cream", 0) >= 0.35:
        out.append("cream_cozy")
    return out


def _frames(ctx):
    p = _p(ctx)
    fr = [f for f in (p or {}).get("frames", []) if not f.get("error") and "desktop-full" not in str(f.get("file", ""))]
    return fr or None


def _fname(f):
    return os.path.basename(f.get("file") or f.get("path", ""))


@rule(id="COL-01", title="AI 상투 배색 (화면 전체 색 구성)", category="visual", kind="fingerprint", source="perceive",
      weight=3, drivers=["P1"], applies=["web", "game"], threshold=1, saturation=1,
      why="화면 대부분을 차지하는 색 구성이 AI 생성물에서 반복적으로 보이는 배색(보라 테크, 어두운 청록 시네마틱, 파스텔 하늘, 네온 사이버, 크림 코지)과 일치한다. "
          "사람들은 개별 요소보다 먼저 전체 색으로 첫인상을 정하기 때문에, 배색이 평균값이면 내용을 보기 전에 '어디서 본 것'으로 분류한다.",
      fix={"summary": "작품의 장면·소재·브랜드에서 팔레트를 도출한다(배경 1, 중성 2, 강조 1). 강조색은 다른 작품과 겹치지 않게 고른다.",
           "steps": ["작품을 대표하는 실제 장면/사진 1장을 정한다.", "그 장면에서 5~6색을 추출해 팔레트로 만든다(Coolors, Adobe Color).",
                     "배경을 단색 평면 대신 그 팔레트의 질감·그라데이션으로 채운다.", "강조색은 핵심 행동 1~2곳에만 쓴다."],
           "example": "", "effort": "M", "directive": "보라 테크·어두운 청록·파스텔 하늘·네온 사이버·크림 코지 같은 평균 배색 금지. 작품의 장면에서 팔레트를 도출할 것."})
def col_scheme(ctx):
    fr = _frames(ctx)
    if not fr:
        return None
    usable = [f for f in fr if f.get("darkShare", 0) < 0.95]  # loading / failed black screens say nothing about the palette
    if not usable:
        return None
    counts = {}
    for f in usable:
        for fam in _family(f):
            counts.setdefault(fam, []).append(f)
    if not counts:
        return CLEAN
    fam, hit = max(counts.items(), key=lambda kv: len(kv[1]))
    if len(hit) / len(usable) < 0.5:
        return CLEAN
    name, why, fix = FAMILIES[fam]
    orange = [f for f in hit if 0.005 <= f.get("orange", 0) <= 0.15]
    accent = " + 주황 강조색" if orange else ""
    ev = [E(f"{_fname(f)}: 상위 색 {', '.join(c['hex'] + ' ' + str(round(c['share'] * 100)) + '%' for c in f.get('topColors', [])[:3])}", _fname(f)) for f in hit[:4]]
    ev.append(E(f"왜: {why}"))
    ev.append(E(f"해결 방향: {fix}"))
    others = [FAMILIES[k][0] for k in counts if k != fam]
    return Result(1, ev, f"{name}{accent} — 화면 {len(usable)}장 중 {len(hit)}장" + (f" (그 외: {', '.join(others)})" if others else ""))


@rule(id="COL-02", title="빈 단색 화면 (환경·배경 아트 부재)", category="visual", kind="quality", source="perceive",
      weight=3, drivers=["P2", "P3"], applies=["game"], threshold=1, saturation=1,
      why="플레이 화면의 대부분이 한 가지 색 평면이다(단색 잔디, 하늘색 바탕). 공간·장소를 보여주는 환경 아트가 없어서 '테스트 씬'처럼 비어 보이고, "
          "캐릭터와 오브젝트가 어디에 있는지 감정이 생기지 않는다.",
      fix={"summary": "바닥 타일셋·소품·조명·원경으로 공간을 채운다. 평면을 유지한다면 질감·명암 변화와 경계를 준다.",
           "steps": ["플레이 공간의 장소를 정한다(숲 가장자리, 마을 마당 등).", "바닥 타일 변형 3~4종과 소품 5~10종을 배치한다.",
                     "원경·그림자·조명으로 깊이를 만든다."], "example": "", "effort": "L",
           "directive": "플레이 화면을 단색 평면으로 두지 말 것. 장소를 보여주는 환경 아트로 채울 것."})
def col_flat(ctx):
    fr = _frames(ctx)
    if not fr:
        return None
    play = [f for f in fr if f.get("darkShare", 0) < 0.95 and not re.search(r"desktop|mobile|start", _fname(f))]
    if not play:
        return None
    def flat(f):
        top3 = sum(c["share"] for c in (f.get("topColors") or [])[:3])
        band = max(f.get(k, 0) for k in ("green", "skyLight", "tealCyan", "cream", "purpleBlue"))
        return top3 >= 0.6 or band >= 0.6, top3, band
    hits = [(f, *flat(f)[1:]) for f in play if flat(f)[0]]
    if len(hits) / len(play) >= 0.5:
        return Result(1, [E(f"{_fname(f)}: 상위 3색이 화면의 {t3:.0%}, 한 색 계열 {b:.0%}", _fname(f)) for f, t3, b in hits[:4]],
                      f"플레이 화면 {len(play)}장 중 {len(hits)}장이 단색 평면 위주")
    return CLEAN


@rule(id="COL-03", title="순색 원색 UI 요소 (#ff0000 같은 기본 색)", category="visual", kind="quality", source="perceive",
      weight=2, drivers=["P1", "P3"], applies=["game"], threshold=1, saturation=1,
      why="체력 바·게이지·표시가 순수 빨강/초록/파랑 같은 기본 색이다. 팔레트를 정하지 않고 엔진·코드 기본값을 그대로 쓴 '프로그래머 컬러'라서 화면이 거칠어 보인다.",
      fix={"summary": "UI 색을 게임 팔레트에서 가져오고, 게이지에는 프레임·그라데이션·여백을 준다.", "steps": [], "example": "hpFill.color = palette.Danger; // #c8473d",
           "effort": "S", "directive": "UI에 순색 원색(#ff0000, #00ff00, #0000ff) 금지. 게임 팔레트 색만."})
def col_primary(ctx):
    fr = _frames(ctx)
    if not fr:
        return None
    play = [f for f in fr if f.get("darkShare", 0) < 0.95]
    hits = [f for f in play if f.get("primaryShare", 0) >= 0.004]
    if play and len(hits) / len(play) >= 0.5:
        return Result(1, [E(f"{_fname(f)}: 순색 픽셀 {f['primaryShare']:.1%}", _fname(f)) for f in hits[:3]], f"화면 {len(play)}장 중 {len(hits)}장에 순색 원색 UI")
    return CLEAN if play else None
