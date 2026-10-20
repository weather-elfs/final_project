import assert from 'node:assert/strict';
import test from 'node:test';

import { ApiError, buildDashboardConfigUrl, buildDashboardUrl, buildHistoryUrl, request } from './api';

test('대시보드 설정 URL에 지도 경계 좌표를 포함한다', () => {
  const url = new URL(buildDashboardConfigUrl({
    south: 37,
    west: 124,
    north: 38.3,
    east: 127,
  }), 'https://example.test');

  assert.equal(url.pathname, '/api/v1/dashboard/config');
  assert.equal(url.searchParams.get('south'), '37');
  assert.equal(url.searchParams.get('west'), '124');
  assert.equal(url.searchParams.get('north'), '38.3');
  assert.equal(url.searchParams.get('east'), '127');
});

test('대시보드 URL에 명세의 통합 조회 조건을 모두 포함한다', () => {
  const url = new URL(buildDashboardUrl({
    stationId: '112',
    forecastIntervalH: 6,
    missionType: 'MARITIME_TRANSPORT',
    asOf: '2022-01-01T01:00:00+09:00',
    mock: false,
  }), 'https://example.test');

  assert.equal(url.pathname, '/api/v1/stations/112/dashboard');
  assert.equal(url.searchParams.get('forecast_interval_h'), '6');
  assert.equal(url.searchParams.get('mission_type'), 'MARITIME_TRANSPORT');
  assert.equal(url.searchParams.get('as_of'), '2022-01-01T01:00:00+09:00');
  assert.equal(url.searchParams.get('mock'), 'false');
});

test('선택 파라미터가 없으면 as_of와 mock을 전송하지 않는다', () => {
  const url = new URL(buildDashboardUrl({
    stationId: '112', forecastIntervalH: 3, missionType: 'MARITIME_TRANSPORT',
  }), 'https://example.test');

  assert.equal(url.searchParams.has('as_of'), false);
  assert.equal(url.searchParams.has('mock'), false);
});

test('이력 조회 URL에는 선택한 필터만 포함한다', () => {
  const filtered = new URL(buildHistoryUrl({
    historyType: 'ALERT', missionType: 'MARITIME_TRANSPORT',
  }), 'https://example.test');
  const unfiltered = new URL(buildHistoryUrl({
    historyType: 'ALL', missionType: 'ALL',
  }), 'https://example.test');

  assert.equal(filtered.pathname, '/api/v1/history');
  assert.equal(filtered.searchParams.get('history_type'), 'ALERT');
  assert.equal(filtered.searchParams.get('mission_type'), 'MARITIME_TRANSPORT');
  assert.equal(unfiltered.search, '');
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

test('FastAPI detail 오류 메시지를 보존한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({
    detail: '지도 경계 좌표가 필요합니다.',
  }, { status: 422 }));

  await assert.rejects(request('/api/test'), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 422);
    assert.equal(error.message, '지도 경계 좌표가 필요합니다.');
    return true;
  });
});
