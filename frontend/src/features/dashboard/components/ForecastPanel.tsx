import { fogGradeByVisibility } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData } from '../types';

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
    return `${grade.stage ? `${grade.stage}/6단계` : '—/6단계'} ${grade.label}`;
  };

  return (
    <section className="panel forecast-panel" aria-labelledby="forecast-title">
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
      ) : loading ? (
        <div className="forecast-empty" role="status"><strong>예측 결과 조회 중</strong><span>선택한 조건의 4개 시점을 불러오고 있습니다.</span></div>
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
                <tr className="forecast-visibility-row"><th scope="row">시정</th>{forecast.map((point) => <td key={`visibility-${point.horizonH}-${point.validAt}`}>{metric(point.visibilityPredKm, 'km', 1)}</td>)}</tr>
                <tr><th scope="row">안개 단계</th>{forecast.map((point) => {
                  const grade = fogGradeByVisibility(point.visibilityPredKm);
                  return <td className="forecast-cell-lines" key={`fog-${point.horizonH}-${point.validAt}`}><span>{grade.stage ? `${grade.stage}/6단계` : '—/6단계'}</span><span>{point.fogGradeLabel ?? grade.label}</span></td>;
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
