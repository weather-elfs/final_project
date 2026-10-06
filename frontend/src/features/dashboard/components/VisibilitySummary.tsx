import { aqiGradeTone, fogGradeByVisibility } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData } from '../types';

function weatherGlyph(label?: string) {
  if (label?.includes('비')) return '☂';
  if (label?.includes('맑')) return '☀';
  if (label?.includes('구름') || label?.includes('흐림')) return '☁';
  return '≡';
}

export default function VisibilitySummary({ dashboard, loading, onRefresh }: { dashboard: DashboardData | null; loading: boolean; onRefresh: () => void }) {
  const current = dashboard?.current;
  const diagnosis = dashboard?.diagnosis;
  const lastRefreshAt = dashboard?.meta?.generatedAt ?? current?.observedAt;
  const errors = dashboard?.apiStatus?.summary?.fail ?? 0;
  const delayed = dashboard?.apiStatus?.summary?.delayed ?? 0;
  const statusLabel = errors ? `오류 ${errors}` : delayed ? `지연 ${delayed}` : '정상';
  const statusTone = errors ? 'error' : delayed ? 'delayed' : 'good';
  const fogGrade = fogGradeByVisibility(current?.visibilityKm);
  const aqiLabel = current?.aqi?.displayGrade ?? diagnosis?.pmDisplayGrade ?? '판단 대기';
  const fogDetail = fogGrade.stage ? `${fogGrade.label} · ${fogGrade.rangeLabel}` : fogGrade.label;

  return (
    <section className="panel current-weather-panel" aria-labelledby="current-weather-title">
      <div className="panel-header current-weather-header">
        <h2 id="current-weather-title">현재 기상</h2>
        <div className="observation-actions">
          <div className="observation-meta">
            <div className="observation-status"><strong><span className={`status-${statusTone}`}>●</span> 데이터 상태 · {statusLabel}</strong><span className="status-info">ⓘ</span></div>
            <span className="observation-time">갱신 시각 {formatKstTime(lastRefreshAt)} KST</span>
          </div>
          <button type="button" className="refresh-button" onClick={onRefresh} disabled={loading} aria-label="현재 관측 갱신"><img src="/figma-assets/refresh.svg" alt="" /></button>
        </div>
      </div>

      <div className="weather-metrics">
        <article><b>날씨</b><strong>{current?.weatherLabel?.includes('안개') ? <img className="weather-icon" src="/figma-assets/weather-fog.png" alt="" /> : <span className="weather-glyph" aria-hidden="true">{weatherGlyph(current?.weatherLabel)}</span>}{current?.weatherLabel ?? '자료 없음'}</strong><small>시정 {metric(current?.visibilityKm, 'km', 1)}</small></article>
        <article><b>기온</b><strong>{current?.temperatureC == null ? '자료 없음' : <><span>{current.temperatureC.toFixed(0)}</span><span className="weather-unit">°C</span></>}</strong><small>현재 기온</small></article>
        <article><b>풍향</b><strong><img className="wind-arrow" src="/figma-assets/wind-direction.png" style={{ rotate: `${current?.windDirectionDeg ?? 0}deg` }} alt="" />{current?.windDirectionLabel ?? '자료 없음'}</strong><small>{current?.windDirectionDeg == null ? '방향 없음' : `${current.windDirectionDeg}°`}</small></article>
        <article><b>풍속</b><strong>{current?.windSpeedMS == null ? '자료 없음' : <><span>{current.windSpeedMS.toFixed(1)}</span><span className="weather-unit"> m/s</span></>}</strong><small>{current?.windSpeedMS == null ? '자료 없음' : current.windSpeedMS <= 4.5 ? '약한 바람' : '보통 바람'}</small></article>
      </div>

      <div className="impact-title"><h3>시정 영향 요인 ⓘ</h3></div>
      <div className="impact-grid">
        <article><div><strong>안개</strong><span>{fogDetail}</span></div><b className={`factor-stage grade-tone-${fogGrade.tone}`}>{fogGrade.stage ? `${fogGrade.stage}/6단계` : '—/6단계'}</b></article>
        <article><div><strong>대기질</strong><span>AQI {current?.aqi?.value ?? '—'} · {aqiLabel}</span></div><b className={`factor-stage grade-tone-${aqiGradeTone(aqiLabel)}`}>{current?.aqi?.displayLevel ?? '—'}/5단계</b></article>
      </div>
      <p className="diagnosis-summary">종합 추정: {diagnosis?.summary ?? '데이터 대기'}</p>

      <h3 className="related-title">시정 관련 관측 지표</h3>
      <div className="metric-grid">
        <div><span>PM2.5</span><strong>{metric(current?.pm25UgM3, 'µg/m³')}</strong></div>
        <div><span>PM10</span><strong>{metric(current?.pm10UgM3, 'µg/m³')}</strong></div>
        <div><span>상대습도</span><strong>{metric(current?.relativeHumidityPct, '%')}</strong></div>
        <div><span>기온−이슬점</span><strong>{metric(current?.temperatureDewpointSpreadC, '°C', 1)}</strong></div>
      </div>
    </section>
  );
}
