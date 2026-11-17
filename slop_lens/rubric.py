"""Human-perception rubric for the *visual* pass.

Static analysis can't see a screenshot. Multimodal agents (Claude, Codex, Gemini…) can.
The agent takes screenshots (desktop + 390px mobile, and gameplay for games), answers
each item with yes / partial / no / na, and submits the answers back to SlopLens.
Every item is phrased so that **"yes" = slop present**.
"""
from .model import Rule


def _r(id, title, category, kind, weight, drivers, applies, question, look_for, why, fix):
    return Rule(id=id, title=title, category=category, kind=kind, weight=weight, drivers=drivers,
                applies=applies, why=why, fix=fix, source="visual",
                threshold=0, saturation=1) , question, look_for


_ITEMS = [
    _r("VR-01", "브랜드 교체 테스트 실패", "visual", "fingerprint", 5, ["P1", "P2"], ["web"],
       "로고와 제품명을 다른 회사 것으로 바꿔도 어색함 없이 성립하는가?",
       "색·서체·이미지·카피 중 이 브랜드만의 것이 하나라도 있는지. 없으면 yes.",
       "어떤 제품에든 붙일 수 있는 디자인은 사람에게 '템플릿'으로 인식된다.",
       {"summary": "이 브랜드만의 시그니처 요소 1개(고유 일러스트, 특정 사진 톤, 독특한 레이아웃 장치, 목소리)를 정해 페이지 전체에 반복한다.",
        "steps": ["브랜드를 형용사 3개로 정의한다.", "시그니처 요소 1개를 정해 hero·섹션 구분·버튼에 일관되게 쓴다."],
        "effort": "L", "directive": "이 브랜드만의 시그니처 시각 요소 1개를 정의하고 전체에 일관되게 반복할 것."}),
    _r("VR-02", "시선 초점 부재", "layout", "quality", 3, ["P2"], ["web", "game"],
       "첫 화면에서 시선을 끄는 '주인공' 요소 없이 모든 요소가 비슷한 무게인가?",
       "3초 동안 본 뒤 기억나는 것이 하나도 없다면 yes.",
       "위계가 없는 화면은 결정을 내리지 않은 화면이다.",
       {"summary": "첫 화면 주인공을 1개 정하고 크기·대비·여백을 그 요소에 몰아준다.", "steps": ["주인공 외 요소의 크기와 대비를 낮춘다."],
        "effort": "M", "directive": "첫 화면에 명확한 주인공 요소 1개, 나머지는 의도적으로 낮은 위계."}),
    _r("VR-03", "AI 이미지 아티팩트", "imagery", "fingerprint", 5, ["P4"], ["web", "game"],
       "이미지에 생성 모델 특유의 흔적이 보이는가?",
       "뭉개진 손가락·글자·로고, 의미 없는 기호, 플라스틱 피부, 과한 보케, 완벽 대칭, 오렌지-틸 시네마틱 톤, 모든 것이 빛나는 조명.",
       "언캐니 아티팩트는 1초 만에 '생성 이미지'로 판정되고 전체 신뢰를 떨어뜨린다.",
       {"summary": "아티팩트가 있는 이미지는 교체하거나 리터치하고, 글자가 들어간 이미지는 실제 텍스트로 다시 얹는다.",
        "steps": ["이미지를 200% 확대해 손·글자·경계를 검수한다.", "이미지 속 가짜 텍스트는 지우고 HTML 텍스트로 대체한다."],
        "effort": "M", "directive": "생성 이미지는 손·글자·경계 아티팩트를 검수·리터치하고, 이미지 속 텍스트는 실제 텍스트로."}),
    _r("VR-04", "에셋 스타일 혼재", "imagery", "quality", 4, ["P5"], ["web", "game"],
       "3D 렌더·플랫 일러스트·사진·아이콘(또는 스프라이트) 스타일이 섞여 있는가?",
       "선 굵기, 조명 방향, 해상도, 채도, 원근이 이미지마다 다르면 yes.",
       "한 사람이 결정했다면 스타일이 하나다. 섞여 있으면 '여러 번 뽑아서 붙인' 결과로 보인다.",
       {"summary": "스타일 가이드 1장(팔레트·조명·선·해상도)을 만들고 기준에 맞지 않는 에셋을 교체한다.", "steps": ["가장 좋은 에셋 1개를 기준으로 정한다."],
        "effort": "L", "directive": "모든 에셋은 하나의 스타일 가이드(팔레트·조명·선 굵기·해상도)를 따를 것."}),
    _r("VR-05", "보랏빛 다크모드 + 글로우 무드", "visual", "fingerprint", 3, ["P1"], ["web", "game"],
       "어두운 배경 + 보라/시안 발광 + 그라디언트의 'AI 테크' 무드인가?", "",
       "가장 흔한 AI 미감의 평균값.",
       {"summary": "브랜드에 맞는 다른 무드(밝은 종이 톤, 저채도 다크, 고대비 흑백 등)를 의도적으로 선택한다.", "steps": [],
        "effort": "M", "directive": "보랏빛 다크 + 네온 글로우 무드 금지."}),
    _r("VR-06", "섹션 리듬 단조로움", "layout", "fingerprint", 3, ["P1"], ["web"],
       "스크롤하면 '제목-부제-카드 3개'가 섹션마다 반복되는가?", "섹션 썸네일을 나란히 놓았을 때 구분이 안 되면 yes.",
       "같은 패턴 반복은 자동 생성의 대표 신호.",
       {"summary": "섹션마다 다른 형태(전폭 이미지, 표, 인용, 타임라인, 비대칭 2열)를 쓴다.", "steps": [],
        "effort": "M", "directive": "섹션마다 레이아웃 형태를 다르게 할 것."}),
    _r("VR-07", "정보 없는 장식 영역", "visual", "fingerprint", 3, ["P2"], ["web"],
       "블롭·그라디언트 메쉬·추상 3D 오브·떠다니는 도형처럼 정보 없이 공간만 채우는 비주얼이 큰 면적을 차지하는가?", "",
       "보여줄 실체가 없을 때 장식이 늘어난다.",
       {"summary": "장식을 제품의 실제 장면·사례·데이터 시각화로 교체한다.", "steps": [],
        "effort": "M", "directive": "정보 없는 장식 비주얼 대신 실제 제품 장면을 보여줄 것."}),
    _r("VR-08", "실체 부재", "imagery", "quality", 4, ["P2", "P3"], ["web"],
       "제품의 실제 모습(실제 화면, 실물, 실제 사례, 만든 사람)이 하나도 보이지 않는가?", "",
       "실체가 보이지 않으면 '존재하지 않는 제품'처럼 느껴진다.",
       {"summary": "실제 화면/실물/사례/팀 사진 중 최소 1개를 첫 화면에 넣는다.", "steps": [],
        "effort": "M", "directive": "실제 제품 화면 또는 실물을 첫 화면에 보여줄 것."}),
    _r("VR-09", "타이포 위계 부재", "visual", "fingerprint", 2, ["P1"], ["web", "game"],
       "글자 크기만 다르고 서체·굵기·자간 대비가 없어 모든 텍스트가 같은 목소리인가?", "",
       "타이포는 브랜드 목소리. 대비가 없으면 기본값으로 읽힌다.",
       {"summary": "디스플레이/본문 서체 페어링과 굵기·자간 대비를 만든다.", "steps": [],
        "effort": "S", "directive": "서체 페어링과 굵기·자간 대비로 타이포 위계를 만들 것."}),
    _r("VR-10", "정렬·간격 미세 오류", "visual", "quality", 3, ["P3", "P5"], ["web", "game"],
       "아이콘-텍스트 기준선 어긋남, 카드 높이 들쭉날쭉, 버튼 패딩 불균형, 가장자리 여백 불일치가 보이는가?", "",
       "사람은 미세한 어긋남을 '덜 다듬어짐'으로 즉시 느낀다.",
       {"summary": "4/8px 간격 체계와 그리드 기준선을 정하고 어긋난 곳을 맞춘다.", "steps": [],
        "effort": "S", "directive": "4/8px 간격 체계와 기준선 정렬을 엄격히 지킬 것."}),
    _r("VR-11", "눌러도 아무 일 없음", "ux", "quality", 4, ["P3"], ["web", "game"],
       "주요 버튼·링크·메뉴를 실제로 눌렀을 때 동작하지 않거나 같은 페이지 맨 위로만 가는가?", "최소 5개 클릭 테스트.",
       "껍데기 완성도의 결정적 체감.",
       {"summary": "동작하지 않는 UI를 연결하거나 제거한다.", "steps": [],
        "effort": "S", "directive": "모든 노출된 UI는 실제로 동작해야 함."}),
    _r("VR-12", "모바일 폭에서 깨짐", "ux", "quality", 3, ["P3"], ["web", "game"],
       "390px 폭에서 가로 스크롤, 겹침, 잘림, 너무 작은 글자가 있는가?", "",
       "대부분의 첫 방문은 모바일이다.",
       {"summary": "모바일 우선으로 레이아웃을 재검수한다.", "steps": [],
        "effort": "M", "directive": "390px 폭에서 깨지지 않게."}),
    _r("VR-13", "가짜 로고 월·가짜 증거", "copy", "quality", 4, ["P3", "P4"], ["web"],
       "'Trusted by' 로고가 실존하지 않거나 흐릿한 가짜 로고, 출처 없는 후기·별점이 보이는가?", "",
       "가짜 증거는 신뢰를 정면으로 깎는다.",
       {"summary": "검증 가능한 증거만 남긴다.", "steps": [],
        "effort": "S", "directive": "가짜 로고·후기·별점 금지."}),
    _r("VR-14", "아이콘 남용", "visual", "fingerprint", 2, ["P1"], ["web"],
       "거의 모든 항목·제목 앞에 의미 없는 아이콘(또는 이모지)이 붙어 있는가?", "",
       "아이콘이 정보가 아니라 장식이 됨.",
       {"summary": "아이콘은 인식 속도를 높이는 곳에만 남긴다.", "steps": [],
        "effort": "S", "directive": "의미 없는 장식 아이콘 금지."}),
    _r("VR-15", "관점·목소리 부재", "copy", "fingerprint", 3, ["P2"], ["web", "game"],
       "유머·의견·구체적 경험 없이 중립적인 홍보 톤만 있는가?", "읽고 나서 '누가 썼는지' 상상이 안 되면 yes.",
       "사람이 만든 결과물에는 결정한 사람의 관점이 묻어난다.",
       {"summary": "만든 사람의 관점(왜 만들었나, 무엇을 의도적으로 안 했나)을 카피에 넣는다.", "steps": [],
        "effort": "M", "directive": "만든 사람의 관점과 구체적 경험이 드러나는 목소리로 카피를 쓸 것."}),
    # ---------- game-specific ----------
    _r("VG-01", "목표·조작 불명확", "game", "quality", 3, ["P3"], ["game"],
       "첫 10초 안에 무엇을 해야 하는지, 어떻게 조작하는지 알 수 없는가?", "",
       "온보딩 없는 게임은 테크 데모로 느껴진다.",
       {"summary": "첫 10초를 튜토리얼 없이 '해보며 배우는' 구간으로 설계한다.", "steps": [],
        "effort": "M", "directive": "첫 10초에 목표와 조작을 자연스럽게 학습시키는 구간을 설계."}),
    _r("VG-02", "타격감·피드백 부재", "game", "quality", 5, ["P2"], ["game"],
       "맞히거나 맞았을 때, 아이템을 먹었을 때 시각·청각 피드백이 거의 없는가?", "",
       "게임필이 없으면 '숫자만 바뀌는' 게임.",
       {"summary": "히트스톱·플래시·파티클·카메라·사운드를 핵심 행동에 쌓는다.", "steps": [],
        "effort": "M", "directive": "핵심 행동마다 다층 피드백(히트스톱/플래시/파티클/카메라/사운드)."}),
    _r("VG-03", "아트 일관성 붕괴", "game", "quality", 4, ["P5"], ["game"],
       "스프라이트마다 해상도·외곽선·팔레트·원근이 다른가?", "픽셀아트인데 픽셀 크기가 제각각이면 yes.",
       "여러 번 생성해 붙인 에셋의 대표 증상.",
       {"summary": "아트 바이블 1장을 정하고 기준 밖 에셋을 교체·리드로우한다.", "steps": [],
        "effort": "L", "directive": "모든 스프라이트는 같은 해상도·외곽선·팔레트."}),
    _r("VG-04", "생성 스프라이트 아티팩트", "game", "fingerprint", 4, ["P4"], ["game"],
       "스프라이트에 뭉개진 디테일, 반투명 노이즈 가장자리, 배경 잔여물, 픽셀 그리드 어긋남이 있는가?", "",
       "AI 스프라이트를 정리 없이 쓴 흔적.",
       {"summary": "팔레트 양자화·픽셀 그리드 정렬·가장자리 정리를 수작업으로 한다.", "steps": [],
        "effort": "M", "directive": "생성 스프라이트는 팔레트 양자화·그리드 정렬·가장자리 정리 후 사용."}),
    _r("VG-05", "반복 플레이 동기 부재", "game", "quality", 4, ["P2"], ["game"],
       "한 판 끝나면 다시 할 이유(진행·해금·기록 갱신·변주)가 없는가?", "",
       "코어 루프만 있고 메타 루프가 없다.",
       {"summary": "최고 기록, 해금, 일일 시드, 업그레이드 중 하나를 추가한다.", "steps": [],
        "effort": "M", "directive": "최고 기록·해금·변주 등 재도전 동기를 설계."}),
    _r("VG-06", "장르 평균값 복제", "game", "fingerprint", 4, ["P1"], ["game"],
       "흔한 장르(플래피/브레이크아웃/뱀서/러너)를 비틀기 없이 그대로 구현했는가?", "고유한 메카닉 1개를 한 문장으로 말할 수 없으면 yes.",
       "LLM은 장르의 평균을 만든다. 사람의 게임은 하나의 비틀기에서 출발한다.",
       {"summary": "핵심 메카닉에 '하지만 ~'을 하나 추가한다 (예: 점프할 때마다 중력이 반전된다).", "steps": [],
        "effort": "L", "directive": "장르 평균 복제 금지. 한 문장으로 설명 가능한 고유 메카닉 비틀기 1개를 중심으로."}),
    _r("VG-07", "기본값 HUD", "game", "fingerprint", 2, ["P1"], ["game"],
       "좌상단 'Score: 0' 기본 폰트 텍스트 외에 HUD 디자인이 없는가?", "",
       "정보 디자인이 없는 화면.",
       {"summary": "HUD를 아이콘·게이지·숫자 애니메이션으로 디자인한다.", "steps": [],
        "effort": "S", "directive": "기본 폰트 텍스트 HUD 금지."}),
]

