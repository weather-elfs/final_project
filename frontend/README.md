# 저시정 상황판 프론트엔드

- 기술 구성: React + TypeScript + Vite
- 개발·Storybook 데이터: MSW 기반 백엔드 계약 모사
- 배포 시연 데이터: `demo` 빌드에서만 로그인·경보·이력을 프론트 샘플로 처리하고, 기상 API는 실제 백엔드 사용
- 도메인 판정: 현재 기상의 안개·PM 기반 추정 AQI는 관측값으로 프론트에서 계산하고, 종합 판정·임무 가능 여부는 API 결과 표시

## 실행

```bash
pnpm install
pnpm dev
pnpm test
pnpm typecheck
pnpm build
pnpm storybook
pnpm build-storybook
```

## API 기준

- [BE–FE 연동 API 명세서 v0.4 (2026-09-30)](https://docs.google.com/document/d/1zjBbNEa1c2HuNsfqGURhRHMnJt8upEdP/edit?rtpof=true&tab=t.0)

## Docker 배포용 시연 모드

`pnpm build`는 `vite build --mode demo`로 빌드한다. 생성된 `dist/`를 백엔드 또는
웹 서버에서 제공하고, 같은 출처의 `/api/*`는 실제 백엔드에 연결한다.
Vite 개발 프록시는 배포 파일에 포함되지 않는다.

| 기능 | 시연 빌드 동작 |
| --- | --- |
| 로그인 | 센터 ID `33182`, 공개 시연 코드 `100005`가 모두 맞으면 화면 진입. 서버 요청 없음 |
| 대시보드 설정·현재 관측·예측 | 기존 실제 백엔드 API 사용 |
| 예측 레이어 안개 음영 | 기존 GK2A 격자로 이동 시연. 실제 안개 예측 아님 |
| 경보 운영 | 프론트의 합성 샘플 표시. 실제 발령·해제·저장 없음 |
| 이력 조회 | 합성 샘플 표시와 유형·임무 필터 적용. 실제 조회 결과 저장·이력 API 호출 없음 |

로그인은 **실제 인증·인가 기능이 아닌 공개 시연용 화면**이다. 코드와 샘플 데이터는
브라우저 번들에서 확인할 수 있으며, 이 진입 화면으로 백엔드 API를 보호할 수 없다.
민감 데이터나 실제 운영 기능의 접근 제어로 사용하지 않는다. 비밀번호를 서버로 보내거나
저장하지 않고, 기존 ID 저장 옵션만 유지한다. 새로고침하면 시연 로그인 화면으로 돌아간다.

로그인 화면과 경보·이력 페이지에는 시연용임을 표시한다. 샘플은
`src/mocks/operationsFixtures.ts`, 시연 분기는 `src/demo.ts`와 `src/api.ts`에서 관리한다.
전체 MSW를 운영에서 켜지 않으며 `mockServiceWorker.js`는 시연 빌드 산출물에서 제외한다.
실제 인증·경보·이력 API로 전환할 때는 시연 모드와 연결 정책을 함께 변경해야 한다.

### 예측 레이어 안개 이동 시연

`예측 레이어`에서는 API의 `forecast_timeline` 시점을 그대로 사용하면서 안개 음영만
기존 이동 시연으로 재생한다. API에 `fog_layer`가 없으면 번들에 포함된 과거 GK2A
격자(`src/mocks/gk2aFogLayer.ts`)를 예측 지도 전용 바탕으로 사용한다. 현재 관측 모드에는
이 대체 격자를 넣지 않으며, 관측·예측 수치와 API 응답도 변경하지 않는다.

- 프레임 생성: `src/features/dashboard/forecastFog.ts`의 `buildForecastFogDemoFrames`
- 재생: 기존 900 ms 간격, 프레임 간 부드러운 보간, 마지막 시점 뒤 처음부터 재생
- 표시: 실제 안개 예측이 아닌 과거 격자 기반 시연임을 지도 아래에 명시
- 제어: 일시정지·재생·시점 선택 지원. 동작 줄이기 설정에서는 자동 재생하지 않음
- 예측 시점이 없으면 임의의 시점을 만들지 않음. 재생 중 매 프레임마다 API를 호출하지 않음

이 연결은 실제 API 개발 모드(`pnpm dev:backend`)와 배포 시연 빌드(`pnpm build`) 모두에서
동작하며, 기존 안개 모양·색상·투명도·보간 렌더링은 그대로 사용한다.

## PM 기반 추정 AQI 계산

현재 기상 카드의 **시정 영향 요인 → 대기질**은 API의 `current.pm25_ug_m3`와
`current.pm10_ug_m3`(단위: µg/m³)로 프론트에서 계산한다.
어댑터를 거친 `pm25UgM3`, `pm10UgM3`를 사용하며, 서버의 `current.aqi`나
`diagnosis.pm_display_grade`로 이 영역의 계산값을 대체하지 않는다.

- 구현: [gradeTones.ts](src/features/dashboard/gradeTones.ts)의 `airQualityByParticles`
- 표시: [VisibilitySummary.tsx](src/features/dashboard/components/VisibilitySummary.tsx)
- 테스트: [gradeTones.test.ts](src/features/dashboard/gradeTones.test.ts), [VisibilitySummary.test.ts](src/features/dashboard/components/VisibilitySummary.test.ts)

### 계산 순서와 산식

1. PM2.5는 소수 첫째 자리까지, PM10은 정수까지 남기고 그 아래 자리는 버린다.
   예: PM2.5 `9.19 → 9.1`, PM10 `19.99 → 19`.
2. 아래 표에서 각 농도가 속한 구간을 찾고 선형 보간한다.
3. 각 입자 지수를 가장 가까운 정수로 반올림한다(`Math.round`).
4. 두 입자 지수 중 더 높은 값을 대기질 추정 지수로 표시한다. 더하거나 평균내지 않는다.

```text
입자별 지수 I = (I_high - I_low) / (C_high - C_low) × (C - C_low) + I_low
추정 AQI = max(round(I_PM2.5), round(I_PM10))
```

- `C`: 자릿수 버림을 적용한 입자 농도
- `C_low`, `C_high`: 해당 농도 구간의 하한·상한
- `I_low`, `I_high`: 해당 구간에 대응하는 AQI 하한·상한

### 입자별 농도 구간

EPA/AirNow의 농도 구간과 산식을 사용한다. **입력값의 평균 기간이 확인되지 않으므로
24시간 평균 또는 NowCast를 적용한 공식 AQI가 아닌 단일 관측값 기반 추정값**이다.

| AQI 구간 | PM2.5 농도(µg/m³) | PM10 농도(µg/m³) |
| --- | --- | --- |
| 0–50 | 0.0–9.0 | 0–54 |
| 51–100 | 9.1–35.4 | 55–154 |
| 101–150 | 35.5–55.4 | 155–254 |
| 151–200 | 55.5–125.4 | 255–354 |
| 201–300 | 125.5–225.4 | 355–424 |
| 301–500 | 225.5–325.4 | 425–604 |

표의 마지막 농도 상한을 넘으면 마지막 구간 산식으로 외삽한다. 계산된 지수를
500으로 제한하지 않으며, 300을 초과하는 값은 모두 프로젝트의 위험 5단계다.

### 프로젝트 표시 단계

EPA의 공식 AQI 범주를 그대로 표시하는 것이 아니라, 기존 UI 기준에 따라
AQI 0–50과 51–100을 **양호 1단계**로 묶은 5단계를 사용한다.
배지와 안내 팝업은 같은 `AIR_QUALITY_CRITERIA`를 공유한다.

| 추정 AQI | 표시 단계 | 표시명 | 색상 |
| --- | --- | --- | --- |
| 0–100 | 1/5단계 | 양호 | 초록 |
| 101–150 | 2/5단계 | 민감군 주의 | 주황 |
| 151–200 | 3/5단계 | 나쁨 | 빨강 |
| 201–300 | 4/5단계 | 매우 나쁨 | 보라 |
| 301 이상 | 5/5단계 | 위험 | 적갈색 |

### 계산 예시

인천 응답의 PM2.5 `3 µg/m³`, PM10 `19 µg/m³`인 경우:

```text
PM2.5 지수 = round((50 - 0) / (9.0 - 0.0) × (3.0 - 0.0) + 0) = 17
PM10 지수 = round((50 - 0) / (54 - 0) × (19 - 0) + 0) = 18
추정 AQI = max(17, 18) = 18
화면 표시 = 추정 AQI 18 · 양호 · 1/5단계
```

### 누락값과 한계

- 두 농도가 모두 유효해야 계산한다. 하나라도 `null`·`undefined`·음수·`NaN`·무한대이면
  `추정 AQI — · 판단 대기`, `—/5단계`와 회색 배지를 표시한다. `0`은 유효한 관측값이다.
- 입력 농도의 평균 기간, NowCast, 오존 등 다른 오염물질을 반영하지 않는다.
  따라서 공식 AQI·통합대기환경지수(CAI) 또는 건강·작전 판단의 대체 지표로 사용하지 않는다.
- 관측값이 오래됐어도 그 값으로 계산되며, 데이터 신선도는 출처별 데이터 상태에서 별도로 표시한다.
- 종합 추정 문구와 임무 판정은 이 계산으로 변경하지 않고 서버 응답을 유지한다.

기준 확인일: 2026-10-20.
[EPA/AirNow AQI 기술 문서(2026년 5월), Equation 1·Table 6](https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf),
[EPA AQS 농도 구간표](https://aqs.epa.gov/aqsweb/documents/codetables/aqi_breakpoints.html).

## 구조와 재사용 경계

- `DashboardPage`: API 조회와 상태 관리
- `dashboardAdapter`: API `snake_case`의 UI `camelCase` 변환
- `types.ts`: 화면·컴포넌트 공용 TypeScript 계약
- `DashboardView`: 외부 데이터 의존성 없는 화면 조합
- `components/`: 좁은 props 기반 표시·입력 컴포넌트
- `stories/`: 합성 fixture 기반 상태 카탈로그
- `mocks/`: 개발·Storybook 전용 API 계약

## 재사용 범위

- 기본 묶음: `DashboardView`, `components/`, `dashboardAdapter`, `styles.css`
- npm 패키지 전환 시점: 두 번째 소비자 발생과 버전 정책 확정 이후

## 운영 전 보안 항목

- 인증·인가 계약 미확정
  - 현재: 개발용 `/api/v1/auth/login`은 MSW 계약이며, 배포 시연 모드는 공개 시연 ID·코드를 프론트에서 확인한다. 둘 다 운영 보안 수단이 아님
  - 운영 전: 서버 세션 확인·로그아웃·권한 검사 확정 및 `HttpOnly; Secure; SameSite` 쿠키 적용
- CSRF·CORS 미확정
  - 현재: 쿠키 인증 방식과 실제 API 호스트 미확정
  - 운영 전: CSRF 토큰과 CORS 허용 출처의 서버 공동 확정
- 배포 보안 헤더 미확정
  - 운영 전: `Content-Security-Policy`(`frame-ancestors` 포함), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Cache-Control: no-store`, HTTPS/HSTS 적용
- 발표용 지도 예외
  - 현재: 민감 데이터가 없는 발표 시연에 OpenStreetMap 공개 타일 사용
  - 유의 사항: 외부 타일 서버로 브라우저 IP·요청 좌표·Referer 전달 가능
  - 운영 전: 민감 데이터·운영 환경 전환 전 승인된 내부 타일 서버로 교체
- MSW 운영 제외
  - 현재: MSW는 개발·Storybook 전용. `demo` 빌드는 worker 파일을 산출물에서 제거하고 경보·이력 합성 데이터만 직접 사용
  - 운영 전: 예전에 같은 출처에 등록한 개발용 worker가 없는지 확인. 배포 도메인에서 개발 서버를 제공하지 않음
- Storybook 공개 금지
  - 운영 관측값·좌표·계정 정보의 story/fixture 사용 금지
  - 게시 시 사내 인증 적용 및 외부 검색·공개 배포 금지
- 명세 확인 필요
  - 현재: 설정 응답 스키마의 관측소 상태 필드와 예시 응답 불일치
  - 계약 확정 전: UI의 `available` 필드만 사용

> 프런트엔드 로그인 화면과 상태값은 서버 인가 수단 아님.
