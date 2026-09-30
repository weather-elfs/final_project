import { formatKst, isFiniteNumber, metric, statusLabels } from '../formatters';
import { aqiGradeTone, displayAqiGrade, fogGradeTone } from '../gradeTones';
import type { DashboardData } from '../types';

const SOURCE_LABELS: Record<string, string> = {
  ASOS: 'ASOS',
  BUOY: '해양부이',
  AIRKOREA: '에어코리아',
  SATELLITE: '천리안',
};

const SOURCE_TONES: Record<string, string> = {
  ASOS: 'blue', BUOY: 'blue', AIRKOREA: 'yellow', SATELLITE: 'red',
};

export default function VisibilitySummary({ dashboard, horizonH }: { dashboard: DashboardData | null; horizonH: number }) {
  const { current, selectedForecast: future, diagnosis, sourceStatus = [], station, meta } = dashboard ?? {};
  const currentVisibility = current?.visibilityKm;
  const futureVisibility = future?.visibilityPredKm;
  const delta = isFiniteNumber(currentVisibility) && isFiniteNumber(futureVisibility)
    ? futureVisibility - currentVisibility : null;
  const fogLabel = diagnosis?.fogLabel ?? '판단 대기';
  const aqiLabel = displayAqiGrade(diagnosis?.pmDisplayGrade);

  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-title">
      <div className="panel-header evidence-header">
        <div><h2 id="evidence-title">현재 / 예측 시정</h2><p>{station?.stationName ?? '관측소 선택 대기'}</p></div>
        <span className="evidence-delay">{meta?.partial ? '일부 자료 지연' : '자료 정상'}</span>
      </div>

      <div className="comparison-grid">
        <article><span>현재 관측 · {formatKst(current?.observedAt)}</span><strong>{metric(currentVisibility, 'km', 1)}</strong><small>{current?.status ? statusLabels[current.status] ?? current.status : '대기'}</small></article>
        <article><span>+{horizonH}시간 예측 · {formatKst(future?.validAt)}</span><strong>{metric(futureVisibility, 'km', 1)}</strong><small>{future?.status ? statusLabels[future.status] ?? future.status : '대기'}</small></article>
        <article className={delta !== null && delta < 0 ? 'negative' : ''}><span>변화량 (예측−현재)</span><strong>{delta === null ? '판단 불가' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)} km`}</strong><small>{delta === null ? '자료 확인 필요' : delta < 0 ? '시정 감소 예상' : '시정 유지·개선'}</small></article>
      </div>

      <div className="diagnosis-heading">
        <h3>저시정 원인 진단</h3>
        <span>관측 근거와 모델 영향도를 분리해 판단</span>
      </div>
      <div className="diagnosis-row">
        <article>
          <div><strong>안개 가능성</strong><span>현재·예측 자료 기반 판정</span></div>
          <b className={`diagnosis-grade grade-tone-${fogGradeTone(fogLabel)}`}>{fogLabel}</b>
        </article>
        <article>
          <div><strong>미세먼지 영향</strong><span>PM2.5 {metric(current?.pm25UgM3, 'µg/m³')}</span></div>
          <b className={`diagnosis-grade grade-tone-${aqiGradeTone(diagnosis?.pmDisplayGrade)}`}>{aqiLabel}</b>
        </article>
      </div>
      <p className="diagnosis-summary">종합 추정: {diagnosis?.summary ?? '데이터 대기'}</p>

      <div className="related-heading">
        <h3>대기질 · 안개 관련 요소</h3>
        <span>확정 원인이 아닌 현재 관측·예측 기반 추정</span>
      </div>
      <div className="metric-grid">
        <div><span>PM2.5</span><strong>{metric(current?.pm25UgM3, 'µg/m³')}</strong></div>
        <div><span>PM10</span><strong>{metric(current?.pm10UgM3, 'µg/m³')}</strong></div>
        <div><span>상대습도</span><strong>{metric(current?.relativeHumidityPct, '%')}</strong></div>
        <div><span>기온−이슬점</span><strong>{metric(current?.temperatureDewpointSpreadC, '°C', 1)}</strong></div>
      </div>
      <div className="source-strip">
        {sourceStatus.map((source) => <span key={source.source}><i className={`source-dot-${SOURCE_TONES[source.source] ?? 'gray'}`} />{SOURCE_LABELS[source.source] ?? source.source}</span>)}
      </div>
    </section>
  );
}
