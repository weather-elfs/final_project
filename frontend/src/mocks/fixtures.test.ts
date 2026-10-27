import assert from 'node:assert/strict';
import test from 'node:test';

import { dashboardConfig, dashboardFixture } from './fixtures';

test('10월 30일 14:30 기준으로 모든 관측소·예측 간격의 날짜와 기온을 맞춘다', () => {
  const asOf = Date.parse('2026-10-30T14:30:00+09:00');
  const ranges: Record<string, [number, number][]> = {
    '102': [[12, 16], [9, 12], [9, 13]],
    '112': [[6, 14], [6, 13], [5, 12]],
    '201': [[6, 16], [2, 12], [2, 12]],
  };
  assert.equal(Date.parse(dashboardConfig.data.meta.generated_at), asOf);
  for (const { station_id: stationId } of dashboardConfig.data.stations) {
    const stationRanges = ranges[stationId];
    assert.ok(stationRanges);
    const firstDayRange = stationRanges[0];
    assert.ok(firstDayRange);
    for (const interval of dashboardConfig.data.forecast_intervals_h) {
      const fixture = dashboardFixture(stationId, interval);
      assert.ok(fixture);
      assert.equal(Date.parse(fixture.data.current.observed_at), asOf);
      assert.equal(fixture.data.current.temperature_c, firstDayRange[1]);
      assert.equal(fixture.data.current.weather_label, '구름많음');
      assert.equal(Date.parse(fixture.data.meta.generated_at), asOf);
      assert.equal(fixture.data.forecast_timeline.length, 4);
      for (const [index, point] of fixture.data.forecast_timeline.entries()) {
        assert.equal(point.horizon_h, interval * (index + 1));
        assert.equal(Date.parse(point.valid_at), asOf + point.horizon_h * 3_600_000);
        const localDay = new Date(Date.parse(point.valid_at) + 9 * 3_600_000).toISOString().slice(0, 10);
        const dayIndex = ['2026-10-30', '2026-10-31', '2026-11-01'].indexOf(localDay);
        assert.ok(dayIndex >= 0);
        const range: [number, number] | undefined = stationRanges[dayIndex];
        assert.ok(range);
        const [minimum, maximum]: [number, number] = range;
        assert.ok(point.temperature_c >= minimum && point.temperature_c <= maximum, `${stationId} ${point.valid_at}: ${point.temperature_c}`);
        assert.equal(point.weather_label, localDay === '2026-11-01' ? '맑음' : '구름많음');
      }
      assert.equal(fixture.data.forecast_summary.visibility_pred_km, Math.min(...fixture.data.forecast_timeline.map((point) => point.visibility_pred_km)));
    }
  }
});

test('시간별 기온은 보간하고 다음 날 예보를 사용한다', () => {
  const hourly = dashboardFixture('112', 1);
  const daily = dashboardFixture('112', 12);
  assert.ok(hourly && daily);
  assert.deepEqual(hourly.data.forecast_timeline.map((point) => point.temperature_c), [13.5, 12.9, 12.4, 11.9]);
  assert.deepEqual(daily.data.forecast_timeline.map((point) => point.temperature_c), [7.6, 13, 6.6, 12]);
  assert.equal(dashboardFixture('112', 5), null);
  assert.equal(dashboardFixture('unknown', 3), null);
  assert.equal(dashboardFixture('112', 3, true)?.data.mission_evaluation.evaluation_status, 'NOT_EVALUABLE');
});
