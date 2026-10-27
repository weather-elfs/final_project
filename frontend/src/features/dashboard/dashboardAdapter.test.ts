import assert from 'node:assert/strict';
import test from 'node:test';

import { stationsInViewport, toDashboardConfig, toDashboardData, toViewModel } from './dashboardAdapter';
import { normalizeCurrentStatus } from './stationStatus';

test('DB 없이 수집 전인 관측소와 실제 API에서 받은 최신 상태를 구분한다', () => {
  assert.equal(normalizeCurrentStatus('UNKNOWN'), 'UNKNOWN');
  assert.equal(normalizeCurrentStatus('fresh'), 'GOOD');
  assert.equal(normalizeCurrentStatus('delayed'), 'DELAYED');
  assert.equal(normalizeCurrentStatus('missing'), 'MISSING');
});

test('API snake_case를 UI camelCase로 변환하고 비활성 항목을 제외한다', () => {
  const config = toDashboardConfig({
    stations: [{ station_id: '112', station_name: '인천', available: true }, { station_id: '999', station_name: '중지', available: false }],
    mission_types: [{ mission_type: 'A', enabled: true }, { mission_type: 'B', enabled: false }],
    forecast_interval_options_h: [1, 3, 6, 12],
  });
  assert.deepEqual(config.stations.map(({ id, name }) => ({ id, name })), [{ id: '112', name: '인천' }]);
  assert.deepEqual(config.missionTypes.map(({ missionType }) => missionType), ['A']);
  assert.deepEqual(config.forecastIntervalOptionsH, [1, 3, 6, 12]);
  assert.deepEqual(toViewModel({ mission_evaluation: { rule_version: 'v1' } }), { missionEvaluation: { ruleVersion: 'v1' } });
});

test('백엔드 설정 응답의 forecast_intervals_h 별칭을 지원한다', () => {
  const config = toDashboardConfig({
    stations: [],
    mission_types: [],
    forecast_intervals_h: [1, 3, 6, 12],
  });

  assert.deepEqual(config.forecastIntervalOptionsH, [1, 3, 6, 12]);
});

test('백엔드의 고정 FAIL 상태를 현재 자료 지연과 예측 미제공으로 구분한다', () => {
  const config = toDashboardConfig({
    stations: [{
      station_id: '112',
      station_name: '인천',
      latitude: 37.47772,
      longitude: 126.6249,
      available: true,
      current_status: 'FAIL',
      forecast_status: 'FAIL',
    }],
    mission_types: [],
    forecast_intervals_h: [1, 3, 6, 12],
  });

  assert.equal(config.stations[0]?.currentStatus, 'DELAYED');
  assert.equal(config.stations[0]?.forecastStatus, 'NOT_AVAILABLE');
});

test('백엔드 대시보드 응답의 소스 상태 객체와 해양 자료를 UI 모델로 변환한다', () => {
  const dashboard = toDashboardData({
    station: { station_id: '112', station_name: '인천' },
    current: {
      observed_at: '2026-09-18T09:00:00+09:00',
      temperature_c: 18,
      relative_humidity_pct: 81,
      visibility_km: 4.8,
    },
    marine: {
      water_temperature_c: 21.4,
      salinity_psu: 31.2,
      wave_height_m: null,
    },
    source_status: {
      asos: { status: 'OK', observed_at: '2026-09-18T09:00:00+09:00', age_minutes: 0, reason: null },
      airkorea: { status: 'STALE', observed_at: '2026-09-18T08:00:00+09:00', age_minutes: 60, reason: '지연' },
      marine: { status: 'MISSING', observed_at: null, age_minutes: null, reason: '결측' },
    },
    forecast_timeline: [],
    mission_evaluation: { evaluation_status: 'NOT_EVALUABLE' },
  });

  assert.deepEqual(dashboard.sourceStatus?.map(({ source, status }) => ({ source, status })), [
    { source: 'asos', status: 'OK' },
    { source: 'airkorea', status: 'STALE' },
    { source: 'marine', status: 'MISSING' },
  ]);
  assert.deepEqual(dashboard.apiStatus?.summary, { good: 1, delayed: 1, fail: 1 });
  assert.equal(dashboard.marine?.waterTemperatureC, 21.4);
  assert.equal(dashboard.marine?.waveHeightM, null);
});

