import { useEffect, useRef, useState } from 'react';

import { aqiGradeTone, fogGradeByVisibility } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData, SourceStatusDetail } from '../types';

const FOG_CRITERIA = [
  { stage: '1/6단계', label: '옅은 안개', range: '4–10 km', tone: 'green' },
  { stage: '2/6단계', label: '옅은 안개', range: '2–4 km', tone: 'yellow' },
  { stage: '3/6단계', label: '안개', range: '1–2 km', tone: 'orange' },
  { stage: '4/6단계', label: '안개', range: '500 m–1 km', tone: 'red' },
  { stage: '5/6단계', label: '짙은 안개', range: '200–500 m', tone: 'purple' },
  { stage: '6/6단계', label: '짙은 안개', range: '200 m 미만', tone: 'maroon' },
] as const;

const AIR_QUALITY_CRITERIA = [
  { stage: '1/5단계', label: '양호', range: 'AQI 0–100', tone: 'green' },
  { stage: '2/5단계', label: '민감군 주의', range: 'AQI 101–150', tone: 'orange' },
  { stage: '3/5단계', label: '나쁨', range: 'AQI 151–200', tone: 'red' },
  { stage: '4/5단계', label: '매우 나쁨', range: 'AQI 201–300', tone: 'purple' },
  { stage: '5/5단계', label: '위험', range: 'AQI 301 이상', tone: 'maroon' },
] as const;

const SOURCE_LABELS: Record<string, string> = {
  ASOS: '기상청 ASOS',
  AIRKOREA: '에어코리아',
  TIDE_OBSERVATORY: '해양부이',
  MARINE: '해양부이',
  PM1: '산림청 PM1',
  FOREST: '산림청 PM1',
  GK2A: '천리안',
};

const SOURCE_ORDER = ['ASOS', 'TIDE_OBSERVATORY', 'MARINE', 'PM1', 'FOREST', 'AIRKOREA', 'GK2A'];

function sourceStatusPresentation(status?: string) {
  const normalized = status?.toUpperCase();
  if (normalized === 'OK' || normalized === 'FRESH' || normalized === 'GOOD') {
    return { label: '정상', tone: 'good' } as const;
  }
  if (normalized === 'STALE' || normalized === 'DELAYED') {
    return { label: '지연', tone: 'delayed' } as const;
  }
  return { label: '오류', tone: 'error' } as const;
}

function elapsedLabel(minutes?: number | null) {
  if (minutes == null || !Number.isFinite(minutes)) return '수신 지연';
  if (minutes >= 1_440) return `${Math.floor(minutes / 1_440)}일째 미수신`;
  if (minutes >= 60) return `${Math.floor(minutes / 60)}시간째 미수신`;
  return `${Math.max(1, Math.floor(minutes))}분째 미수신`;
}

