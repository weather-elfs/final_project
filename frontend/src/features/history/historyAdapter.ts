import type { HistoryData, HistoryRecord, HistoryType } from './types';

interface HistoryResponse {
  records?: Array<{
    id?: string;
    occurred_at?: string;
    type?: string;
    target?: string;
    status?: string;
    summary?: string;
    mission?: string;
    released_at?: string | null;
    data_status?: string;
    reason?: string;
    explanation?: string;
    mission_type?: string;
  }>;
  total?: number;
}

function historyType(value?: string): HistoryRecord['type'] {
  return value === 'ALERT' || value === 'INCIDENT' ? value : 'RESULT';
}

function historyStatus(value?: string): HistoryRecord['status'] {
  if (value === 'ALERTED' || value === 'DELAYED' || value === 'ERROR') return value;
  return 'COMPLETED';
}

export function toHistoryData(payload: unknown): HistoryData {
  const data = (payload ?? {}) as HistoryResponse;
  const records = (data.records ?? []).map((item, index) => ({
    id: item.id ?? `history-${index}`,
    occurredAt: item.occurred_at ?? '',
    type: historyType(item.type),
    target: item.target ?? '',
    status: historyStatus(item.status),
    summary: item.summary ?? '',
    mission: item.mission ?? '',
    releasedAt: item.released_at,
    dataStatus: item.data_status ?? '',
    reason: item.reason ?? '',
    explanation: item.explanation ?? '',
    missionType: item.mission_type ?? '',
  }));
  return { records, total: data.total ?? records.length };
}

export const HISTORY_TYPE_LABELS: Record<HistoryType, string> = {
  ALL: '전체',
  RESULT: '결과',
  ALERT: '경보',
  INCIDENT: '장애',
};
