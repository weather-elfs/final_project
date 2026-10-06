import assert from 'node:assert/strict';
import test from 'node:test';

import { stationsInViewport, toDashboardConfig, toViewModel } from './dashboardAdapter';

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
