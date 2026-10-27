import assert from 'node:assert/strict';
import test from 'node:test';

import { toHistoryData } from './historyAdapter';

test('이력 응답을 상세 판단 근거 화면 모델로 변환한다', () => {
  const result = toHistoryData({
    total: 1,
    records: [{ id: 'history-1', occurred_at: '2026-09-18T09:05:00+09:00', type: 'ALERT', target: '해양 수송·보급', status: 'ALERTED', summary: '기준 충족', mission: '해양 수송·보급', released_at: null, data_status: '정상', reason: '판단 근거', explanation: '설명', mission_type: 'MARITIME_TRANSPORT' }],
  });

  assert.equal(result.total, 1);
  assert.equal(result.records[0]?.occurredAt, '2026-09-18T09:05:00+09:00');
  assert.equal(result.records[0]?.dataStatus, '정상');
  assert.equal(result.records[0]?.status, 'ALERTED');
});
