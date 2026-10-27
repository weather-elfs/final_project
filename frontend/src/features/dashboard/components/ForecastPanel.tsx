import { airQualityByAqi, airQualityByParticles, fogGradeByVisibility, fogStageLabel } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData } from '../types';
import { DATA_SOURCE_LABELS } from '../stationStatus';
import CardLoadingOverlay from './CardLoadingOverlay';

const TARGET_LABELS: Record<string, string> = { visibility_km: '시정', pm25: 'PM2.5', pm10: 'PM10' };

const WEATHER_PATHS = {
  sun: 'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5',
  cloud: 'M6 18h11a4 4 0 0 0 .4-8A6 6 0 0 0 6 8a5 5 0 0 0 0 10Z',
  mist: 'M5 8h14M3 12h18M5 16h14',
  fog: 'M6 14h11a3 3 0 0 0 .3-6A5 5 0 0 0 7 7a3.5 3.5 0 0 0-1 7ZM4 18h16M7 21h10',
  rain: 'M6 14h11a3 3 0 0 0 .3-6A5 5 0 0 0 7 7a3.5 3.5 0 0 0-1 7ZM7 18l-1 3m6-3-1 3m6-3-1 3',
  snow: 'M6 14h11a3 3 0 0 0 .3-6A5 5 0 0 0 7 7a3.5 3.5 0 0 0-1 7ZM7 18v4m-2-2h4m7-2v4m-2-2h4',
  sleet: 'M6 14h11a3 3 0 0 0 .3-6A5 5 0 0 0 7 7a3.5 3.5 0 0 0-1 7ZM7 18l-1 3m10-3v4m-2-2h4',
};

function ForecastWeatherIcon({ label }: { label?: string }) {
  const kind = !label ? null : label.includes('안개') ? 'fog'
    : label.includes('박무') || label.includes('연무') ? 'mist'
    : label.includes('비') && label.includes('눈') ? 'sleet'
    : label.includes('눈') ? 'snow' : /비|소나기|빗방울/.test(label) ? 'rain'
    : label.includes('맑') ? 'sun' : /구름|흐림/.test(label) ? 'cloud' : null;
  return kind && <svg className="forecast-weather-icon" data-weather={kind} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={WEATHER_PATHS[kind]} /></svg>;
}

interface ForecastPanelProps {
  dashboard: DashboardData | null;
  requested: boolean;
  loading: boolean;
  available?: boolean;
}

