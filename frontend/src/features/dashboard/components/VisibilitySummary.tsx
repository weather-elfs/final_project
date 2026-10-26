import { useEffect, useRef, useState } from 'react';

import { AIR_QUALITY_CRITERIA, airQualityByAqi, airQualityByParticles, fogGradeByVisibility, fogStageLabel } from '../gradeTones';
import { formatKstTime, metric } from '../formatters';
import type { DashboardData, SourceStatusDetail } from '../types';
import { DATA_SOURCE_LABELS, SOURCE_FAILURE_MESSAGES } from '../stationStatus';
import CardLoadingOverlay from './CardLoadingOverlay';

const FOG_CRITERIA = [
  { stage: '안개 없음', label: '시정 양호', range: '10 km 이상', tone: 'sky' },
  { stage: '1/6단계', label: '옅은 안개', range: '4–10 km 미만', tone: 'green' },
  { stage: '2/6단계', label: '옅은 안개', range: '2–4 km', tone: 'yellow' },
  { stage: '3/6단계', label: '안개', range: '1–2 km', tone: 'orange' },
  { stage: '4/6단계', label: '안개', range: '500 m–1 km', tone: 'red' },
  { stage: '5/6단계', label: '짙은 안개', range: '200–500 m', tone: 'purple' },
  { stage: '6/6단계', label: '짙은 안개', range: '200 m 미만', tone: 'maroon' },
] as const;

const SOURCE_LABELS: Record<string, string> = {
  ...DATA_SOURCE_LABELS,
  ASOS: '기상청 ASOS',
  AIRKOREA: '에어코리아',
  TIDE_OBSERVATORY: '국립해양조사원',
  MARINE: '해양부이',
  PM1: '산림청 PM1',
  FOREST: '산림청 PM1',
  GK2A: '천리안',
};

const SOURCE_ORDER = ['ASOS', 'TIDE_OBSERVATORY', 'MARINE', 'PM1', 'FOREST', 'AIRKOREA', 'GK2A'];

