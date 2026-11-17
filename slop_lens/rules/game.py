"""Game design / game-feel signals. Works for HTML5 canvas, Phaser/PIXI/Three, and
keyword-level checks for Unity (C#), Godot (GDScript), LÖVE (Lua)."""
import re

from ..model import Evidence, Result, rule
from ._genre import compiled_build, realtime

G = ["game"]


def _code(ctx):
    return ctx.joined("script", "engine", "markup")


@rule(id="GAM-01", title="setInterval 게임 루프", category="gametech", kind="quality",
      weight=3, drivers=["P3"], applies=G, threshold=1, saturation=1,
      why="setInterval(update, 16) 루프는 화면 주사율과 맞지 않아 끊김(jank)을 만들고 탭 전환 시 폭주한다. 'AI가 최소 동작만 만든 게임'의 기술적 지문이다.",
      fix={"summary": "requestAnimationFrame + 고정 timestep(또는 delta time) 루프로 교체한다.",
           "steps": ["setInterval 루프를 rAF 루프로 바꾼다.", "update(dt)와 render()를 분리한다."],
           "example": "let last=performance.now(),acc=0;const STEP=1/60;\nfunction frame(t){acc+=Math.min(.25,(t-last)/1000);last=t;\n while(acc>=STEP){update(STEP);acc-=STEP}render();requestAnimationFrame(frame)}\nrequestAnimationFrame(frame);",
           "effort": "S",
           "directive": "게임 루프는 requestAnimationFrame + 고정 timestep(delta time)으로."})
def gam_interval(ctx):
    if not realtime(ctx):
        return None  # idle / turn-based games tick on timers by design
    c, ev = ctx.grep(r"setInterval\s*\(\s*(?:gameLoop|update|draw|loop|tick|render|game|step|main)\b|"
                     r"setInterval\s*\([\s\S]{0,200}?(?:ctx\.|clearRect|draw)[\s\S]{0,200}?,\s*(?:1000\s*/\s*\d+|1[0-9]|16|17|20|30|33)\s*\)",
                     "script", "markup")
    if c:
        return Result(c, ev, "setInterval 기반 루프")


@rule(id="GAM-02", title="프레임 독립 이동 없음 (delta time 미사용)", category="gametech", kind="quality",
      weight=3, drivers=["P3"], applies=G, threshold=1, saturation=1,
      why="프레임마다 x += 5 처럼 움직이면 120Hz 모니터에서는 2배 빨라지고 저사양에서는 느려진다. 플레이 감각이 기기마다 달라진다.",
      fix={"summary": "모든 이동·타이머에 dt(초)를 곱한다. Unity는 Time.deltaTime, Godot은 delta를 사용한다.",
           "steps": ["속도 단위를 '픽셀/초'로 재정의한다.", "update(dt)에서 pos += vel * dt 로 바꾼다."],
           "example": "player.x += player.speed * dt; // speed = 240 px/s",
           "effort": "S",
           "directive": "이동/타이머는 delta time 기반(px/초)으로."})
def gam_dt(ctx):
    code = _code(ctx)
    rx_dt = r"\b(?:dt|delta|deltaTime|delta_time|elapsed|lastTime|last_time|timestamp|performance\.now|Time\.deltaTime|frameTime|now\s*-\s*last)\b"
    if re.search(r"requestAnimationFrame", code) and not re.search(rx_dt, code):
        return Result(1, [], "rAF 루프에 delta time 없음")
    clock = re.compile(r"[dD]eltaTime|dspTime|Time\.time\b|timeSinceLevelLoad|unscaledTime|realtimeSinceStartup|getTimelinePosition|"
                       r"Stopwatch|songPosition|SongTime|AudioSettings|\bdelta\b")
    bad = []
    for f in ctx.by_role("engine"):
        if f.ext != ".cs":
            continue
        m = re.search(r"void\s+(?:Update|LateUpdate)\s*\(", f.text)
        if m and re.search(r"transform\.(?:position\s*[+\-]=|Translate\s*\()", f.text) and not clock.search(f.text):
            bad.append(Evidence(f.path, f.line_of(m.start()), "Update()에서 이동하지만 시간 기준(deltaTime 등) 없음"))
    if bad:
        return Result(1, bad[:5], f"프레임 의존 이동 의심 파일 {len(bad)}개", strength=min(1.0, 0.4 + 0.15 * len(bad)))


