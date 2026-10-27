import assert from 'node:assert/strict';
import test from 'node:test';

import { toAlertOperationsData } from './alertAdapter';

test('경보 운영 응답의 snake_case 필드를 화면 모델로 변환한다', () => {
  const result = toAlertOperationsData({
    principles: [{ title: '기준 사전 확정', description: '설명' }],
    rules: [{ id: 'rule-1', mission_type: '해양 수송·보급', trigger_threshold: '1 km', clear_threshold: '2 km', confirmation_duration: '10분', missing_data_action: '판단 불가' }],
    decisions: [{ id: 'decision-1', occurred_at: '2026-09-18T09:05:00+09:00', status: 'ALERT', mission: '해양 수송·보급', reason: '기준 충족' }],
  });

  assert.equal(result.rules[0]?.missionType, '해양 수송·보급');
  assert.equal(result.rules[0]?.confirmationDuration, '10분');
  assert.equal(result.decisions[0]?.occurredAt, '2026-09-18T09:05:00+09:00');
});
