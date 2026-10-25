import assert from 'node:assert/strict';
import test from 'node:test';

import { DEMO_MODE, demoAlertOperations, demoHistory, matchesDemoLogin } from './demo';
import { toAlertOperationsData } from './features/alerts/alertAdapter';
import { toHistoryData } from './features/history/historyAdapter';

test('명시적인 demo 모드가 아니면 시연 분기를 활성화하지 않는다', () => {
  assert.equal(DEMO_MODE, false);
});

test('공개 시연 ID와 코드가 모두 맞을 때만 진입을 허용한다', () => {
  assert.equal(matchesDemoLogin('33182', '100005'), true);
  assert.equal(matchesDemoLogin('33182', 'wrong'), false);
  assert.equal(matchesDemoLogin('other', '100005'), false);
  assert.equal(matchesDemoLogin('', ''), false);
});

test('시연 경보 데이터는 기존 화면 계약을 유지하며 매번 독립된 복사본을 반환한다', () => {
  const first = toAlertOperationsData(demoAlertOperations().data);
  assert.equal(first.rules.length, 3);
  assert.equal(first.decisions.length, 3);
  first.rules.length = 0;
  assert.equal(toAlertOperationsData(demoAlertOperations().data).rules.length, 3);
  assert.equal((demoAlertOperations().data as { meta: { mock: boolean } }).meta.mock, true);
});

test('시연 이력은 유형·임무 필터와 빈 결과를 지원한다', () => {
  assert.equal(toHistoryData(demoHistory().data).total, 24);
  assert.equal(toHistoryData(demoHistory({ historyType: 'ALL', missionType: 'ALL' }).data).total, 24);
  const incidents = toHistoryData(demoHistory({ historyType: 'INCIDENT', missionType: 'MARITIME_TRANSPORT' }).data);
  assert.equal(incidents.total, 7);
  assert.ok(incidents.records.every((record) => record.type === 'INCIDENT'));
  assert.equal(toHistoryData(demoHistory({ missionType: 'AIR_OPERATION' }).data).total, 0);
});
