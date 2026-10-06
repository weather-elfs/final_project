import { gk2aFogLayer } from './gk2aFogLayer';

interface StationSnapshot {
  station: { station_id: string; station_name: string; latitude: number; longitude: number };
  current: {
    visibility_km: number;
    pm1_ug_m3: number;
    pm25_ug_m3: number;
    pm10_ug_m3: number;
    temperature_c: number;
    wind_direction_deg: number;
    wind_direction_label: string;
    wind_speed_m_s: number;
    relative_humidity_pct: number;
    temperature_dewpoint_spread_c: number;
    weather_label: string;
    fog_grade_label: string;
  };
}
const OBSERVED_AT = '2026-09-18T09:00:00+09:00';

export const dashboardConfig = {
  code: 'SUCCESS',
  message: '대시보드 설정을 조회했습니다.',
  data: {
    stations: [
      { station_id: '102', station_name: '백령도', latitude: 37.97396, longitude: 124.71237, available: true, current_status: 'GOOD', forecast_status: 'GOOD' },
      { station_id: '112', station_name: '인천', latitude: 37.47772, longitude: 126.6249, available: true, current_status: 'GOOD', forecast_status: 'RETRY_SUCCESS' },
      { station_id: '201', station_name: '강화', latitude: 37.70739, longitude: 126.44634, available: true, current_status: 'GOOD', forecast_status: 'GOOD' },
    ],
    forecast_interval_options_h: [1, 3, 6, 12],
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
    fog_layer: gk2aFogLayer,
    meta: { request_id: 'req_20260918_000002', generated_at: OBSERVED_AT, partial: false },
  },
};

const stationSnapshots: Record<string, StationSnapshot> = {
  '102': {
    station: { station_id: '102', station_name: '백령도', latitude: 37.97396, longitude: 124.71237 },
    current: { visibility_km: 7.2, pm1_ug_m3: 9, pm25_ug_m3: 18, pm10_ug_m3: 31, temperature_c: 17, wind_direction_deg: 280, wind_direction_label: '서풍', wind_speed_m_s: 5.1, relative_humidity_pct: 76, temperature_dewpoint_spread_c: 3.4, weather_label: '구름많음', fog_grade_label: '옅은 안개' },
  },
  '112': {
    station: { station_id: '112', station_name: '인천', latitude: 37.47772, longitude: 126.6249 },
    current: { visibility_km: 4.8, pm1_ug_m3: 12, pm25_ug_m3: 27, pm10_ug_m3: 44, temperature_c: 18, wind_direction_deg: 315, wind_direction_label: '북서풍', wind_speed_m_s: 4.2, relative_humidity_pct: 81, temperature_dewpoint_spread_c: 2.8, weather_label: '안개', fog_grade_label: '옅은 안개' },
  },
  '201': {
    station: { station_id: '201', station_name: '강화', latitude: 37.70739, longitude: 126.44634 },
    current: { visibility_km: 3.6, pm1_ug_m3: 17, pm25_ug_m3: 34, pm10_ug_m3: 53, temperature_c: 16, wind_direction_deg: 260, wind_direction_label: '서풍', wind_speed_m_s: 2.8, relative_humidity_pct: 88, temperature_dewpoint_spread_c: 1.6, weather_label: '박무', fog_grade_label: '옅은 안개' },
  },
};

function validAt(horizonH: number) {
  return new Date(new Date(OBSERVED_AT).getTime() + horizonH * 3_600_000).toISOString();
}

