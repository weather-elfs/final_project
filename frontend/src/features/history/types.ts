export type HistoryType = 'ALL' | 'RESULT' | 'ALERT' | 'INCIDENT';

export interface HistoryRecord {
  id: string;
  occurredAt: string;
  type: Exclude<HistoryType, 'ALL'>;
  target: string;
  status: 'ALERTED' | 'DELAYED' | 'ERROR' | 'COMPLETED';
  summary: string;
  mission: string;
  releasedAt?: string | null;
  dataStatus: string;
  reason: string;
  explanation: string;
  missionType: string;
}

export interface HistoryData {
  records: HistoryRecord[];
  total: number;
}