@rule(id="GAM-03", title="프로그래머 아트 (사각형·원만으로 렌더링)", category="game", kind="quality",
      weight=3, drivers=["P2", "P3"], applies=G, threshold=1, saturation=1,
      why="플레이어·적·아이템이 모두 fillRect/arc 단색 도형이면 '프로토타입을 그대로 출시한' 느낌이 된다. 장르를 막론하고 시각적 정체성이 없다.",
      fix={"summary": "하나의 아트 방향(팔레트 4~8색, 해상도, 선 규칙)을 정하고 핵심 오브젝트부터 스프라이트로 교체한다.",
           "steps": ["아트 방향을 1문장으로 정한다 (예: '16색 픽셀아트, 2px 외곽선, 따뜻한 석양 팔레트').",
                     "플레이어 → 적 → 투사체 → 배경 순으로 교체한다 (가장 많이 보는 것부터).",
                     "도형을 유지한다면 '의도된 미니멀리즘'으로: 제한 팔레트, 두께 있는 외곽선, 모양 언어(삼각형=위험) 정의."],
           "example": "const img=new Image();img.src='sprites/player.png';\nctx.imageSmoothingEnabled=false;ctx.drawImage(img,frame*16,0,16,16,x,y,32,32);",
           "effort": "L",
           "directive": "단색 사각형/원 프로그래머 아트 금지. 하나의 아트 방향(제한 팔레트·해상도·외곽선 규칙)으로 스프라이트를 통일."})
def gam_primitives(ctx):
    code = _code(ctx)
    prim = len(re.findall(r"\.(?:fillRect|strokeRect|arc|ellipse)\s*\(|\.add\.(?:rectangle|circle)\s*\(|\.beginFill\(", code))
    img = len(re.findall(r"drawImage\s*\(|new\s+Image\s*\(|load\.(?:image|spritesheet|atlas)|Texture|Sprite\.from|loadImage\(|SpriteRenderer|Sprite2D|AnimatedSprite", code))
    if prim >= 5 and img == 0:
        c, ev = ctx.grep(r"\.(?:fillRect|arc)\s*\(", "script", "markup", max_ev=3)
        return Result(1, ev, f"도형 그리기 {prim}회, 이미지/스프라이트 0")


JUICE = {
    "screen shake": r"shake|screenShake|camera\.shake|cameraShake",
    "particles": r"particle|emitter|ParticleSystem|GPUParticles|CPUParticles",
    "easing/lerp": r"\blerp\b|Mathf\.Lerp|easeOut|easeIn|easing|tween|Tween|smoothstep",
    "hit flash": r"flash|hitFlash|tint|blink|invuln",
    "hit stop": r"hitstop|hit_stop|hitStop|freezeFrame|timeScale",
    "squash/stretch": r"squash|stretch|scaleY\s*=|scale\.y\s*=",
    "knockback/recoil": r"knockback|recoil|impulse",
    "trail/afterimage": r"\btrail|afterimage|ghosting",
}


@rule(id="GAM-04", title="게임필(Juice) 부재 — 타격감·피드백 없음", category="game", kind="quality",
      weight=4, drivers=["P2"], applies=G, threshold=1, saturation=1,
      why="맞히거나 맞았을 때 화면 흔들림·파티클·히트스톱·플래시·이징이 전혀 없으면 조작이 '숫자가 바뀌는 것'으로만 느껴진다. "
          "사람이 'AI가 만든 게임 같다'고 말하는 가장 큰 이유가 이 빈 손맛이다.",
      fix={"summary": "핵심 동사(점프·공격·수집) 1개에 피드백 레이어를 5겹 쌓는다: 예비동작 → 이펙트 → 사운드 → 카메라 → 여운.",
           "steps": ["게임의 핵심 행동 1개를 고른다.", "명중 시: 2~4프레임 히트스톱 + 흰색 플래시 + 파티클 8~12개 + 짧은 카메라 흔들림.",
                     "이동은 lerp/easing으로 가감속을 준다.", "같은 사운드라도 피치를 ±5% 랜덤화한다.",
                     "효과마다 on/off 토글을 두고 비교 플레이해 강도를 조정한다."],
           "example": "function onHit(e){hitStop=0.05;shake=6;e.flash=0.08;spawnParticles(e.x,e.y,10);sfx.hit.play({rate:0.95+Math.random()*0.1})}\n"
                      "// render: ctx.translate((Math.random()-.5)*shake,(Math.random()-.5)*shake); shake*=0.9;",
           "effort": "M",
           "directive": "핵심 행동마다 히트스톱·플래시·파티클·카메라 흔들림·사운드 피드백을 넣을 것. 이동은 가감속(easing) 적용."})
