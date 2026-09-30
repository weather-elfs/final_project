import { isFiniteNumber, metric } from '../formatters';
import type { DashboardData, ForecastPoint } from '../types';

interface TrendChartProps {
  history: NonNullable<DashboardData['history']>;
  forecast: ForecastPoint[];
  threshold: number;
}

function TrendChart({ history, forecast, threshold }: TrendChartProps) {
  const observed = history.map((item) => item.visibilityKm).filter((value): value is number => Number.isFinite(value));
  const predicted = forecast.map((item) => item.visibilityPredKm).filter((value): value is number => Number.isFinite(value));
  const values = [...observed, ...predicted, threshold].filter(Number.isFinite);
  const ceiling = Math.max(...values, 1) * 1.18;
  const x = (index: number, count: number) => 28 + (index / Math.max(count - 1, 1)) * 544;
  const y = (value: number) => 142 - (value / ceiling) * 112;
  const observedPoints = observed.map((value, index) => `${x(index, observed.length + 1)},${y(value)}`).join(' ');
  const predictedPoints = predicted.map((value, index) => `${x(index + observed.length, observed.length + predicted.length)},${y(value)}`).join(' ');

  return (
    <svg className="trend-chart" viewBox="0 0 600 175" role="img" aria-label="과거 관측과 예측 시정 추이">
      <line x1="28" x2="572" y1={y(threshold)} y2={y(threshold)} className="threshold-line" />
      {[30, 86, 142].map((yPos) => <line key={yPos} x1="28" x2="572" y1={yPos} y2={yPos} className="grid-line" />)}
      {observedPoints && <polyline points={observedPoints} className="observed-line" />}
      {predictedPoints && <polyline points={predictedPoints} className="predicted-line" />}
      <text x="28" y="166">−3시간</text><text x="286" y="166" textAnchor="middle">현재</text><text x="572" y="166" textAnchor="end">예측</text>
    </svg>
  );
}

export default function ForecastPanel({ dashboard, horizonH, minimumVisibilityKm }: { dashboard: DashboardData | null; horizonH: number; minimumVisibilityKm: number }) {
  const current = dashboard?.current;
  const future = dashboard?.selectedForecast;
  const evaluation = dashboard?.missionEvaluation;
  const factor = evaluation?.factors?.[0];
  const currentVisibility = current?.visibilityKm;
  const futureVisibility = future?.visibilityPredKm;
  const delta = isFiniteNumber(currentVisibility) && isFiniteNumber(futureVisibility)
    ? futureVisibility - currentVisibility : null;

  return (
    <section className="panel forecast-panel" aria-labelledby="forecast-title">
      <div className="panel-header">
        <div><h2 id="forecast-title">시정 추이 · 임무 판정</h2><p>과거 3시간 관측과 선택 예측시간</p></div>
        <span className={`mission-grade grade-${evaluation?.missionGrade?.toLowerCase()}`}>{evaluation?.missionGrade ?? '대기'}</span>
      </div>
      <div className="forecast-summary">
        <div><strong>{metric(future?.visibilityPredKm, 'km', 1)}</strong><span>예상 시정</span></div>
        <p>현재 {metric(current?.visibilityKm, 'km', 1)} → +{horizonH}시간<br /><b>{delta === null ? '변화량 판단 불가' : `${Math.abs(delta).toFixed(1)} km ${delta < 0 ? '감소' : '증가'} 예상`}</b></p>
      </div>
      <TrendChart history={dashboard?.history ?? []} forecast={dashboard?.forecastTimeline ?? []} threshold={minimumVisibilityKm} />
      <div className="chart-legend"><span><i className="observed" />관측</span><span><i className="predicted" />예측</span></div>
      <div className="evaluation-box">
        <div><span>현재 판정</span><strong>{evaluation?.evaluationStatus === 'NOT_EVALUABLE' ? '판정 불가' : evaluation?.passed ? '임무 기준 충족' : '임무 기준 미달'}</strong></div>
        <div><span>판정 근거</span><strong>{factor ? `${factor.actual} ${factor.unit} ${factor.operator} ${factor.threshold} ${factor.unit}` : '근거 대기'}</strong></div>
        <div><span>규칙 버전</span><strong>{evaluation?.ruleVersion ?? '미정'}</strong></div>
      </div>
    </section>
  );
}
