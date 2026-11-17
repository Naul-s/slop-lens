---
description: SlopLens를 GitHub 최신 버전으로 업데이트
argument-hint: "[--check: 확인만]"
---
SlopLens를 GitHub 최신 버전으로 업데이트해줘.

1. 다음 명령을 실행한다 (`$ARGUMENTS`가 `--check`이면 그대로 붙여서 확인만 한다):
   `python "${CLAUDE_PLUGIN_ROOT}/bin/slop-lens.py" update $ARGUMENTS`
2. 출력에서 업데이트 전후 커밋과 브라우저 측정 모듈 상태를 짧게 알려준다.
3. 새 버전을 받았다면 `/reload-plugins`를 실행하거나 새 세션을 열어야 적용된다고 안내한다.
