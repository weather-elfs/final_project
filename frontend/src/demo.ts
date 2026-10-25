import type { ApiEnvelope, HistoryRequest } from './api';
import { alertOperationsFixture, historyRecords } from './mocks/operationsFixtures';

// 공개 시연용 화면 모드다. 인증·인가 또는 비밀 자격증명으로 사용하지 않는다.
export const DEMO_MODE = import.meta.env?.MODE === 'demo';
export const DEMO_CENTER = { id: '33182', name: '시연 관제센터' };

export function matchesDemoLogin(centerId: string, accessCode: string) {
  return centerId === DEMO_CENTER.id && accessCode === '100005';
}

export function demoAlertOperations(): ApiEnvelope<unknown> {
  const fixture = structuredClone(alertOperationsFixture);
  return {
    ...fixture,
    message: '시연용 경보 운영 데이터를 표시합니다.',
    data: { ...fixture.data, meta: { ...fixture.data.meta, mock: true } },
  };
}

export function demoHistory({ historyType, missionType }: HistoryRequest = {}): ApiEnvelope<unknown> {
  const records = structuredClone(historyRecords.filter((record) => (
    (!historyType || historyType === 'ALL' || record.type === historyType)
    && (!missionType || missionType === 'ALL' || record.mission_type === missionType)
  )));
  return {
    code: 'SUCCESS',
    message: '시연용 이력 데이터를 표시합니다.',
    data: {
      records,
      total: records.length,
      page: 1,
      page_size: 10,
      meta: { request_id: 'req_demo_history', generated_at: '2026-10-30T14:30:00+09:00', mock: true },
    },
  };
}
