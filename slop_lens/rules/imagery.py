"""Imagery / asset signals: generator provenance, AI sizes, placeholder services."""
import re

from ..images import AI_FILENAME
from ..model import Evidence, Result, rule


@rule(id="IMG-01", title="AI 이미지 생성기 메타데이터가 남은 원본 에셋", category="imagery", kind="fingerprint",
      weight=3, drivers=["P4"], applies=["web", "game"], threshold=1, saturation=4,
      why="이미지 안에 DALL·E/Midjourney/Stable Diffusion 프롬프트, C2PA 'AI 생성' 표기가 그대로 남아 있다는 것은 생성 결과를 편집 없이 바로 넣었다는 뜻이다. "
          "AI 이미지 사용 자체가 슬롭은 아니지만, 무보정 원본은 언캐니 아티팩트(손, 글자, 질감)를 함께 가져온다.",
      fix={"summary": "AI 이미지는 '재료'로만 쓰고 반드시 사람의 편집(크롭·리터치·색 보정·합성·스타일 통일)을 거친다. 출처 표기 정책도 정한다.",
           "steps": ["리포트의 이미지를 열어 손/글자/로고/대칭 오류를 확대 검수한다.",
                     "브랜드 팔레트로 색 보정하고, 같은 프롬프트 스타일 가이드로 전체 에셋을 통일한다.",
                     "가능한 핵심 이미지(hero, 제품, 캐릭터)는 실제 사진·직접 그린 일러스트로 교체한다.",
                     "생성 이미지를 쓴다면 C2PA/IPTC 표기를 유지하되 alt와 캡션에 의도를 적는다 (투명성)."],
           "example": "exiftool -a -G1 assets/hero.png   # 메타데이터 확인\n(리터치 후) exiftool -overwrite_original -Parameters= assets/hero.png",
           "effort": "M",
           "directive": "생성 이미지를 무보정으로 쓰지 말 것. 모든 이미지는 하나의 스타일 가이드(팔레트·조명·선 굵기)로 통일하고 아티팩트를 검수할 것."})
def img_meta(ctx):
    hits, ev = 0.0, []
    for im in ctx.images:
        strong = [g for g, s in im.generators if s]
        weak = [g for g, s in im.generators if not s]
        if strong:
            hits += 1
        elif weak:
            hits += 0.5
        else:
            continue
        if len(ev) < 6:
            ev.append(Evidence(im.path, 0, "생성기 흔적: " + ", ".join(strong + weak) +
                               (f" · {im.width}×{im.height}" if im.width else "")))
    if hits:
        return Result(hits, ev, f"생성기 메타데이터가 있는 이미지 {hits:g}개")


@rule(id="IMG-02", title="AI 생성기 기본 해상도 이미지 다수 (1024², 1792×1024…)", category="imagery", kind="fingerprint",
      weight=1, drivers=["P4"], applies=["web", "game"], threshold=2, saturation=6,
      why="1024×1024, 1792×1024, 1536×1024 등은 이미지 생성기의 기본 출력 크기다. 크롭·리사이즈 없이 그대로 쓰였다는 약한 신호다 (단독으로는 판단하지 않음).",
      fix={"summary": "레이아웃 슬롯에 맞게 크롭하고 반응형 크기(srcset)로 다시 내보낸다.",
           "steps": ["이미지가 들어갈 실제 비율(예: 4:5, 21:9)을 정하고 의도적으로 크롭한다.",
                     "AVIF/WebP + srcset으로 여러 크기를 만든다."],
           "example": "<img src=\"hero-1600.avif\" srcset=\"hero-800.avif 800w, hero-1600.avif 1600w\" sizes=\"100vw\" alt=\"…\">",
           "effort": "S",
           "directive": "이미지는 레이아웃 비율에 맞춰 의도적으로 크롭하고 srcset으로 제공."})
def img_sizes(ctx):
    pot = {(512, 512), (1024, 1024), (2048, 2048)}
    sized = [im for im in ctx.images if im.ai_size and not (ctx.kind == "game" and (im.width, im.height) in pot)]
    if len(sized) >= 2:
        return Result(len(sized), [Evidence(im.path, 0, f"{im.width}×{im.height}") for im in sized[:6]],
                      f"생성기 기본 해상도 이미지 {len(sized)}개")


@rule(id="IMG-03", title="AI 생성기 파일명 그대로 사용", category="imagery", kind="fingerprint",
      weight=3, drivers=["P4", "P3"], applies=["web", "game"], threshold=1, saturation=4,
      why="'DALL·E 2025-…png', 'ChatGPT Image …', 'Gemini_Generated_Image_…', 'user_prompt_text_uuid.png' 같은 파일명은 생성 결과를 다운로드해 그대로 넣었다는 증거다.",
      fix={"summary": "에셋 파일명을 역할 기반으로 바꾸고 (hero-desk-morning.avif) 에셋 파이프라인(리사이즈·압축)을 거친다.",
           "steps": ["파일명을 '용도-내용-변형' 규칙으로 바꾼다.", "참조 경로를 일괄 수정한다."],
           "example": "assets/DALL·E 2025-03-02 10.11.png → assets/hero-cafe-counter@2x.avif",
           "effort": "S",
           "directive": "에셋 파일명은 역할 기반 규칙으로. 생성기 기본 파일명 금지."})
