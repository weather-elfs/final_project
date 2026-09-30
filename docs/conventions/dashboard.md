# 대시보드 프런트엔드 규칙

- 기술 스택은 React + TypeScript + Vite + Storybook이며 구현 위치는 `frontend/`이다.
- API 조회와 상태는 `*Page`, 응답 변환은 `*Adapter`, 순수 표시는 `*View`와 `components/`로 분리한다.
- UI는 API의 `snake_case` 응답을 직접 소비하지 않는다. 어댑터가 `camelCase` 뷰 모델로 변환한다.
- AQI, 안개, 임무 가능 여부 등 도메인 판정은 서버 결과만 표시한다.
- MSW는 개발과 Storybook에서만 사용하며 처리되지 않은 `/api/*` 요청은 오류로 간주한다.
- Storybook은 합성 데이터만 사용하고 외부 지도·기상 서비스나 운영 API를 호출하지 않는다.
- 재사용 CSS는 `.weather-ui` 아래로 범위를 제한한다.
- 대시보드 변경 시 최소 `pnpm typecheck`, `pnpm test`, `pnpm build`, `pnpm build-storybook`을 통과시킨다.
