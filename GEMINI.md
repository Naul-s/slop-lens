# SlopLens (Gemini CLI extension)

이 확장은 AI로 만든 웹사이트·게임의 **AI Slop** 여부를 판독하는 MCP 도구를 제공한다.

- 사용자가 "AI 슬롭인지", "AI 티 나는지", "사운드가 밋밋한지", "게임필"을 물으면 `slop_scan` → `slop_review_protocol`(시트 이미지를 직접 봄) → `slop_submit_review` → `slop_fix_plan` 순서로 사용한다. Unity 게임은 먼저 `slop-lens.py unity-capture`.
- 판정을 설명할 때는 점수만이 아니라 근거 위치(file:line)와 "사람이 왜 그렇게 느끼는지"를 함께 말한다.
- 수정할 때 가짜 후기·통계·연락처를 더 그럴듯한 가짜로 바꾸지 않는다. 브랜드 결정은 사용자에게 먼저 묻는다.
- 전체 워크플로: `skills/slop-lens/SKILL.md`, 판정 기준: `docs/CRITERIA.md`
- 명령: `/slop-check [경로|URL]`, `/slop-fix [경로]`