def img_names(ctx):
    names = [im.path for im in ctx.images if im.ai_filename]
    refs, ev = 0, []
    for f in ctx.by_role("markup", "style", "script"):
        for m in re.finditer(r"[\"'`(]([^\"'`()\n]{1,200}\.(?:png|jpe?g|webp|gif|avif))[\"'`)?#]", f.text, re.I):
            base = m.group(1).replace("\\", "/").rsplit("/", 1)[-1]
            if AI_FILENAME.search(base):
                refs += 1
                if len(ev) < 4:
                    ev.append(Evidence(f.path, f.line_of(m.start()), base[:90]))
    total = len(names) + (refs if not names else 0)
    if total:
        ev2 = [Evidence(p, 0, "파일명: " + p.rsplit("/", 1)[-1][:90]) for p in names[:4]]
        return Result(total, ev2 + ev, f"생성기 파일명 {total}개")


@rule(id="IMG-04", title="플레이스홀더 이미지 서비스 (picsum, pravatar, unsplash 랜덤…)", category="imagery", kind="quality",
      weight=3, drivers=["P3", "P2"], applies=["web", "game"], threshold=1, saturation=5,
      why="picsum.photos, i.pravatar.cc, placehold.co, source.unsplash.com 같은 임시 이미지는 '내용 없이 자리만 채웠다'는 뜻이다. 특히 pravatar 얼굴 + 가짜 후기 조합은 가장 강한 슬롭 신호다.",
      fix={"summary": "모든 임시 이미지를 실제 에셋으로 교체하고, 없으면 이미지 슬롯 자체를 없앤다.",
           "steps": ["리포트 위치의 URL을 실제 에셋 경로로 바꾼다.", "인물 아바타는 실제 사용자 동의를 받은 사진만 쓰거나 이니셜 배지로 대체한다.",
                     "스톡 사진을 쓴다면 의도에 맞게 골라 크롭·색보정하고 로컬에 저장한다."],
           "example": "<img src=\"https://i.pravatar.cc/150?img=3\"> → <span class=\"avatar\" aria-hidden=\"true\">JK</span>",
           "effort": "S",
           "directive": "picsum/pravatar/placehold/unsplash 랜덤 등 플레이스홀더 이미지 금지."})
def img_placeholder(ctx):
    c, ev = ctx.grep(r"picsum\.photos|placehold\.(?:co|it)|via\.placeholder\.com|placekitten|placeimg|dummyimage\.com|"
                     r"i\.pravatar\.cc|randomuser\.me/api/portraits|ui-avatars\.com|source\.unsplash\.com|loremflickr|fakeimg\.pl|"
                     r"images\.unsplash\.com/photo-[\w-]+\?[^\"')\s]*(?:w=|ixlib)", "markup", "style", "script")
    if c:
        return Result(c, ev, f"플레이스홀더 이미지 {c}곳")


@rule(id="IMG-05", title="실제 이미지가 하나도 없음 (아이콘·그라디언트뿐)", category="imagery", kind="quality",
      weight=2, drivers=["P2"], applies=["web"], threshold=1, saturation=1,
      why="여러 섹션이 있는데 제품 화면·사진·일러스트가 전혀 없고 아이콘과 그라디언트만 있다면, 보여줄 '실체'가 없는 페이지로 읽힌다.",
      fix={"summary": "제품이 실제로 동작하는 장면 1~3개를 hero와 핵심 섹션에 넣는다.",
           "steps": ["실제 화면을 캡처해 브라우저 프레임 없이 크롭한다.", "사용 맥락 사진 또는 직접 만든 일러스트를 추가한다."],
           "example": "<img src=\"/shots/budget-week.avif\" alt=\"주간 예산이 초과된 카테고리가 빨갛게 표시된 실제 화면\">",
           "effort": "M",
           "directive": "제품/게임의 실제 화면 또는 의도된 일러스트를 반드시 포함."})
def img_none(ctx):
    if len(ctx.headings) < 5:
        return None
    real = [s for _f, _l, s, _a in ctx.imgs if s and not re.search(r"\.svg$|icon|logo|avatar|pravatar|picsum|placehold", s, re.I)]
    bg = ctx.has(r"background(?:-image)?\s*:[^;]*url\((?![^)]*(?:svg|noise|grain))", "style", "markup")
    if not real and not bg and not ctx.has(r"<video\b|<picture\b|<canvas\b", "markup"):
        return Result(1, [], f"제목 {len(ctx.headings)}개 섹션에 실제 이미지 0개")
