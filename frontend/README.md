# 저시정 상황판 프론트엔드

- 기술 구성: React + TypeScript + Vite
- 개발·Storybook 데이터: MSW 기반 백엔드 계약 모사
- 도메인 판정: AQI·안개·임무 가능 여부의 프런트엔드 재계산 없이 API 결과 표시

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
  - 현재: 명세 v0.4의 인증 API 부재. `/api/v1/auth/login`은 개발용 MSW 계약이며 운영 보안 수단 아님
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
  - 현재: `mockServiceWorker.js`의 개발·Storybook 전용 사용
  - 운영 전: 배포 산출물에서 제거하거나 웹 서버 제공 차단
- Storybook 공개 금지
  - 운영 관측값·좌표·계정 정보의 story/fixture 사용 금지
  - 게시 시 사내 인증 적용 및 외부 검색·공개 배포 금지
- 명세 확인 필요
  - 현재: 설정 응답 스키마의 관측소 상태 필드와 예시 응답 불일치
  - 계약 확정 전: UI의 `available` 필드만 사용

> 프런트엔드 로그인 화면과 상태값은 서버 인가 수단 아님.