def gam_juice(ctx):
    if not realtime(ctx):
        return None  # hit-stop / shake / particles are action-game expectations
    if compiled_build(ctx):
        return None  # compiled engine build: juice lives in wasm, not readable code — judge it from the screen
    code = _code(ctx)
    found = [k for k, p in JUICE.items() if re.search(p, code)]
    if len(found) <= 1:
        return Result(1, [], "발견된 게임필 기법: " + (", ".join(found) if found else "없음"),
                      strength=1.0 if not found else 0.6)


@rule(id="GAM-05", title="사운드 없음", category="game", kind="quality",
      weight=3, drivers=["P2"], applies=G, threshold=1, saturation=1,
      why="게임 체감의 절반은 소리다. 효과음·배경음이 전혀 없으면 미완성 데모로 인식된다.",
      fix={"summary": "핵심 행동 3~5개에 효과음, 루프 BGM 1개, 음소거 토글을 추가한다.",
           "steps": ["jsfxr/ChipTone 등으로 효과음을 만든다 (점프, 명중, 획득, 피격, 게임오버).",
                     "첫 입력 이후 AudioContext를 resume 한다 (자동재생 정책).", "볼륨/음소거 설정을 제공한다."],
           "example": "const sfx={jump:new Audio('sfx/jump.wav')};\nfunction play(s){const a=s.cloneNode();a.volume=settings.sfx;a.play()}",
           "effort": "S",
           "directive": "핵심 행동 효과음 + BGM + 음소거 토글 필수."})
def gam_audio(ctx):
    if compiled_build(ctx):
        return None  # sound is measured at runtime (AUD-*) for compiled builds
    code = _code(ctx)
    if not re.search(r"new\s+Audio\s*\(|AudioContext|Howl\b|howler|\.sound\.|sound\.(?:add|play)|AudioSource|AudioStreamPlayer|playSound|\bsfx\b|\bbgm\b|"
                     r"\.(?:mp3|ogg|wav)\b|<audio\b|zzfx|Tone\.|webkitAudioContext|me\.audio|createjs\.Sound|SoundJS|jsfxr|sfxr|"
                     r"\baudio\.play\(", code, re.I):
        return Result(1, [], "오디오 코드/에셋 없음")


@rule(id="GAM-06", title="alert 게임오버 / 새로고침 재시작", category="gametech", kind="quality",
      weight=4, drivers=["P3"], applies=G, threshold=1, saturation=2,
      why="alert('Game Over! Score: 120') 후 location.reload()로 재시작하는 흐름은 AI가 만든 최소 게임의 전형이다. 루프의 마지막 경험이 브라우저 경고창이다.",
      fix={"summary": "게임 안에서 그려지는 게임오버 화면(점수, 최고기록, 재시작 키)과 상태 초기화 함수를 만든다.",
           "steps": ["reset() 함수로 상태를 초기화한다 (새로고침 금지).", "게임오버 화면에 이번 점수·최고 점수·다음 목표를 보여준다.",
                     "재시작은 같은 키로 즉시(0.3초 이내) 가능하게 한다."],
           "example": "function reset(){Object.assign(state,{score:0,hp:3,enemies:[],mode:'play'})}\nif(state.mode==='over'&&keys.Space)reset();",
           "effort": "S",
           "directive": "alert 게임오버·location.reload 재시작 금지. 게임 내 게임오버 화면과 즉시 재시작."})
def gam_alert(ctx):
    c, ev = ctx.grep(r"alert\s*\([^)]{0,80}(?:game ?over|you (?:win|lose|died)|score|게임 ?오버|점수|승리|패배)|(?:window\.)?location\.reload\s*\(", "script", "markup", skip_comments=True)
    if c:
        return Result(c, ev, f"alert/reload 흐름 {c}곳")