function sourceStatusMessage(source: SourceStatusDetail) {
  const presentation = sourceStatusPresentation(source.status);
  const observedTime = source.observedAt ? formatKstTime(source.observedAt) : '';
  if (presentation.tone === 'good') return observedTime ? `${observedTime} 수신` : '정상 수신';
  if (presentation.tone === 'delayed') {
    return `${elapsedLabel(source.ageMinutes)}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
  }

  const reason = source.reason?.toUpperCase() === 'TIMEOUT'
    ? '응답 시간 초과'
    : source.reason?.toUpperCase() === 'MISSING'
      ? '데이터 없음'
      : source.reason || '수신 오류';
  return `${reason}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
}

function weatherGlyph(label?: string) {
  if (label?.includes('비')) return '☂';
  if (label?.includes('맑')) return '☀';
  if (label?.includes('구름') || label?.includes('흐림')) return '☁';
  return '≡';
}

export default function VisibilitySummary({ dashboard, loading, onRefresh }: { dashboard: DashboardData | null; loading: boolean; onRefresh: () => void }) {
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const criteriaRootRef = useRef<HTMLDivElement>(null);
  const statusRootRef = useRef<HTMLDivElement>(null);
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
  const sourceStatuses = [...(dashboard?.sourceStatus ?? [])].sort((left, right) => {
    const leftOrder = SOURCE_ORDER.indexOf(left.source.toUpperCase());
    const rightOrder = SOURCE_ORDER.indexOf(right.source.toUpperCase());
    return (leftOrder < 0 ? SOURCE_ORDER.length : leftOrder) - (rightOrder < 0 ? SOURCE_ORDER.length : rightOrder);
  });

  useEffect(() => {
    if (!criteriaOpen) return undefined;

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!criteriaRootRef.current?.contains(event.target as Node)) setCriteriaOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setCriteriaOpen(false);
    };

    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [criteriaOpen]);

  useEffect(() => {
    if (!statusOpen) return undefined;

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!statusRootRef.current?.contains(event.target as Node)) setStatusOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setStatusOpen(false);
    };

    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [statusOpen]);

  return (
    <section className="panel current-weather-panel" aria-labelledby="current-weather-title">
      <div className="panel-header current-weather-header">
        <h2 id="current-weather-title">현재 기상</h2>
        <div className="observation-actions">
          <div className="observation-meta" ref={statusRootRef}>
            <div className="observation-status">
              <span className={`observation-status-dot status-${statusTone}`} aria-hidden="true" />
              <strong>데이터 상태 · {statusLabel}</strong>
              <button
                type="button"
                className="status-info"
                aria-label="출처별 데이터 상태 보기"
                aria-haspopup="dialog"
                aria-expanded={statusOpen}
                aria-controls="data-status-popover"
                onClick={() => {
                  setStatusOpen((open) => !open);
                  setCriteriaOpen(false);
                }}
              >
                <span aria-hidden="true">i</span>
              </button>
            </div>
            <span className="observation-time">갱신 시각 {formatKstTime(lastRefreshAt)} KST</span>
            {statusOpen && (
              <div
                id="data-status-popover"
                className="data-status-popover"
                role="dialog"
                aria-modal="false"
                aria-labelledby="data-status-title"
              >
                <div className="data-status-header">
                  <h3 id="data-status-title">출처별 데이터 상태</h3>
                  <span>현재 상태</span>
                </div>
                <div className="data-status-list">
                  {sourceStatuses.length > 0 ? sourceStatuses.map((source) => {
                    const presentation = sourceStatusPresentation(source.status);
                    return (
                      <div className="data-status-row" key={source.source}>
                        <i className={`status-${presentation.tone}`} aria-hidden="true" />
                        <strong>{SOURCE_LABELS[source.source.toUpperCase()] ?? source.source}</strong>
                        <b className={`status-${presentation.tone}`}>{presentation.label}</b>
                        <span>{sourceStatusMessage(source)}</span>
                      </div>
                    );
                  }) : <p className="data-status-empty">출처별 상태 정보가 없습니다.</p>}
                </div>
                <div className="data-status-footer">
                  <span>갱신 시각 {formatKstTime(lastRefreshAt)} KST</span>
                  <span>Esc로 닫기</span>
                </div>
              </div>
            )}
          </div>
          <button type="button" className="refresh-button" onClick={onRefresh} disabled={loading} aria-label="현재 관측 갱신"><img src="/figma-assets/refresh.svg" alt="" /></button>
        </div>
      </div>

      <div className="weather-metrics">
        <article><b>날씨</b><strong className={current?.weatherLabel ? undefined : 'weather-value-missing'}>{current?.weatherLabel?.includes('안개') ? <img className="weather-icon" src="/figma-assets/weather-fog.png" alt="" /> : <span className="weather-glyph" aria-hidden="true">{weatherGlyph(current?.weatherLabel)}</span>}{current?.weatherLabel ?? '자료 없음'}</strong><small>시정 {metric(current?.visibilityKm, 'km', 1)}</small></article>
        <article><b>기온</b><strong className={current?.temperatureC == null ? 'weather-value-missing' : undefined}>{current?.temperatureC == null ? '자료 없음' : <><span>{current.temperatureC.toFixed(0)}</span><span className="weather-unit">°C</span></>}</strong><small>현재 기온</small></article>
        <article><b>풍향</b><strong className={current?.windDirectionLabel ? undefined : 'weather-value-missing'}><img className="wind-arrow" src="/figma-assets/wind-direction.png" style={{ rotate: `${current?.windDirectionDeg ?? 0}deg` }} alt="" />{current?.windDirectionLabel ?? '자료 없음'}</strong><small>{current?.windDirectionDeg == null ? '방향 없음' : `${current.windDirectionDeg}°`}</small></article>
        <article><b>풍속</b><strong className={current?.windSpeedMS == null ? 'weather-value-missing' : undefined}>{current?.windSpeedMS == null ? '자료 없음' : <><span>{current.windSpeedMS.toFixed(1)}</span><span className="weather-unit"> m/s</span></>}</strong><small>{current?.windSpeedMS == null ? '자료 없음' : current.windSpeedMS <= 4.5 ? '약한 바람' : '보통 바람'}</small></article>
      </div>

      <div className="impact-title" ref={criteriaRootRef}>
        <h3>시정 영향 요인</h3>
        <button
          type="button"
          className="criteria-info-button"
          aria-label="시정 영향 단계 기준 보기"
          aria-haspopup="dialog"
          aria-expanded={criteriaOpen}
          aria-controls="stage-criteria-popover"
          onClick={() => {
            setCriteriaOpen((open) => !open);
            setStatusOpen(false);
          }}
        >
          <span aria-hidden="true">i</span>
        </button>
        {criteriaOpen && (
          <div
            id="stage-criteria-popover"
            className="stage-criteria-popover"
            role="dialog"
            aria-modal="false"
            aria-labelledby="stage-criteria-title"
          >
            <div className="stage-criteria-header">
              <h4 id="stage-criteria-title">시정 영향 단계 기준</h4>
              <span>숫자가 클수록 위험</span>
            </div>

            <section className="stage-criteria-section" aria-labelledby="fog-criteria-title">
              <div className="stage-criteria-section-title">
                <h5 id="fog-criteria-title">안개 위험 단계 · 6등급</h5>
              </div>
              <div className="stage-criteria-items fog-criteria-items">
                {FOG_CRITERIA.map((item) => (
                  <div className="stage-criteria-item" key={item.stage}>
                    <b className={`stage-criteria-badge grade-tone-${item.tone}`}>{item.stage}</b>
                    <span>{item.label}<small>{item.range}</small></span>
                  </div>
                ))}
              </div>
            </section>

            <section className="stage-criteria-section" aria-labelledby="air-quality-criteria-title">
              <div className="stage-criteria-section-title">
                <h5 id="air-quality-criteria-title">대기질 단계 · 5등급</h5>
                <span>AirNow AQI · 색각 보조</span>
              </div>
              <div className="stage-criteria-items air-quality-criteria-items">
                {AIR_QUALITY_CRITERIA.map((item) => (
                  <div className="stage-criteria-item" key={item.stage}>
                    <b className={`stage-criteria-badge grade-tone-${item.tone}`}>{item.stage}</b>
                    <span>{item.label}<small>{item.range}</small></span>
                  </div>
                ))}
              </div>
            </section>

            <p className="stage-criteria-note">상태명은 옅은 안개·안개·짙은 안개로 통일한 프로젝트 UI 기준</p>
          </div>
        )}
      </div>
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
