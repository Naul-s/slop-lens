---
description: AI Slop 수정 — 최신 판독 결과의 수정 계획을 빠른 수정부터 실제 적용
argument-hint: "[폴더 경로, 생략 시 현재 프로젝트]"
---
`$ARGUMENTS`(비어 있으면 현재 작업 폴더)에 SlopLens 수정 계획을 적용해줘.

1. `slop_scan` → `slop_fix_plan`.
2. '빠른 수정' 항목을 근거 위치(file:line)부터 실제로 고친다. 가짜 후기·통계·연락처는 더 그럴듯한 가짜로 바꾸지 말고 삭제하거나 나에게 물어볼 것.
3. '핵심 개선' 전에 Anti-Slop 브리프의 "먼저 결정할 것" 질문을 나에게 묻고, 답을 받은 뒤 진행.
4. 끝나면 `slop_scan`을 다시 실행해 전후 Slop Index와 해결된 규칙 ID를 보고.