@rule(id="GAM-07", title="난이도 곡선 없음 (고정 스폰·속도)", category="game", kind="quality",
      weight=2, drivers=["P2"], applies=G, threshold=1, saturation=1,
      why="처음부터 끝까지 같은 속도·같은 스폰 간격이면 30초 안에 지루해진다. 사람이 설계한 게임은 긴장과 이완의 곡선이 있다.",
      fix={"summary": "시간/점수에 따른 난이도 곡선과 패턴(웨이브)을 데이터로 정의한다.",
           "steps": ["0~30초 학습, 30~90초 상승, 이후 변주 구간을 정한다.", "스폰 간격·적 속도·패턴을 테이블로 만들고 곡선으로 보간한다.",
                     "주기적으로 '쉬는 구간'을 넣는다."],
           "example": "const waves=[{t:0,interval:1.4,types:['walker']},{t:30,interval:1.0,types:['walker','dasher']},{t:75,interval:0.8,types:['dasher','splitter']}];",
           "effort": "M",
           "directive": "시간/점수 기반 난이도 곡선과 웨이브 테이블을 설계. 고정 스폰 금지."})
def gam_difficulty(ctx):
    if not realtime(ctx):
        return None  # puzzles / idle / narrative games progress by content, not spawn curves
    if compiled_build(ctx):
        return None
    code = _code(ctx)
    if not re.search(r"difficult|level\s*(?:\+\+|\+=)|\bwave|speed\s*(?:\*=|\+=)|spawn(?:Rate|Interval|Delay|Timer)\s*(?:\*=|-=|=\s*Math\.max)|"
                     r"increase|ramp|stage|progress|난이도|tier", code, re.I):
        return Result(1, [], "난이도/웨이브/레벨 진행 코드 없음")


@rule(id="GAM-08", title="게임 상태 흐름 없음 (타이틀·일시정지·메뉴)", category="game", kind="quality",
      weight=3, drivers=["P3"], applies=G, threshold=1, saturation=1,
      why="페이지를 열자마자 게임이 시작되고 일시정지도 메뉴도 없다. 시작-플레이-종료-재도전의 흐름이 없으면 '테크 데모'로 느껴진다.",
      fix={"summary": "상태 머신(title → play → pause → over)을 도입한다.",
           "steps": ["mode 변수와 상태별 update/render를 분리한다.", "Esc/P로 일시정지, 탭 비활성 시 자동 일시정지(visibilitychange)."],
           "example": "const S={title:{update:t=>{if(keys.Enter)go('play')}},play:{…},pause:{…},over:{…}};\ndocument.addEventListener('visibilitychange',()=>document.hidden&&go('pause'));",
           "effort": "M",
           "directive": "title/play/pause/over 상태 머신과 일시정지(Esc/P, 탭 비활성 시 자동) 필수."})
def gam_states(ctx):
    if not realtime(ctx):
        return None  # turn-based / idle games need no pause state
    if compiled_build(ctx):
        return None
    code = _code(ctx)
    has_pause = re.search(r"pause|paused", code, re.I)
    has_menu = re.search(r"menu|title ?screen|start ?screen|gameState|game_state|GameState|mode\s*===?\s*[\"']|state\s*===?\s*[\"'](?:menu|title|playing|paused|over|gameover)|"
                         r"scene\.(?:start|switch)|SceneManager|change_scene", code, re.I)
    missing = [n for n, ok in (("일시정지", has_pause), ("타이틀/메뉴 상태", has_menu)) if not ok]
    if missing:
        return Result(len(missing), [], "없음: " + ", ".join(missing), strength=0.6 + 0.2 * len(missing))


@rule(id="GAM-09", title="AI식 범용 게임 제목 (Neon Dash, Cosmic Defender…)", category="game", kind="fingerprint",
      weight=2, drivers=["P1"], applies=G, threshold=1, saturation=1,
      why="Neon/Cosmic/Galaxy/Quantum/Pixel + Dash/Defender/Quest/Rush 조합은 LLM이 게임 이름을 지을 때의 평균값이다. 제목부터 '어디서 본 게임'이 된다.",
      fix={"summary": "게임의 고유 메카닉이나 세계관의 구체 명사로 제목을 짓는다.",
           "steps": ["게임에서 플레이어가 가장 많이 하는 동사와 가장 특이한 대상을 적는다.", "그 둘을 조합하거나 은유로 바꾼다."],
           "example": "Neon Dash → '야간 택배: 마지막 한 집'",
           "effort": "S",
           "directive": "Neon/Cosmic/Galaxy/Pixel + Dash/Quest/Defender 류 범용 제목 금지."})