function sourceStatusPresentation(status?: string) {
  const normalized = status?.toUpperCase();
  if (normalized === 'PARTIAL') return { label: '일부 누락', tone: 'delayed' } as const;
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

export function sourceStatusMessage(source: SourceStatusDetail) {
  const presentation = sourceStatusPresentation(source.status);
  if (source.source.toUpperCase().endsWith('_FORECAST')) {
    const times = [source.issuedAt ? `발표 ${formatKstTime(source.issuedAt)}` : '', source.collectedAt ? `수집 ${formatKstTime(source.collectedAt)}` : ''].filter(Boolean).join(' · ');
    return `${presentation.tone === 'good' ? '예보 수신' : SOURCE_FAILURE_MESSAGES[source.reason ?? ''] ?? '예보 일부 누락'}${times ? ` · ${times}` : ''}`;
  }
  const observedTime = source.observedAt ? formatKstTime(source.observedAt) : '';
  if (source.status.toUpperCase() === 'PARTIAL') return `${SOURCE_FAILURE_MESSAGES[source.reason ?? ''] ?? '일부 관측값 누락'}${observedTime ? ` · 관측 ${observedTime}` : ''}`;
  if (presentation.tone === 'good') return observedTime ? `${observedTime} 수신` : '정상 수신';
  if (presentation.tone === 'delayed') {
    return `${elapsedLabel(source.ageMinutes)}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
  }

  const reason = SOURCE_FAILURE_MESSAGES[source.reason ?? ''] ?? (source.reason?.toUpperCase() === 'TIMEOUT'
    ? '응답 시간 초과'
    : source.reason?.toUpperCase() === 'MISSING'
      ? '데이터 없음'
      : source.reason || '수신 오류');
  return `${reason}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
}

function weatherGlyph(label?: string) {
  if (label?.includes('비')) return '☂';
  if (label?.includes('맑')) return '☀';
  if (label?.includes('구름') || label?.includes('흐림')) return '☁';
  return '≡';
}

export default function VisibilitySummary({ dashboard, loading, onRefresh, retryingSource }: { dashboard: DashboardData | null; loading: boolean; onRefresh: () => void; retryingSource?: string | null }) {
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const criteriaRootRef = useRef<HTMLDivElement>(null);
  const statusRootRef = useRef<HTMLDivElement>(null);
  const current = dashboard?.current;
  const diagnosis = dashboard?.diagnosis;
  const lastRefreshAt = dashboard?.meta?.generatedAt;
  const errors = dashboard?.apiStatus?.summary?.fail ?? 0;
  const delayed = dashboard?.apiStatus?.summary?.delayed ?? 0;
  const statusLabel = !dashboard ? loading ? '조회 중' : '자료 없음' : errors ? `일부 누락 ${errors}` : delayed ? `지연 ${delayed}` : '정상';
  const statusTone = !dashboard ? 'delayed' : errors ? 'error' : delayed ? 'delayed' : 'good';
  const fogGrade = fogGradeByVisibility(current?.visibilityKm);
  const serverAqi = current?.aqi;
  const usesNowcast = serverAqi?.basis === 'NOWCAST_CURRENT';
  const airQuality = usesNowcast
    ? airQualityByAqi(serverAqi.status === 'calculated' ? serverAqi.value : null)
    : airQualityByParticles(current?.pm25UgM3, current?.pm10UgM3);
  const fogDetail = fogGrade.rangeLabel === '자료 없음' ? fogGrade.label : `${fogGrade.label} · ${fogGrade.rangeLabel}`;
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
    <section className="panel current-weather-panel" aria-labelledby="current-weather-title" aria-busy={loading}>
      {loading && <CardLoadingOverlay label="현재 기상 조회 중" />}
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
                disabled={loading}
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
            {statusOpen && !loading && (
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
          <button type="button" className="refresh-button" onClick={onRefresh} disabled={loading || Boolean(retryingSource)} aria-label="현재 관측 갱신"><img src="/figma-assets/refresh.svg" alt="" /></button>
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
          disabled={loading}
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
        {criteriaOpen && !loading && (
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
                <span>{usesNowcast ? '서버 NowCast AQI · 색각 보조' : 'PM 기반 AQI 추정 · 색각 보조'}</span>
              </div>
              <div className="stage-criteria-items air-quality-criteria-items">
                {AIR_QUALITY_CRITERIA.map((item) => (
                  <div className="stage-criteria-item" key={item.stage}>
                    <b className={`stage-criteria-badge grade-tone-${item.tone}`}>{item.stage}/5단계</b>
                    <span>{item.label}<small>{item.range}</small></span>
                  </div>
                ))}
              </div>
            </section>

            <p className="stage-criteria-note">안개는 시정 기반 프로젝트 UI 분류이며, 10 km 이상은 안개 없음으로 표시합니다.</p>
            {usesNowcast ? (
              <p className="stage-criteria-note">백엔드가 PM2.5·PM10의 최근 시간별 자료로 계산한 NowCast AQI 수치를 사용하고, 등급·색상은 기획안의 5단계를 적용합니다. 자료 부족·유효하지 않은 응답은 판단 대기로 표시하며, 현재 PM 농도로 다시 계산하지 않습니다. 0–100은 양호 1단계, 300 초과는 위험 5단계입니다.</p>
            ) : (
              <>
                <p className="stage-criteria-note">대기질은 PM2.5·PM10을 각각 환산한 지수 중 높은 값입니다. 두 값이 모두 있어야 계산하며, 하나라도 누락되면 판단 대기입니다.</p>
                <p className="stage-criteria-note">단일 관측값 기반 추정으로, 24시간 평균·NowCast 및 다른 오염물질을 반영한 공식 AQI가 아닙니다. <a href="https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf" target="_blank" rel="noreferrer">EPA/AirNow 산식·농도 구간(2026)</a>을 사용하며 0–100은 프로젝트 기준 양호 1단계로 묶습니다.</p>
              </>
            )}
          </div>
        )}
      </div>
      <div className="impact-grid">
        <article><div><strong>안개</strong><span>{fogDetail}</span></div><b className={`factor-stage grade-tone-${fogGrade.tone}`}>{fogStageLabel(current?.visibilityKm)}</b></article>
        <article><div><strong>대기질</strong><span>{usesNowcast ? 'AQI (NowCast)' : '추정 AQI'} {airQuality.value ?? '—'} · {airQuality.label}</span></div><b className={`factor-stage grade-tone-${airQuality.tone}`}>{airQuality.stage ?? '—'}/5단계</b></article>
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
