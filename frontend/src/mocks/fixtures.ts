type ForecastSnapshot = [visibilityKm: number, pm25: number, pm10: number, fogLabel: string];

interface StationSnapshot {
  station: { station_id: string; station_name: string };
  current: {
    visibility_km: number;
    pm25_ug_m3: number;
    pm10_ug_m3: number;
    relative_humidity_pct: number;
    temperature_dewpoint_spread_c: number;
  };
  forecasts: { 1: ForecastSnapshot; 6: ForecastSnapshot };
  history: [number, number, number];
}

export const dashboardConfig = {
  code: 'SUCCESS',
  message: '대시보드 설정을 조회했습니다.',
  data: {
    stations: [
      { station_id: '102', station_name: '백령도', latitude: 37.97396, longitude: 124.71237, available: true },
      { station_id: '112', station_name: '인천', latitude: 37.47772, longitude: 126.6249, available: true },
      { station_id: '201', station_name: '강화', latitude: 37.70739, longitude: 126.44634, available: true },
    ],
    forecast_horizons_h: [1, 6],
    mission_types: [
      {
        mission_type: 'MARITIME_TRANSPORT',
        display_name: '해상 수송·보급',
        enabled: true,
        rule_version: 'maritime-transport-v1',
        required_metrics: ['visibility_pred_km'],
      },
      {
        mission_type: 'PORT_ENTRY_EXIT',
        display_name: '입출항·접안',
        enabled: false,
        rule_version: null,
        required_metrics: ['visibility_pred_km', 'wind_speed_pred_m_s'],
      },
    ],
    meta: { request_id: 'req_20260930_000002', partial: false },
  },
};

const stationSnapshots: Record<string, StationSnapshot> = {
  '102': {
    station: { station_id: '102', station_name: '백령도' },
    current: { visibility_km: 7.2, pm25_ug_m3: 18, pm10_ug_m3: 31, relative_humidity_pct: 76, temperature_dewpoint_spread_c: 3.4 },
    forecasts: { 1: [6.9, 19, 32, '박무'], 6: [5.8, 22, 36, '박무'] },
    history: [7.8, 7.6, 7.4],
  },
  '112': {
    station: { station_id: '112', station_name: '인천' },
    current: { visibility_km: 4.8, pm25_ug_m3: 27, pm10_ug_m3: 44, relative_humidity_pct: 81, temperature_dewpoint_spread_c: 2.8 },
    forecasts: { 1: [4.5, 28, 45, '박무'], 6: [3.9, 30, 48, '안개 가능'] },
    history: [5.1, 5.0, 4.9],
  },
  '201': {
    station: { station_id: '201', station_name: '강화' },
    current: { visibility_km: 3.6, pm25_ug_m3: 34, pm10_ug_m3: 53, relative_humidity_pct: 88, temperature_dewpoint_spread_c: 1.6 },
    forecasts: { 1: [3.3, 35, 54, '박무'], 6: [2.6, 39, 58, '안개 가능'] },
    history: [4.2, 4.0, 3.8],
  },
};

export function dashboardFixture(stationId: string, horizonH: number, minimumVisibilityKm: number) {
  const snapshot = stationSnapshots[stationId];
  if (!snapshot) return null;

  const selected = snapshot.forecasts[horizonH as 1 | 6] ?? snapshot.forecasts[6];
  if (!selected) return null;
  const passed = selected[0] >= minimumVisibilityKm;
  const observedAt = '2026-09-30T09:00:00+09:00';
  const validAt = horizonH === 1 ? '2026-09-30T10:00:00+09:00' : '2026-09-30T15:00:00+09:00';

  return {
    code: 'PARTIAL_SUCCESS',
    message: '일부 자료가 재시도 후 수집되어 사용 가능한 결과를 반환했습니다.',
    data: {
      station: snapshot.station,
      request_context: {
        horizon_h: horizonH,
        history_hours: 3,
        mission_type: 'MARITIME_TRANSPORT',
        minimum_visibility_km: minimumVisibilityKm,
      },
      current: {
        observed_at: observedAt,
        ...snapshot.current,
        aqi: { value: 84, display_level: 1, display_grade: '양호', status: 'calculated' },
        status: 'fresh',
      },
      selected_forecast: {
        base_time: observedAt,
        horizon_h: horizonH,
        valid_at: validAt,
        visibility_pred_km: selected[0],
        pm25_pred_ug_m3: selected[1],
        pm10_pred_ug_m3: selected[2],
        fog_grade_code: selected[3] === '박무' ? 'MIST' : 'FOG_POSSIBLE',
        fog_grade_label: selected[3],
        aqi: { value: 84, display_level: 1, display_grade: '양호', status: 'calculated' },
        status: 'ready',
      },
      forecast_timeline: [
        { horizon_h: 1, visibility_pred_km: snapshot.forecasts[1][0], fog_grade_label: snapshot.forecasts[1][3], aqi: { display_grade: '양호' } },
        { horizon_h: 6, visibility_pred_km: snapshot.forecasts[6][0], fog_grade_label: snapshot.forecasts[6][3], aqi: { display_grade: '양호' } },
      ],
      history: [
        { observed_at: '2026-09-30T06:00:00+09:00', visibility_km: snapshot.history[0] },
        { observed_at: '2026-09-30T07:00:00+09:00', visibility_km: snapshot.history[1] },
        { observed_at: '2026-09-30T08:00:00+09:00', visibility_km: snapshot.history[2] },
      ],
      mission_evaluation: {
        mission_type: 'MARITIME_TRANSPORT',
        rule_version: 'maritime-transport-v1',
        evaluation_status: 'EVALUATED',
        passed,
        mission_grade: passed ? 'NORMAL' : 'RESTRICTED',
        factors: [{ metric: 'visibility_pred_km', actual: selected[0], operator: '>=', threshold: minimumVisibilityKm, unit: 'km', required: true, passed }],
        reason_codes: [passed ? 'VISIBILITY_OK' : 'VISIBILITY_BELOW_MINIMUM'],
      },
      diagnosis: { fog_label: selected[3] === '안개 가능' ? '안개' : selected[3], pm_display_grade: '좋음', summary: '안개 영향 우세 · 미세먼지는 보조 요인' },
      source_status: [
        { source: 'ASOS', status: 'fresh', observed_at: observedAt },
        { source: 'AIRKOREA', status: 'fresh', observed_at: observedAt },
        { source: 'BUOY', status: 'delayed', observed_at: '2026-09-30T08:00:00+09:00' },
        { source: 'SATELLITE', status: 'fresh', observed_at: observedAt },
      ],
      api_status: {
        overall: { code: 'RETRY_SUCCESS', label: 'Retry Success' },
        sources: [
          { source: 'ASOS', code: 'GOOD', label: 'Good', attempts: 1 },
          { source: 'AIRKOREA', code: 'GOOD', label: 'Good', attempts: 1 },
          { source: 'BUOY', code: 'RETRY_SUCCESS', label: 'Retry Success', attempts: 2 },
        ],
      },
      meta: { request_id: `req_20260930_${stationId}_${horizonH}`, generated_at: '2026-09-30T09:05:00+09:00', partial: true },
    },
  };
}