def gam_title(ctx):
    rx = re.compile(r"\b(?:neon|cosmic|galaxy|galactic|quantum|pixel|cyber|star|space|astro|nova|void|hyper|retro|turbo|mega|super|ultra|epic)\b"
                    r"[\s\-:]*\w*[\s\-:]*\b(?:dash|run(?:ner)?|blast(?:er)?|defender|quest|odyssey|rush|shooter|invaders|jumper|escape|adventure|"
                    r"chronicles|frenzy|mania|strike|wars?|survivor|attack|arena|clash)\b", re.I)
    cands = [(d.get("title") or "", d["file"], 1) for d in ctx.html_docs] + [(t, f, ln) for lvl, t, f, ln in ctx.headings if lvl == 1]
    cands += [(m.group(1), f.path, f.line_of(m.start())) for f in ctx.by_role("script") for m in re.finditer(r"fillText\(\s*[\"'`]([^\"'`]{3,40})", f.text)]
    hits = [(t, f, ln) for t, f, ln in cands if rx.search(t)]
    if hits:
        return Result(1, [Evidence(f, ln, t) for t, f, ln in hits[:3]], "제목: " + hits[0][0])


@rule(id="GAM-10", title="고정 캔버스 크기 (리사이즈·DPR 미대응)", category="gametech", kind="quality",
      weight=2, drivers=["P3"], applies=G, threshold=1, saturation=1,
      why="800×600 고정 캔버스는 고해상도 화면에서 흐릿하고 모바일에서 잘린다.",
      fix={"summary": "논리 해상도를 고정하고 화면에 맞춰 정수 배율로 스케일하며 devicePixelRatio를 반영한다.",
           "steps": ["논리 해상도(예: 320×180)를 정한다.", "resize 이벤트에서 배율을 계산하고 canvas.width에 DPR을 곱한다."],
           "example": "function fit(){const s=Math.floor(Math.min(innerWidth/W,innerHeight/H))||1;const d=devicePixelRatio||1;\ncv.style.width=W*s+'px';cv.style.height=H*s+'px';cv.width=W*s*d;cv.height=H*s*d;ctx.setTransform(s*d,0,0,s*d,0,0)}\naddEventListener('resize',fit);fit();",
           "effort": "S",
           "directive": "캔버스는 논리 해상도 + 화면 맞춤 스케일 + devicePixelRatio 대응."})
def gam_canvas(ctx):
    code = _code(ctx)
    fixed = re.search(r"<canvas[^>]*width\s*=\s*[\"']?(?:800|640|600|480|1024|960|1280)|\.width\s*=\s*(?:800|640|1024|960|1280)\b|width\s*:\s*(?:800|640|1024|960)\s*,\s*height", code)
    if fixed and not re.search(r"devicePixelRatio|addEventListener\(\s*[\"']resize|onresize|ResizeObserver|Scale\.(?:FIT|RESIZE|ENVELOP)|innerWidth", code):
        return Result(1, [], "고정 크기 캔버스, resize/DPR 처리 없음")


@rule(id="GAM-11", title="기본 폰트 HUD ('20px Arial' Score:)", category="game", kind="fingerprint",
      weight=2, drivers=["P1"], applies=G, threshold=1, saturation=4,
      why="ctx.font = '20px Arial'로 좌상단에 'Score: 0'을 찍는 HUD는 AI 캔버스 게임의 기본 화면이다. 정보 디자인이 전혀 없다.",
      fix={"summary": "게임 톤에 맞는 비트맵/픽셀 폰트를 쓰고 HUD를 아이콘·숫자 중심으로 재설계한다.",
           "steps": ["게임 아트 방향에 맞는 폰트를 로드한다 (예: 픽셀아트 → 비트맵 폰트).", "점수 변화에 펀치 스케일·카운트업 애니메이션을 준다.",
                     "HUD 요소를 화면 가장자리 안전 영역에 정렬한다."],
           "example": "await document.fonts.load('16px \"Press Start 2P\"');ctx.font='16px \"Press Start 2P\"';",
           "effort": "S",
           "directive": "Arial/sans-serif 기본 폰트 HUD 금지. 게임 아트 방향에 맞는 폰트와 HUD 디자인."})
def gam_font(ctx):
    c, ev = ctx.grep(r"\.font\s*=\s*[\"'`]\s*(?:bold\s+|italic\s+)?\d+px\s+(?:Arial|sans-serif|serif|Helvetica|monospace|Verdana|Courier|Times)|"
                     r"fontFamily\s*:\s*[\"'](?:Arial|sans-serif|Helvetica|Verdana|Courier)", "script", "markup")
    if c:
        return Result(c, ev, f"기본 폰트 HUD {c}곳")