test('최신 백엔드 예측 응답과 fresh/delayed/missing 상태를 UI 모델로 변환한다', () => {
  const dashboard = toDashboardData({
    request_context: {
      forecast_interval_h: 3,
      forecast_horizons_h: [3, 6, 9, 12],
      mission_type: 'MARITIME_TRANSPORT',
    },
    source_status: [
      { source: 'ASOS', status: 'fresh' },
      { source: 'AIRKOREA', status: 'delayed' },
      { source: 'TIDE_OBSERVATORY', status: 'missing' },
    ],
    forecast_timeline: [{
      horizon_h: 3,
      valid_at: '2022-01-01T04:00:00+09:00',
      visibility_pred_km: 4.2,
      visibility_grade: 'MODERATE',
      fog_grade_label: '옅은 안개',
      pm25_pred_ug_m3: 18.2,
      pm10_pred_ug_m3: 31.4,
    }],
    forecast_summary: {
      horizon_h: 3,
      visibility_pred_km: 4.2,
      selection_reason: 'MIN_VISIBILITY',
    },
    mission_evaluation: {
      mission_type: 'MARITIME_TRANSPORT',
      evaluation_status: 'EVALUATED',
      passed: true,
      mission_grade: 'NORMAL',
      reason_codes: ['VISIBILITY_OK'],
    },
    meta: { mock: false },
  });

  assert.equal(dashboard.requestContext?.forecastIntervalH, 3);
  assert.equal(dashboard.forecastTimeline?.[0]?.visibilityGrade, 'MODERATE');
  assert.equal(dashboard.forecastTimeline?.[0]?.pm25PredUgM3, 18.2);
  assert.equal(dashboard.forecastSummary?.selectionReason, 'MIN_VISIBILITY');
  assert.equal(dashboard.missionEvaluation?.missionType, 'MARITIME_TRANSPORT');
  assert.deepEqual(dashboard.missionEvaluation?.reasonCodes, ['VISIBILITY_OK']);
  assert.deepEqual(dashboard.apiStatus?.summary, { good: 1, delayed: 1, fail: 1 });
  assert.equal(dashboard.meta?.mock, false);
});

test('같은 예측 간격과 대상 시각의 기상청 예보를 연결하고 모델 결과는 유지한다', () => {
  const dashboard = toDashboardData({
    forecast_timeline: [{ horizon_h: 3, valid_at: '2026-10-27T12:00:00+09:00', visibility_pred_km: 4.6 }],
    meta: { forecasts: [{ horizon_h: 3, valid_at: '2026-10-27T03:00:00Z', values: { future_fcst_temp: 17, future_fcst_wind_dir: 315, future_fcst_wind_speed: 4, future_fcst_sky: 4, future_fcst_pty: 0 } }] },
  });
  const point = dashboard.forecastTimeline?.[0];
  assert.equal(point?.temperatureC, 17);
  assert.equal(point?.windDirectionLabel, '북서풍');
  assert.equal(point?.windSpeedMS, 4);
  assert.equal(point?.weatherLabel, '흐림');
  assert.equal(point?.visibilityPredKm, 4.6);
});

test('다른 시각 예보·결측 강수 코드는 날씨를 채우지 않고 명시된 timeline 값은 보존한다', () => {
  const forecast = { horizon_h: 3, valid_at: '2026-10-27T12:00:00+09:00', values: { future_fcst_temp: 17, future_fcst_wind_dir: null, future_fcst_sky: 1, future_fcst_pty: null as number | null } };
  const convert = (validAt: string, temperature?: number | null) => toDashboardData({
    forecast_timeline: [{ horizon_h: 3, valid_at: validAt, ...(temperature === undefined ? {} : { temperature_c: temperature }) }],
    meta: { forecasts: [forecast] },
  }).forecastTimeline?.[0];
  assert.equal(convert('2026-10-27T15:00:00+09:00')?.temperatureC, undefined);
  assert.equal(convert(forecast.valid_at)?.weatherLabel, undefined);
  assert.equal(convert(forecast.valid_at)?.windDirectionLabel, undefined);
  assert.equal(convert(forecast.valid_at, null)?.temperatureC, null);
  assert.equal(convert(forecast.valid_at, 20)?.temperatureC, 20);
  for (const [code, label] of [[1, '비'], [2, '비 또는 눈'], [3, '눈'], [4, '소나기']] as const) {
    forecast.values.future_fcst_pty = code;
    assert.equal(convert(forecast.valid_at)?.weatherLabel, label);
  }
});

test('설정 응답의 좌표로 현재 지도 범위 안 관측소만 반환한다', () => {
  const config = toDashboardConfig({
    stations: [
      { station_id: '102', station_name: '백령도', latitude: 37.97396, longitude: 124.71237, available: true },
      { station_id: '112', station_name: '인천', latitude: 37.47772, longitude: 126.6249, available: true },
      { station_id: '201', station_name: '강화', latitude: 37.70739, longitude: 126.44634, available: true },
    ],
    mission_types: [],
    forecast_interval_options_h: [],
  });

  const visible = stationsInViewport(config.stations, {
    west: 126.3, south: 37.3, east: 126.9, north: 37.65, zoom: 10,
  });

  assert.deepEqual(visible.map((station) => station.id), ['112']);
});

test('GK2A 안개 레이어의 좌표와 품질 정보를 camelCase로 변환한다', () => {
  const config = toDashboardConfig({
    stations: [],
    mission_types: [],
    forecast_interval_options_h: [],
    fog_layer: {
      source: 'GK2A',
      observed_at: '2025-06-23T13:00:00Z',
      projection: 'LCC',
      resolution_km: 2,
      quality: { field: 'fog_dqf', accepted_values: [0] },
      legend: [{ value: 5, label: '안개', color: '#7a001f' }],
      cells: [{ id: '440-381', fog_class: 5, positions: [[37.5, 126.5]] }],
    },
  });

  assert.equal(config.fogLayer?.observedAt, '2025-06-23T13:00:00Z');
  assert.deepEqual(config.fogLayer?.quality.acceptedValues, [0]);
  assert.equal(config.fogLayer?.cells[0]?.fogClass, 5);
});