RUBRIC = {r.id: (r, q, lf) for r, q, lf in _ITEMS}


def rubric_for(kind: str):
    return [(r, q, lf) for r, q, lf in _ITEMS if kind in r.applies]


def _shot_list(shots):
    if not shots:
        return []
    out = []
    for k in ("desktop", "desktopFull", "mobile"):
        if shots.get(k):
            out.append(f"   - {k}: `{shots[k]}`")
    for p in shots.get("game") or []:
        out.append(f"   - gameplay: `{p}`")
    return out


def rubric_markdown(kind: str, scan_id: str = "", shots=None) -> str:
    items = rubric_for(kind)
    shot_lines = _shot_list(shots)
    if shot_lines:
        step1 = "1. 렌더 프로브가 찍어 둔 스크린샷을 이미지로 열어 보세요:\n" + "\n".join(shot_lines)
    else:
        step1 = ("1. 스크린샷 확보: 데스크톱(1440px) 첫 화면 + 전체 스크롤, 모바일(390px) 첫 화면"
                 + (", 실제 플레이 30초(피격·명중·게임오버 포함)" if kind == "game" else ", 주요 버튼 5개 클릭 결과"))
    lines = [f"# SlopLens 시각 검토 루브릭 ({'게임' if kind == 'game' else '웹'})", "",
             "정적 분석은 화면을 볼 수 없습니다. 아래 절차로 **직접 보고** 판정해 주세요.", "",
             "## 절차",
             step1,
             "2. 각 항목에 `yes`(슬롭 신호 있음) / `partial` / `no` / `na` 로 답하고 근거를 한 줄로 적습니다.",
             "3. `slop_submit_visual_review` 도구(또는 CLI `--visual answers.json`)로 제출하면 정적 점수와 합쳐 최종 판정합니다.", "",
             "## 항목 (yes = 슬롭)", ""]
    for r, q, lf in items:
        lines.append(f"- **{r.id} {r.title}** (가중치 {r.weight}) — {q}" + (f"  \n  살펴볼 것: {lf}" if lf else ""))
    tmpl = ",\n".join(f'    {{"id": "{r.id}", "answer": "no", "note": ""}}' for r, _, _ in items)
    lines += ["", "## 제출 형식", "```json", "{", f'  "scan_id": "{scan_id or "<slop_scan 결과의 scan_id>"}",', '  "answers": [', tmpl, "  ]", "}", "```"]
    return "\n".join(lines)