@rule(id="GAM-12", title="이모지 스프라이트", category="game", kind="fingerprint",
      weight=3, drivers=["P1", "P2"], applies=G, threshold=1, saturation=4,
      why="🚀👾💎를 fillText로 그려 캐릭터·적으로 쓰는 것은 '그림 없이 빠르게' 만든 AI 게임의 상징이다. OS마다 모양이 달라 의도한 화면도 보장되지 않는다.",
      fix={"summary": "이모지를 스프라이트(직접 그리거나 일관된 에셋 팩)로 교체한다.",
           "steps": ["이모지를 사용하는 오브젝트 목록을 만들고 같은 아트 방향의 스프라이트로 바꾼다."],
           "example": "ctx.fillText('👾',x,y) → ctx.drawImage(sprites.invader,frame*16,0,16,16,x,y,32,32)",
           "effort": "M",
           "directive": "이모지를 캐릭터/오브젝트 그래픽으로 쓰지 말 것."})
def gam_emoji(ctx):
    c, ev = ctx.grep("(?:fillText\\(|text\\(|\\.text\\s*=|emoji\\s*:)\\s*[\"'`][\U0001F300-\U0001FAFF☀-➿]", "script", "markup", flags=0)
    if c:
        return Result(c, ev, f"이모지 스프라이트 {c}곳")


@rule(id="GAM-13", title="키보드 전용 입력 (터치·패드 미지원)", category="gametech", kind="quality",
      weight=1, drivers=["P3"], applies=G, threshold=1, saturation=1,
      why="웹 게임 링크는 대부분 폰에서 열린다. 키보드만 지원하면 첫 방문자 다수가 플레이조차 못 한다.",
      fix={"summary": "포인터(터치) 입력과 게임패드 입력을 추가하고 입력을 '행동'으로 추상화한다.",
           "steps": ["input.left/right/jump 같은 행동 맵을 만들고 키보드·터치·패드를 매핑한다.", "모바일에 가상 버튼 또는 탭/스와이프 조작을 제공한다."],
           "example": "addEventListener('pointerdown',e=>input.jump=true);addEventListener('pointerup',()=>input.jump=false);",
           "effort": "M",
           "directive": "키보드 + 터치(pointer) + 게임패드 입력을 행동 맵으로 추상화해 지원."})
def gam_input(ctx):
    code = _code(ctx)
    if re.search(r"keydown|keyup|keypress", code) and not re.search(r"touchstart|pointerdown|pointer|getGamepads|gamepad|mousedown|onclick|\.on\(\s*[\"']pointer", code, re.I):
        return Result(1, [], "keydown만 존재")


@rule(id="GAM-14", title="기본 원색 팔레트 ('red', '#00ff00', 'blue')", category="game", kind="fingerprint",
      weight=2, drivers=["P1", "P5"], applies=G, threshold=3, saturation=10,
      why="fillStyle='red'/'lime'/'#00ff00' 같은 CSS 기본 원색은 팔레트를 고민하지 않았다는 신호다. 화면이 거칠고 장난감처럼 보인다.",
      fix={"summary": "4~8색 제한 팔레트를 정의하고 모든 색을 팔레트에서만 가져온다.",
           "steps": ["Lospec 등에서 게임 톤에 맞는 팔레트를 고른다.", "PALETTE 상수를 만들고 모든 fillStyle을 치환한다."],
           "example": "const P={bg:'#1a1c2c',hero:'#ffcd75',enemy:'#b13e53',ui:'#f4f4f4'};ctx.fillStyle=P.enemy;",
           "effort": "S",
           "directive": "CSS 기본 원색(red, blue, lime, #00ff00) 금지. 4~8색 제한 팔레트 상수로만 색 지정."})
def gam_colors(ctx):
    c, ev = ctx.grep(r"(?:fillStyle|strokeStyle|color|fill)\s*[=:]\s*[\"'](?:red|blue|green|yellow|lime|cyan|magenta|purple|orange|#0f0|#00ff00|#ff0000|#f00|#0000ff|#00f|#ffff00|#ff00ff|#00ffff)[\"']",
                     "script", "markup")
    if c:
        return Result(c, ev, f"기본 원색 {c}회")
