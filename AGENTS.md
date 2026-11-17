# AGENTS.md — SlopLens

이 저장소는 **SlopLens**(AI로 만든 웹사이트·게임의 AI Slop 판독기)다. Codex·Gemini·Claude 등 이 파일을 읽는 모든 에이전트용 안내.

## 이 도구를 *사용*할 때 (다른 프로젝트 검사)
- 판정의 핵심은 **보이고 들리는 것**이다. MCP: `slop_scan` → `slop_review_protocol`(시트 이미지를 직접 열어 봄) → `slop_submit_review` → `slop_fix_plan`
- Unity 게임은 먼저 `python bin/slop-lens.py unity-capture <프로젝트>`로 실행 캡처(원본 무수정, 복사본 빌드)를 만든다.
- 없으면 CLI: `python bin/slop-lens.py scan <폴더|URL>` (Python 3.9+, 의존성 없음)
- 렌더 실측(선택): Node 18+ 와 `npm install --prefix probe` 가 있으면 자동으로 실제 브라우저 측정과 스크린샷이 추가된다. `python bin/slop-lens.py doctor`로 확인.
- 전체 워크플로와 수정 원칙: [skills/slop-lens/SKILL.md](skills/slop-lens/SKILL.md)
- 수정할 때 가짜 후기·통계·연락처를 더 그럴듯한 가짜로 바꾸지 말 것. 브랜드 결정은 사용자에게 먼저 물을 것.

## 이 저장소를 *개발*할 때
- Python 코어는 표준 라이브러리만 사용한다 (모든 에이전트 환경에서 바로 돌아가야 함). 브라우저 측정은 `probe/`(Node, playwright-core)에만 두고, 없을 때는 반드시 정적 분석으로 우아하게 후퇴해야 한다.
- 지각 규칙(사운드·에셋·Unity 기본값)은 `slop_lens/rules/perception.py`, 리뷰 프로토콜은 `slop_lens/review.py`.
- 실측 규칙은 `slop_lens/rules/render.py`. 실측이 더 정확한 정적 규칙은 `replaces=[...]`로 대체하고, 측정했는데 문제가 없으면 `CLEAN`을 반환한다.
- 규칙은 `slop_lens/rules/*.py`에 `@rule(...)`로 추가. `why`, `fix.summary/steps/example/effort/directive` 필수.
- 규칙을 바꾼 뒤:
  ```bash
  python scripts/gen_criteria.py              # docs/CRITERIA.md, 스킬 references 재생성
  python -m unittest discover -s tests -v     # 보정 테스트 (슬롭 샘플 ≥ 기준, 수작업 샘플 < 기준)
  ```
- 오탐 방지: 단일 신호로 높은 점수가 나오지 않게 threshold/saturation을 잡고, `examples/crafted-*`가 계속 20 미만인지 확인.