export default function ForecastPanel({ dashboard, requested, loading, available = true }: ForecastPanelProps) {
  const forecast = dashboard?.forecastTimeline ?? [];
  const incomplete = forecast.filter((point) => point.status === 'degraded' || point.status === 'unavailable' || point.missingFeatures?.length);
  const reusedSources = new Set((dashboard?.sourceStatus ?? []).filter((source) => source.reason === 'PREVIOUS_OBSERVATION_USED' || source.reason === 'UPSTREAM_COMMUNICATION_FAILURE_REUSED').map((source) => source.source));
  const intervalH = dashboard?.requestContext?.forecastIntervalH ?? forecast[0]?.horizonH;
  const calculatedLowestVisibilityPoint = forecast.reduce<(typeof forecast)[number] | null>((lowest, point) => {
    if (point.visibilityPredKm == null) return lowest;
    if (lowest?.visibilityPredKm == null || point.visibilityPredKm < lowest.visibilityPredKm) return point;
    return lowest;
  }, null);
  const lowestVisibilityPoint = dashboard?.forecastSummary ?? calculatedLowestVisibilityPoint;

  const forecastTime = (value?: string) => formatKstTime(value).slice(0, 5);
  const stageAndLabel = (visibilityKm?: number | null) => {
    const grade = fogGradeByVisibility(visibilityKm);
    return grade.label === '안개 없음' ? grade.label : `${fogStageLabel(visibilityKm)} ${grade.label}`;
  };

  return (
    <section className="panel forecast-panel" aria-labelledby="forecast-title" aria-busy={loading}>
      {loading && <CardLoadingOverlay label="예측 결과 조회 중" />}
      <div className="panel-header forecast-header">
        <h2 id="forecast-title">시간대별 예측</h2>
        {forecast.length > 0 && (
          <p>{dashboard?.station?.stationName ?? '관측소'}({dashboard?.station?.stationId ?? '—'}) · {intervalH ?? '—'}시간 간격</p>
        )}
      </div>
      {!available ? (
        <div className="forecast-empty"><strong>예측 서비스 미제공</strong><span>현재 관측 자료는 확인할 수 있지만 예측 모델은 아직 연동되지 않았습니다.</span></div>
      ) : !requested ? (
        <div className="forecast-empty"><strong>예측 결과가 없습니다</strong><span>작전 환경을 설정한 뒤 시간대별 예측을 실행하세요.</span></div>
      ) : forecast.length === 0 ? (
        <div className="forecast-empty"><strong>예측 결과가 없습니다</strong><span>선택한 조건에 해당하는 예측 자료가 없습니다.</span></div>
      ) : (
        <div className="forecast-results">
          <div className="forecast-table-scroll">
            <table className="forecast-table">
              <caption>선택한 시간 간격의 기상 예측 비교</caption>
              <thead>
                <tr>
                  <th scope="col">시간</th>
                  {forecast.map((point) => <th key={`time-${point.horizonH}-${point.validAt}`} scope="col">+{point.horizonH}시간 {forecastTime(point.validAt)}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr className="forecast-weather-row"><th scope="row">날씨</th>{forecast.map((point) => <td key={`weather-${point.horizonH}`}><span className="forecast-weather-value"><ForecastWeatherIcon label={point.weatherLabel} /><span>{point.weatherLabel ?? '자료 없음'}</span></span></td>)}</tr>
                <tr><th scope="row">기온</th>{forecast.map((point) => <td key={`temperature-${point.horizonH}`}>{metric(point.temperatureC, '°C').replace(' °C', '°C')}</td>)}</tr>
                <tr className="forecast-wind-row"><th scope="row">풍향·풍속</th>{forecast.map((point) => <td className="forecast-cell-lines" key={`wind-${point.horizonH}`}><span>{point.windDirectionLabel ?? '자료 없음'}</span><span>{metric(point.windSpeedMS, 'm/s', 1)}</span></td>)}</tr>
                <tr className="forecast-visibility-row"><th scope="row">시정</th>{forecast.map((point) => <td key={`visibility-${point.horizonH}-${point.validAt}`}>{metric(point.visibilityPredKm, 'km', 1)}</td>)}</tr>
                <tr><th scope="row">안개 단계</th>{forecast.map((point) => {
                  const grade = fogGradeByVisibility(point.visibilityPredKm);
                  return <td className="forecast-fog-cell" key={`fog-${point.horizonH}-${point.validAt}`}>
                    <div className="forecast-grade">
                      <span className={`stage-criteria-badge forecast-stage-badge grade-tone-${grade.tone}`}>{fogStageLabel(point.visibilityPredKm)}</span>
                      {grade.label !== '안개 없음' && <span className="forecast-grade-description">{point.fogGradeLabel ?? grade.label}</span>}
                    </div>
                  </td>;
                })}</tr>
                <tr className="forecast-air-row"><th scope="row" title="모델 PM 예측값 기반 추정 AQI이며 공식 AQI가 아닙니다.">대기질</th>{forecast.map((point) => {
                  const air = point.aqi ? airQualityByAqi(point.aqi.status === 'calculated' ? point.aqi.value : null)
                    : airQualityByParticles(point.pm25PredUgM3, point.pm10PredUgM3);
                  return <td key={`air-${point.horizonH}`} title={`PM2.5 ${metric(point.pm25PredUgM3, '㎍/m³', 1)} · PM10 ${metric(point.pm10PredUgM3, '㎍/m³', 1)} · ${point.aqi ? 'AQI' : '추정 AQI'} ${air.value ?? '자료 없음'}`}>
                    <div className="forecast-grade">
                      <span className={`stage-criteria-badge forecast-stage-badge grade-tone-${air.tone}`}>{air.stage ? `${air.stage}/5단계` : '—/5단계'}</span>
                      <span className="forecast-grade-description">{air.label}</span>
                    </div>
                  </td>;
                })}</tr>
              </tbody>
            </table>
          </div>
          {lowestVisibilityPoint && (
            <p className="forecast-summary">종합 예측: +{lowestVisibilityPoint.horizonH}시간 시정 최저 {metric(lowestVisibilityPoint.visibilityPredKm, 'km', 1)} · {stageAndLabel(lowestVisibilityPoint.visibilityPredKm)}</p>
          )}
          {incomplete.length > 0 && <details className="forecast-input-details">
            <summary>예측 자료 상세</summary>
            {incomplete.map((point) => <p key={`input-${point.horizonH}`}>
              <strong>+{point.horizonH}시간 · {point.status === 'unavailable' ? '예측 불가' : point.status === 'degraded' && point.missingSources?.some((source) => reusedSources.has(source)) && !point.missingSources.some((source) => !reusedSources.has(source)) && !point.unavailableTargets?.length ? '이전 자료 사용' : point.status === 'degraded' ? '일부 입력 누락' : '일부 항목 결측'}</strong>
              {!!point.missingFeatures?.length && <span> · 모델 입력 {point.missingFeatures.length}개 결측</span>}
              {!!point.missingSources?.length && <span> · {point.missingSources.map((source) => DATA_SOURCE_LABELS[source] ?? source).join(' · ')}</span>}
              {!!point.unavailableTargets?.length && <span> · {point.unavailableTargets.map((target) => TARGET_LABELS[target] ?? target).join(' · ')} 예측 없음</span>}
            </p>)}
          </details>}
        </div>
      )}
    </section>
  );
}
