import { fogGradeByVisibility, fogStageLabel } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData } from '../types';
import { DATA_SOURCE_LABELS } from '../stationStatus';
import CardLoadingOverlay from './CardLoadingOverlay';

const TARGET_LABELS: Record<string, string> = { visibility_km: '시정', pm25: 'PM2.5', pm10: 'PM10' };

interface ForecastPanelProps {
  dashboard: DashboardData | null;
  requested: boolean;
  loading: boolean;
  available?: boolean;
}

export default function ForecastPanel({ dashboard, requested, loading, available = true }: ForecastPanelProps) {
  const forecast = dashboard?.forecastTimeline ?? [];
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
                {forecast.some((point) => point.status === 'degraded' || point.status === 'unavailable' || point.missingFeatures?.length) && <tr className="forecast-input-status"><th scope="row">입력 상태</th>{forecast.map((point) => <td key={`input-${point.horizonH}`}>
                  <strong>{point.status === 'unavailable' ? '예측 불가' : point.status === 'degraded' ? '일부 입력 누락' : point.missingFeatures?.length ? '일부 항목 결측' : '수신 완료'}</strong>
                  {!!point.missingFeatures?.length && <small>모델 입력 {point.missingFeatures.length}개 결측</small>}
                  {!!point.missingSources?.length && <small>{point.missingSources.map((source) => DATA_SOURCE_LABELS[source] ?? source).join(' · ')}</small>}
                  {!!point.unavailableTargets?.length && <small>{point.unavailableTargets.map((target) => TARGET_LABELS[target] ?? target).join(' · ')} 예측 없음</small>}
                </td>)}</tr>}
                <tr className="forecast-visibility-row"><th scope="row">시정</th>{forecast.map((point) => <td key={`visibility-${point.horizonH}-${point.validAt}`}>{metric(point.visibilityPredKm, 'km', 1)}</td>)}</tr>
                <tr><th scope="row">안개 단계</th>{forecast.map((point) => {
                  const grade = fogGradeByVisibility(point.visibilityPredKm);
                  return <td className="forecast-cell-lines" key={`fog-${point.horizonH}-${point.validAt}`}>
                    {grade.label !== '안개 없음' && <span>{fogStageLabel(point.visibilityPredKm)}</span>}
                    <span>{grade.label === '안개 없음' ? grade.label : point.fogGradeLabel ?? grade.label}</span>
                  </td>;
                })}</tr>
                <tr><th scope="row">PM2.5</th>{forecast.map((point) => <td key={`pm25-${point.horizonH}-${point.validAt}`}>{metric(point.pm25PredUgM3, '㎍/m³', 1)}</td>)}</tr>
                <tr><th scope="row">PM10</th>{forecast.map((point) => <td key={`pm10-${point.horizonH}-${point.validAt}`}>{metric(point.pm10PredUgM3, '㎍/m³', 1)}</td>)}</tr>
              </tbody>
            </table>
          </div>
          {lowestVisibilityPoint && (
            <p className="forecast-summary">종합 예측: +{lowestVisibilityPoint.horizonH}시간 시정 최저 {metric(lowestVisibilityPoint.visibilityPredKm, 'km', 1)} · {stageAndLabel(lowestVisibilityPoint.visibilityPredKm)}</p>
          )}
        </div>
      )}
    </section>
  );
}
