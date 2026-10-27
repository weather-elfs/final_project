import { delay, http, HttpResponse } from 'msw';

import { dashboardConfig, dashboardFixture } from './fixtures';
import { alertOperationsFixture, historyRecords } from './operationsFixtures';

function apiError(code: string, message: string, data: unknown = null, status = 200) {
  return HttpResponse.json({ code, message, data }, { status });
}

export const operationsHandlers = [
  http.get('/api/v1/alerts/operations', async () => {
    await delay(180);
    return HttpResponse.json(alertOperationsFixture);
  }),

  http.get('/api/v1/history', async ({ request }) => {
    const url = new URL(request.url);
    const historyType = url.searchParams.get('history_type');
    const missionType = url.searchParams.get('mission_type');
    await delay(180);
    const records = historyRecords.filter((record) => (
      (!historyType || record.type === historyType)
      && (!missionType || record.mission_type === missionType)
    ));
    return HttpResponse.json({
      code: 'SUCCESS',
      message: '운영 이력을 조회했습니다.',
      data: { records, total: records.length, page: 1, page_size: 10, meta: { request_id: 'req_history_20261030', generated_at: '2026-10-30T14:30:00+09:00' } },
    });
  }),
];

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

  ...operationsHandlers,

  http.get('/api/v1/stations/:stationId/dashboard', async ({ params, request }) => {
    const stationId = String(params.stationId);
    const url = new URL(request.url);
    const forecastIntervalH = Number(url.searchParams.get('forecast_interval_h'));
    const missionType = url.searchParams.get('mission_type');
    const mock = url.searchParams.get('mock') === 'true';
    await delay(300);

    if (!dashboardConfig.data.stations.some((station) => station.station_id === stationId && station.available)) {
      return apiError('STATION_NOT_FOUND', '지원하지 않는 관측소입니다.', { station_id: stationId, meta: { request_id: 'req_20261030_000010' } }, 404);
    }
    if (!dashboardConfig.data.forecast_intervals_h.includes(forecastIntervalH)) {
      return apiError('INVALID_PARAMETER', '예측 간격을 확인하세요.', { forecast_interval_h: forecastIntervalH, meta: { request_id: 'req_20261030_000011' } }, 422);
    }
    if (!dashboardConfig.data.mission_types.some((mission) => mission.mission_type === missionType && mission.enabled)) {
      return apiError('INVALID_PARAMETER', '지원하지 않는 임무 유형입니다.', { mission_type: missionType, meta: { request_id: 'req_20261030_000012' } }, 422);
    }

    const fixture = dashboardFixture(stationId, forecastIntervalH, mock);
    return fixture ? HttpResponse.json(fixture) : apiError('MODEL_UNAVAILABLE', '예측 자료를 생성하지 못했습니다.');
  }),
];
