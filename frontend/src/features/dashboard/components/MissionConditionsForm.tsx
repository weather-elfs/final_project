import { formatKstTime } from '../formatters';
import type { DashboardConfig, MissionValue, MissionValueKey, MissionValues } from '../types';

interface MissionConditionsFormProps {
  config: DashboardConfig;
  values: MissionValues;
  selectedStationName?: string;
  currentTime?: string;
  forecastBaseTime?: string;
  loading: boolean;
  submitting?: boolean;
  onChange: (key: MissionValueKey, value: MissionValue) => void;
  onSubmit: () => void;
}

export default function MissionConditionsForm({ config, values, selectedStationName, currentTime, forecastBaseTime, loading, submitting = false, onChange, onSubmit }: MissionConditionsFormProps) {
  const ready = Boolean(values.stationId && values.forecastIntervalH && values.missionType);
  const interval = values.forecastIntervalH;
  const horizons = interval ? [1, 2, 3, 4].map((slot) => slot * interval) : [];

  return (
    <section className="panel mission-panel" aria-labelledby="mission-title">
      <div className="panel-header"><div><h2 id="mission-title">작전 환경</h2><p>해역·임무 유형·예측 간격을 설정해 시간대별 변화를 조회</p></div></div>
      <form className="mission-form" onSubmit={(event) => { event.preventDefault(); if (ready) onSubmit(); }}>
        <div className="form-row">
          <label htmlFor="mission-station">대상 해역
            <select id="mission-station" value={values.stationId} disabled title="대상 해역은 지도에서 ASOS 관측소를 선택하면 변경됩니다.">
              <option value="">지도에서 ASOS를 선택하세요</option>
              {values.stationId && !config.stations.some((station) => station.id === values.stationId) && <option value={values.stationId}>{selectedStationName ?? values.stationId}</option>}
              {config.stations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}
            </select>
          </label>
          <label htmlFor="forecast-interval">예측 간격
            <select id="forecast-interval" value={values.forecastIntervalH} onChange={(event) => onChange('forecastIntervalH', event.target.value ? Number(event.target.value) : '')} disabled={loading}>
              <option value="">예측 간격을 선택하세요</option>
              {config.forecastIntervalOptionsH.map((hour) => <option key={hour} value={hour}>{hour}시간 간격</option>)}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label htmlFor="mission-type">임무 유형
            <select id="mission-type" value={values.missionType} onChange={(event) => onChange('missionType', event.target.value)} disabled={loading}>
              <option value="">임무를 선택하세요</option>
              {config.missionTypes.map((mission) => <option key={mission.missionType} value={mission.missionType}>{mission.displayName}</option>)}
            </select>
          </label>
          <label htmlFor="current-time">현재 시각
            <input id="current-time" value={`${formatKstTime(currentTime)} KST`} readOnly />
          </label>
        </div>
        <label htmlFor="forecast-preview">표시 시점
          <div id="forecast-preview" className="forecast-preview"><span>{horizons.length ? horizons.map((hour) => `+${hour}h`).join(' · ') : '예측 간격을 선택하면 표시됩니다.'}</span><b>{horizons.length ? '4개 시점' : '선택 전'}</b></div>
        </label>
        <div className="mission-actions"><small>예측 기준 시각 {formatKstTime(forecastBaseTime)} KST · 관측 기준으로 선택한 간격의 4개 시점을 비교합니다.</small><button type="submit" disabled={loading || !ready}>{submitting ? '조회 중…' : '시간대별 예측 보기'}</button></div>
      </form>
    </section>
  );
}
