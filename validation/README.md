# 직접 검증하기

이 폴더의 실제 검증 데이터(스크린샷·리포트·개인 프로젝트 결과)는 저장소에 올리지 않습니다.
다른 사람의 페이지 화면, 비공개 프로젝트, 특정 제작자의 작업에 대한 판정이 들어 있기 때문입니다. 결과 요약은 [docs/VALIDATION.md](../docs/VALIDATION.md)에 있습니다.

같은 방식으로 직접 재 볼 수 있습니다.

1. 대상 목록을 만든다. 형식은 [targets.example.json](targets.example.json)을 참고하세요.
   - `label`은 **누가 만들었나**(`ai` / `human`)입니다. "슬롭인가"가 아닙니다.
   - 대상을 고르기 전에 고르는 규칙(무작위 시드, 갤러리 순서 등)을 먼저 정하세요. 결과를 보고 고르면 숫자가 의미를 잃습니다.
2. 측정한다 (점수를 보기 전에 리뷰하려면 출력을 열지 마세요).
   ```bash
   python scripts/validate.py my-targets.json --out validation/my-results
   ```
3. (선택) 측정값을 보지 않고 화면만 보고 리뷰한다: `scan <대상> --protocol --blind`
   - 리뷰 JSON의 `meta`에 `blind`와 `knew_expected`(제작자를 미리 알았나)를 정직하게 적으세요.
   ```bash
   python scripts/apply_reviews.py my-targets.json my-reviews/ validation/my-final
   ```
4. 정확도를 계산한다 (AUC, 90% 구간, 기준선 정확도, 규칙별 변별력).
   ```bash
   python scripts/evaluate.py my-targets.json validation/my-results --final validation/my-final
   ```

결과를 [이슈](https://github.com/Naul-s/slop-lens/issues)로 공유해 주시면 기준을 개선하는 데 씁니다. 특히 **오판 사례**(사람이 만든 작품이 높게, AI 슬롭이 낮게 나온 경우)가 가장 도움이 됩니다.
