# 조사 기록 — 무엇을 근거로 바꿨나 (2026-11-23)

각 자료에서 **확인한 것**과, 그래서 **SlopLens에서 바꾼 것**을 나눠 적는다. 논문은 본문 일부와 요약으로 읽었고 재현하지는 않았다.

## 1. 멀티모달 AI는 사람의 UI 판단을 얼마나 따라가나

[MLLM as a UI Judge](https://arxiv.org/html/2510.08783v1) — UI 30개, 사람 응답 9,296건, 모델 3종(각 10회 채점의 중앙값)
- 절대 점수는 사람과 상관 약 0.7이지만, 둘 중 무엇이 나은지 고르는 과제는 전체 53~60%였다. 사람 점수 차이가 작으면 거의 동전 던지기였다.
- 저자들의 결론은 사람 테스트의 보완이지 대체가 아니라는 것이다.
- 본문과 표의 수치가 서로 다른 곳이 있어 대략의 크기로만 인용한다.

[Distorted Perspectives of LLM-Simulated Preferences](https://arxiv.org/html/2605.18311) — 실제 선호 테스트 29건, 2,073명
- AI가 흉내 낸 선호는 1순위가 53%만 일치했고, 과제의 44%에서 분포가 유의하게 달랐다. 이유 설명은 일반론이 많고 없는 요소를 지어내기도 했다.

**바꾼 것**
- 답 한두 개로는 판정이 확정되지 않는다 (S1 포함 5개 이상).
- 근거 없이 3 이상을 준 리뷰는 신뢰도 "높음"이 될 수 없다.
- 수정 후 예상 점수는 리뷰어의 인상이 바뀐다고 가정하지 않는다.

## 2. 사람 기준 데이터는 어떻게 모아야 하나

[UI-Bench](https://arxiv.org/abs/2508.20410) — 생성 사이트 300개, 전문가 194명, 블라인드 쌍대 비교 4,075건
- 절대 평점은 사람마다 척도 해석과 앵커링이 달라 잡음이 크다고 보고 쌍대 비교를 택했다.

**바꾼 것**
- [`scripts/human_benchmark.py`](../scripts/human_benchmark.py): 익명 쌍대 비교 키트, 사람끼리의 일치도(Krippendorff α), 도구와 사람의 일치도와 작품 단위 재표집 구간.
- **아직 실제 평가자 데이터는 없다.** 도구만 준비됐고 정확도는 여전히 미검증이다.

"AI 슬롭" 인상을 사람 평가자로 직접 잰 동료 검토 연구는 이번 검색에서 찾지 못했다. 업계 블로그의 비율 수치는 출처를 확인할 수 없어 쓰지 않았다.

## 3. 신뢰할 수 없는 페이지를 실행하는 도구의 안전

- [Playwright `chromiumSandbox`](https://playwright.dev/docs/api/class-browsertype): 기본값이 `false`다 → 항상 켠다. 컨테이너용으로 `SLOP_LENS_NO_SANDBOX=1`만 남겼다.
- [Playwright 네트워크](https://playwright.dev/docs/network): 서비스 워커의 요청은 `context.route()`에 잡히지 않는다 → 서비스 워커를 막고 네트워크 계층에서 변경 요청을 차단한다.
- [Node 프로세스 I/O](https://nodejs.org/api/process.html#a-note-on-process-io): macOS·Linux의 파이프는 비동기라 `process.exit()`가 출력을 자를 수 있다 → 쓰기가 끝난 뒤 종료한다.

## 4. MCP와 플러그인 형식

- [플러그인 매니페스트](https://code.claude.com/docs/en/plugins-reference): `mcpServers`를 `plugin.json` 안에 둘 수 있다 → 루트 `.mcp.json`은 저장소를 열었을 때 프로젝트 서버로도 읽혀 실패하므로 없앴다.
- [MCP stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio): 취소 알림을 받으면 작업을 멈추고 그 요청에 답하지 않는다 → 프로브 프로세스 트리까지 종료한다.
- [MCP 버전 규칙](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning): 2026-07-28은 handshake가 없는 방식이다. 이 서버는 2025-06-18까지 지원하므로 구·신 겸용 클라이언트에서는 동작하고 **신규 전용 클라이언트에서는 동작하지 않는다.**
