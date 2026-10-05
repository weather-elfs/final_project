import { fogStageLabel } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData } from '../types';

interface ForecastPanelProps {
  dashboard: DashboardData | null;
  requested: boolean;
  loading: boolean;
}

export default function ForecastPanel({ dashboard, requested, loading }: ForecastPanelProps) {
  const forecast = dashboard?.forecastTimeline ?? [];
  const intervalH = forecast[0]?.horizonH;
  const lowestVisibilityPoint = forecast.reduce<(typeof forecast)[number] | null>((lowest, point) => {
    if (point.visibilityPredKm == null) return lowest;
    if (lowest?.visibilityPredKm == null || point.visibilityPredKm < lowest.visibilityPredKm) return point;
    return lowest;
  }, null);

  const forecastTime = (value?: string) => formatKstTime(value).slice(0, 5);
  const temperature = (value?: number | null) => value == null ? '—' : `${value.toFixed(0)}°C`;
  const stageAndLabel = (label?: string) => `${fogStageLabel(label)} ${label ?? '판단 대기'}`;
  const airQuality = (point: (typeof forecast)[number]) => {
    const level = point.aqi?.displayLevel == null ? '—' : point.aqi.displayLevel;
    return `${level}/5단계 ${point.aqi?.displayGrade ?? '판단 대기'}`;
  };

  return (
    <section className="panel forecast-panel" aria-labelledby="forecast-title">
      <div className="panel-header forecast-header">
        <h2 id="forecast-title">시간대별 예측</h2>
        {forecast.length > 0 && (
          <p>{dashboard?.station?.stationName ?? '관측소'}({dashboard?.station?.stationId ?? '—'}) · {intervalH ?? '—'}시간 간격</p>
        )}
      </div>
      {!requested ? (
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
                <tr><th scope="row">날씨</th>{forecast.map((point) => <td key={`weather-${point.horizonH}-${point.validAt}`}>{point.weatherLabel ?? '자료 없음'}</td>)}</tr>
                <tr><th scope="row">기온</th>{forecast.map((point) => <td key={`temperature-${point.horizonH}-${point.validAt}`}>{temperature(point.temperatureC)}</td>)}</tr>
                <tr><th scope="row">풍향·풍속</th>{forecast.map((point) => <td className="forecast-cell-lines" key={`wind-${point.horizonH}-${point.validAt}`}><span>{point.windDirectionLabel ?? '자료 없음'}</span><span>{metric(point.windSpeedMS, 'm/s', 1)}</span></td>)}</tr>
                <tr className="forecast-visibility-row"><th scope="row">시정</th>{forecast.map((point) => <td key={`visibility-${point.horizonH}-${point.validAt}`}>{metric(point.visibilityPredKm, 'km', 1)}</td>)}</tr>
                <tr><th scope="row">안개 단계</th>{forecast.map((point) => <td className="forecast-cell-lines" key={`fog-${point.horizonH}-${point.validAt}`}><span>{fogStageLabel(point.fogGradeLabel)}</span><span>{point.fogGradeLabel ?? '판단 대기'}</span></td>)}</tr>
                <tr><th scope="row">대기질</th>{forecast.map((point) => <td className="forecast-cell-lines" key={`aqi-${point.horizonH}-${point.validAt}`}><span>{airQuality(point).split(' ')[0]}</span><span>{airQuality(point).split(' ').slice(1).join(' ')}</span></td>)}</tr>
              </tbody>
            </table>
          </div>
          {lowestVisibilityPoint && (
            <p className="forecast-summary">종합 예측: +{lowestVisibilityPoint.horizonH}시간 시정 최저 {metric(lowestVisibilityPoint.visibilityPredKm, 'km', 1)} · {stageAndLabel(lowestVisibilityPoint.fogGradeLabel)}</p>
          )}
        </div>
      )}
    </section>
  );
}
