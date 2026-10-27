import { formatKstTime } from '../formatters';
import { DATA_SOURCE_LABELS, SOURCE_FAILURE_MESSAGES } from '../stationStatus';
import type { DashboardData, SourceStatusDetail } from '../types';

const SOURCE_LABELS: Record<string, string> = {
  ...DATA_SOURCE_LABELS,
  AIRKOREA: '에어코리아', MARINE: '해양부이', PM1: '산림청 PM1', FOREST: '산림청 PM1', GK2A: '천리안',
};
const SOURCE_ORDER = ['ASOS', 'TIDE_OBSERVATORY', 'MARINE', 'PM1', 'FOREST', 'AIRKOREA', 'GK2A'];

function sourceStatusPresentation(status?: string) {
  const normalized = status?.toUpperCase();
  if (normalized === 'PARTIAL') return { label: '일부 누락', tone: 'delayed' } as const;
  if (normalized === 'OK' || normalized === 'FRESH' || normalized === 'GOOD') return { label: '정상', tone: 'good' } as const;
  if (normalized === 'STALE' || normalized === 'DELAYED') return { label: '지연', tone: 'delayed' } as const;
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
  if (source.reason?.startsWith('UPSTREAM_COMMUNICATION_FAILURE')) return `${SOURCE_FAILURE_MESSAGES[source.reason]}${observedTime ? ` · 관측 ${observedTime}` : ''}`;
  if (source.reason === 'PREVIOUS_OBSERVATION_USED') return `${SOURCE_FAILURE_MESSAGES.PREVIOUS_OBSERVATION_USED}${observedTime ? ` · 관측 ${observedTime}` : ''}`;
  if (source.status.toUpperCase() === 'PARTIAL') return `${SOURCE_FAILURE_MESSAGES[source.reason ?? ''] ?? '일부 관측값 누락'}${observedTime ? ` · 관측 ${observedTime}` : ''}`;
  if (presentation.tone === 'good') return observedTime ? `${observedTime} 수신` : '정상 수신';
  if (presentation.tone === 'delayed') return `${elapsedLabel(source.ageMinutes)}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
  const reason = SOURCE_FAILURE_MESSAGES[source.reason ?? ''] ?? (source.reason?.toUpperCase() === 'TIMEOUT'
    ? '응답 시간 초과' : source.reason?.toUpperCase() === 'MISSING' ? '데이터 없음' : source.reason || '수신 오류');
  return `${reason}${observedTime ? ` · 정상 ${observedTime}` : ''}`;
}

export default function CollectionStatus({ dashboard, loading, retryingSource, onRetrySource }: {
  dashboard: DashboardData | null;
  loading: boolean;
  retryingSource?: string | null;
  onRetrySource?: (source: string) => void;
}) {
  const collection = dashboard?.meta?.collection;
  const errors = collection?.errors ?? {};
  const sources = [...(dashboard?.sourceStatus ?? [])];
  for (const [source, reason] of Object.entries(errors)) {
    if (!sources.some((item) => item.source === source)) sources.push({ source, status: 'error', reason });
  }
  sources.sort((left, right) => {
    const leftOrder = SOURCE_ORDER.indexOf(left.source.toUpperCase());
    const rightOrder = SOURCE_ORDER.indexOf(right.source.toUpperCase());
    return (leftOrder < 0 ? SOURCE_ORDER.length : leftOrder) - (rightOrder < 0 ? SOURCE_ORDER.length : rightOrder);
  });
  const expired = collection?.expiresAt ? Date.parse(collection.expiresAt) <= Date.now() : false;

  return <div className="data-status-list">
    {sources.length ? sources.map((source) => {
      const presentation = source.reason?.startsWith('UPSTREAM_COMMUNICATION_FAILURE')
        ? { label: '관측소 통신장애', tone: 'error' } as const
        : sourceStatusPresentation(source.status);
      const label = SOURCE_LABELS[source.source.toUpperCase()] ?? source.source;
      const error = errors[source.source];
      return <details className="data-status-row" key={source.source}>
        <summary>
          <i className={`status-${presentation.tone}`} aria-hidden="true" />
          <strong>{label}</strong>
          <b className={`status-${presentation.tone}`}>{presentation.label}</b>
          <span className="data-status-preview">{sourceStatusMessage(source)}</span>
          <span className="data-status-chevron" aria-hidden="true" />
        </summary>
        <div className="data-status-detail">
          <p>{sourceStatusMessage(source)}</p>
          {error && error !== source.reason && <p>{SOURCE_FAILURE_MESSAGES[error] ?? '입력 자료를 확인할 수 없습니다.'}</p>}
          {onRetrySource && error && collection?.retryableSources?.includes(source.source) && <button type="button"
            disabled={loading || Boolean(retryingSource) || expired}
            aria-busy={retryingSource === source.source}
            aria-label={`${DATA_SOURCE_LABELS[source.source] ?? label}만 재시도`}
            onClick={() => onRetrySource(source.source)}>{retryingSource === source.source && <span className="loading-spinner" aria-hidden="true" />}{retryingSource === source.source ? '재시도 중…' : '재시도'}</button>}
        </div>
      </details>;
    }) : <p className="data-status-empty">출처별 상태 정보가 없습니다.</p>}
    {expired && Object.keys(errors).length > 0 && <p className="data-status-expired">자료 보관 시간이 지났습니다. 현재 관측 갱신으로 전체 자료를 다시 받아주세요.</p>}
  </div>;
}
