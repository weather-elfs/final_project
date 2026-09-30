import assert from 'node:assert/strict';
import test from 'node:test';

import { toDashboardConfig, toViewModel } from './dashboardAdapter';

test('API snake_case를 UI camelCase로 변환하고 비활성 항목을 제외한다', () => {
  const config = toDashboardConfig({
    stations: [{ station_id: '112', station_name: '인천', available: true }, { station_id: '999', station_name: '중지', available: false }],
    mission_types: [{ mission_type: 'A', enabled: true }, { mission_type: 'B', enabled: false }],
    forecast_horizons_h: [1, 6],
  });
  assert.deepEqual(config.stations.map(({ id, name }) => ({ id, name })), [{ id: '112', name: '인천' }]);
  assert.deepEqual(config.missionTypes.map(({ missionType }) => missionType), ['A']);
  assert.deepEqual(toViewModel({ mission_evaluation: { rule_version: 'v1' } }), { missionEvaluation: { ruleVersion: 'v1' } });
});
