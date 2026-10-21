# 대시보드 프런트엔드 규칙

- 기술 스택은 React + TypeScript + Vite + Storybook이며 구현 위치는 `frontend/`이다.
- API 조회와 상태는 `*Page`, 응답 변환은 `*Adapter`, 순수 표시는 `*View`와 `components/`로 분리한다.
- UI는 API의 `snake_case` 응답을 직접 소비하지 않는다. 어댑터가 `camelCase` 뷰 모델로 변환한다.
- 임무 가능 여부·종합 판정은 서버 결과만 표시한다. 사용자 요청으로 현재 기상의 시정 영향 요인만 예외로 프론트에서 계산한다: 안개는 `visibilityKm` 기반 프로젝트 6단계(10 km 이상은 안개 없음·파스텔 하늘색), 대기질은 PM2.5·PM10 기반 추정 AQI와 프로젝트 5단계다. 추정 AQI는 EPA/AirNow 농도 구간·선형 보간식을 적용한 두 입자 지수의 최댓값이며, 공식 AQI가 아님을 명시한다. 두 농도 중 하나라도 누락·유효하지 않으면 판단 대기로 표시한다.
- MSW는 개발과 Storybook에서만 사용하며 처리되지 않은 `/api/*` 요청은 오류로 간주한다.
- Storybook은 합성 데이터만 사용하고 외부 지도·기상 서비스나 운영 API를 호출하지 않는다.
- 재사용 CSS는 `.weather-ui` 아래로 범위를 제한한다.
- 대시보드 변경 시 최소 `pnpm typecheck`, `pnpm test`, `pnpm build`, `pnpm build-storybook`을 통과시킨다.
