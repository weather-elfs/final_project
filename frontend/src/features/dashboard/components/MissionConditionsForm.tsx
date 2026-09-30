import type { DashboardConfig, MissionValue, MissionValueKey, MissionValues } from '../types';

interface MissionConditionsFormProps {
  config: DashboardConfig;
  values: MissionValues;
  loading: boolean;
  onChange: (key: MissionValueKey, value: MissionValue) => void;
  onSubmit: () => void;
}

export default function MissionConditionsForm({ config, values, loading, onChange, onSubmit }: MissionConditionsFormProps) {
  return (
    <section className="panel mission-panel" aria-labelledby="mission-title">
      <div className="panel-header"><div><h2 id="mission-title">임무 조건</h2><p>조건 변경 시 통합 대시보드 API 재조회</p></div></div>
      <form className="mission-form" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <label htmlFor="mission-station">대상 해역
          <select id="mission-station" value={values.stationId} onChange={(event) => onChange('stationId', event.target.value)} disabled={loading}>
            {config.stations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}
          </select>
        </label>
        <div className="form-row">
          <label htmlFor="mission-type">임무 유형
            <select id="mission-type" value={values.missionType} onChange={(event) => onChange('missionType', event.target.value)} disabled={loading}>
              {config.missionTypes.map((mission) => <option key={mission.missionType} value={mission.missionType}>{mission.displayName}</option>)}
            </select>
          </label>
          <label htmlFor="forecast-horizon">예측 시점
            <select id="forecast-horizon" value={values.horizonH} onChange={(event) => onChange('horizonH', Number(event.target.value))} disabled={loading}>
              {config.forecastHorizonsH.map((hour) => <option key={hour} value={hour}>+{hour}시간</option>)}
            </select>
          </label>
        </div>
        <label htmlFor="minimum-visibility">최소 시정 기준 (km)
          <input id="minimum-visibility" type="number" min="0.1" max="50" step="0.1" value={values.minimumVisibilityKm} onChange={(event) => onChange('minimumVisibilityKm', Number(event.target.value))} disabled={loading} />
        </label>
        <div className="mission-actions"><small>임무 조건은 서버의 규칙 엔진에서 판정됩니다.</small><button type="submit" disabled={loading}>{loading ? '조회 중…' : '예측 결과 보기'}</button></div>
      </form>
    </section>
  );
}