function forecastPoint(snapshot: StationSnapshot, horizonH: number, slot: number) {
  const visibility = Math.max(0.2, snapshot.current.visibility_km - slot * 0.25);
  return {
    horizon_h: horizonH,
    valid_at: validAt(horizonH),
    visibility_pred_km: Number(visibility.toFixed(1)),
    pm1_pred_ug_m3: snapshot.current.pm1_ug_m3 + slot,
    pm25_pred_ug_m3: snapshot.current.pm25_ug_m3 + slot * 2,
    pm10_pred_ug_m3: snapshot.current.pm10_ug_m3 + slot * 2,
    temperature_c: snapshot.current.temperature_c + (slot < 3 ? slot : 1),
    wind_direction_deg: snapshot.current.wind_direction_deg,
    wind_direction_label: snapshot.current.wind_direction_label,
    wind_speed_m_s: Number((snapshot.current.wind_speed_m_s + slot * 0.2).toFixed(1)),
    weather_label: slot > 2 ? '흐림' : snapshot.current.weather_label,
    fog_grade_label: visibility < 0.5 ? '짙은 안개' : visibility < 2 ? '안개' : visibility <= 10 ? '옅은 안개' : '안개 없음',
    aqi: { value: 84 + slot * 8, display_level: slot > 2 ? 2 : 1, display_grade: slot > 2 ? '민감군 주의' : '양호', status: 'calculated' },
    status: 'fresh',
  };
}

export function dashboardFixture(stationId: string, forecastIntervalH: number) {
  const snapshot = stationSnapshots[stationId];
  if (!snapshot) return null;
  const forecastTimeline = [1, 2, 3, 4].map((slot) => forecastPoint(snapshot, forecastIntervalH * slot, slot));
  const minimumVisibility = Math.min(...forecastTimeline.map((point) => point.visibility_pred_km));
  const passed = minimumVisibility >= 1;

  return {
    code: 'PARTIAL_SUCCESS',
    message: '일부 자료가 재시도 후 수집되어 사용 가능한 결과를 반환했습니다.',
    data: {
      station: { station_id: snapshot.station.station_id, station_name: snapshot.station.station_name },
      request_context: {
        forecast_interval_h: forecastIntervalH,
        forecast_horizons_h: forecastTimeline.map((point) => point.horizon_h),
        mission_type: 'MARITIME_TRANSPORT',
      },
      current: {
        observed_at: OBSERVED_AT,
        ...snapshot.current,
        aqi: { value: 84, display_level: 1, display_grade: '양호', status: 'calculated' },
        status: 'fresh',
      },
      forecast_timeline: forecastTimeline,
      mission_evaluation: {
        mission_type: 'MARITIME_TRANSPORT',
        rule_version: 'maritime-transport-v1',
        evaluation_status: 'EVALUATED',
        passed,
        mission_grade: passed ? 'NORMAL' : 'RESTRICTED',
        factors: [{ metric: 'visibility_pred_km', actual: minimumVisibility, operator: '>=', threshold: 1, unit: 'km', required: true, passed }],
        reason_codes: [passed ? 'VISIBILITY_OK' : 'VISIBILITY_BELOW_MINIMUM'],
      },
      diagnosis: { fog_label: snapshot.current.fog_grade_label, pm_display_grade: '양호', summary: '안개 영향 우세 · 대기질은 보조 요인' },
      source_status: [
        { source: 'ASOS', status: 'fresh', observed_at: OBSERVED_AT },
        { source: 'AIRKOREA', status: 'fresh', observed_at: OBSERVED_AT },
        { source: 'BUOY', status: 'failed', observed_at: '2026-09-18T08:00:00+09:00' },
        { source: 'KMA', status: 'fresh', observed_at: OBSERVED_AT },
      ],
      api_status: {
        overall: { code: 'FAIL', label: 'Fail' },
        summary: { good: 3, delayed: 0, fail: 1 },
        sources: [
          { source: 'ASOS', display_name: '기상청 ASOS', code: 'GOOD', label: 'Good', attempts: 1 },
          { source: 'AIRKOREA', display_name: '에어코리아', code: 'GOOD', label: 'Good', attempts: 1 },
          { source: 'BUOY', display_name: '해양기상부이', code: 'FAIL', label: 'Fail', attempts: 3 },
          { source: 'KMA', display_name: '기상청 단기예보', code: 'GOOD', label: 'Good', attempts: 1 },
        ],
      },
      meta: { request_id: `req_20260918_${stationId}_${forecastIntervalH}`, generated_at: '2026-09-18T09:05:00+09:00', partial: true },
    },
  };
}
