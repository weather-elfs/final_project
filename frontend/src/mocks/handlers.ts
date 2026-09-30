import { delay, http, HttpResponse } from 'msw';

import { dashboardConfig, dashboardFixture } from './fixtures';

function apiError(code: string, message: string, data: unknown = null, status = 200) {
  return HttpResponse.json({ code, message, data }, { status });
}

export const handlers = [
  // 임시 개발 계약: 실제 인증 계약은 서버 확정 후 교체한다.
  http.post('/api/v1/auth/login', async ({ request }) => {
    const credentials = await request.json() as { center_id?: string; password?: string };
    await delay(350);
    if (!credentials.center_id || !credentials.password) return apiError('INVALID_CREDENTIALS', '센터 ID와 비밀번호를 확인하세요.', null, 401);
    return HttpResponse.json({ code: 'SUCCESS', message: '로그인되었습니다.', data: { center: { id: credentials.center_id, name: '인천 연안 관제센터' } } });
  }),

  http.get('/api/v1/dashboard/config', async () => {
    await delay(220);
    return HttpResponse.json(dashboardConfig);
  }),

  http.get('/api/v1/stations/:stationId/dashboard', async ({ params, request }) => {
    const stationId = String(params.stationId);
    const url = new URL(request.url);
    const horizonH = Number(url.searchParams.get('horizon_h'));
    const minimumVisibilityKm = Number(url.searchParams.get('minimum_visibility_km'));
    const missionType = url.searchParams.get('mission_type');
    await delay(300);

    if (!dashboardConfig.data.stations.some((station) => station.station_id === stationId && station.available)) {
      return apiError('STATION_NOT_FOUND', '지원하지 않는 관측소입니다.', { station_id: stationId, meta: { request_id: 'req_20260930_000010' } });
    }
    if (!dashboardConfig.data.forecast_horizons_h.includes(horizonH) || !Number.isFinite(minimumVisibilityKm) || minimumVisibilityKm < 0.1 || minimumVisibilityKm > 50) {
      return apiError('INVALID_PARAMETER', '예측 시간 또는 최소 시정 기준을 확인하세요.', { meta: { request_id: 'req_20260930_000011' } });
    }
    if (!dashboardConfig.data.mission_types.some((mission) => mission.mission_type === missionType && mission.enabled)) {
      return apiError('MISSION_TYPE_NOT_SUPPORTED', '지원하지 않는 임무 유형입니다.', { mission_type: missionType, meta: { request_id: 'req_20260930_000012' } });
    }

    const fixture = dashboardFixture(stationId, horizonH, minimumVisibilityKm);
    return fixture ? HttpResponse.json(fixture) : apiError('MODEL_UNAVAILABLE', '예측 자료를 생성하지 못했습니다.');
  }),
];
