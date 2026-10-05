import assert from 'node:assert/strict';
import test from 'node:test';

import { ApiError, buildDashboardUrl, request } from './api';

test('대시보드 URL에 명세의 통합 조회 조건을 모두 포함한다', () => {
  const url = new URL(buildDashboardUrl({
    stationId: '112', forecastIntervalH: 6, missionType: 'MARITIME_TRANSPORT',
  }), 'https://example.test');

  assert.equal(url.pathname, '/api/v1/stations/112/dashboard');
  assert.equal(url.searchParams.get('forecast_interval_h'), '6');
  assert.equal(url.searchParams.get('mission_type'), 'MARITIME_TRANSPORT');
});

test('HTTP 200 오류 응답도 코드와 요청 ID를 보존해 거부한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({
    code: 'STATION_NOT_FOUND',
    message: '관측소 없음',
    data: { station_id: '999', meta: { request_id: 'req-1' } },
  }));

  await assert.rejects(request('/api/test'), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, 'STATION_NOT_FOUND');
    assert.equal(error.requestId, 'req-1');
    assert.equal((error.data as { station_id: string }).station_id, '999');
    return true;
  });
});

test('JSON이 아닌 응답은 INVALID_RESPONSE로 정규화한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('gateway error', { status: 502 }));
  await assert.rejects(request('/api/test'), { name: 'ApiError', code: 'INVALID_RESPONSE', status: 502 });
});

test('PARTIAL_SUCCESS는 사용 가능한 응답으로 반환한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ code: 'PARTIAL_SUCCESS', data: { meta: { partial: true } } }));
  assert.equal((await request('/api/test')).code, 'PARTIAL_SUCCESS');
});
