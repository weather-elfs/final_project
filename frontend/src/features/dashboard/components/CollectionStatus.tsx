import { DATA_SOURCE_LABELS, SOURCE_FAILURE_MESSAGES } from '../stationStatus';
import type { DashboardData } from '../types';

export default function CollectionStatus({ dashboard, loading, retryingSource, onRetrySource }: {
  dashboard: DashboardData | null;
  loading: boolean;
  retryingSource?: string | null;
  onRetrySource?: (source: string) => void;
}) {
  const collection = dashboard?.meta?.collection;
  const errors = Object.entries(collection?.errors ?? {});
  const degraded = dashboard?.forecastTimeline?.some((point) => point.status === 'degraded' || point.status === 'unavailable');
  if (!collection || (!errors.length && !degraded)) return null;
  const expired = collection.expiresAt ? Date.parse(collection.expiresAt) <= Date.now() : false;

  return <aside className="collection-status" aria-label="자료 수집 및 예측 제한" aria-live="polite">
    <strong>일부 자료 누락 · 가능한 결과를 표시합니다</strong>
    <p>누락 입력을 포함한 예측은 참고용이며 임무 판정은 대기합니다.</p>
    {errors.map(([source, reason]) => <div className="collection-source" key={source}>
      <span><b>{DATA_SOURCE_LABELS[source] ?? source}</b><small>{SOURCE_FAILURE_MESSAGES[reason] ?? '입력 자료를 확인할 수 없습니다.'}</small></span>
      {onRetrySource && collection?.retryableSources?.includes(source) && <button type="button"
        disabled={loading || Boolean(retryingSource) || expired}
        aria-busy={retryingSource === source}
        aria-label={`${DATA_SOURCE_LABELS[source] ?? source}만 재시도`}
        onClick={() => onRetrySource(source)}>{retryingSource === source && <span className="loading-spinner" aria-hidden="true" />}{retryingSource === source ? '재시도 중…' : '재시도'}</button>}
    </div>)}
    {expired && <p>자료 보관 시간이 지났습니다. 현재 관측 갱신으로 전체 자료를 다시 받아주세요.</p>}
  </aside>;
}
