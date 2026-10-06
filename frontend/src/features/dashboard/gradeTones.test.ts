import assert from 'node:assert/strict';
import test from 'node:test';

import { aqiGradeTone, displayAqiGrade, fogGradeByVisibility, fogGradeTone, fogStageLabel } from './gradeTones';

test('시정 거리를 6단계 표준 안개 명칭과 색상으로 변환한다', () => {
  assert.deepEqual(fogGradeByVisibility(7), { stage: 1, label: '옅은 안개', rangeLabel: '4–10 km', tone: 'green' });
  assert.deepEqual(fogGradeByVisibility(3), { stage: 2, label: '옅은 안개', rangeLabel: '2–4 km', tone: 'yellow' });
  assert.deepEqual(fogGradeByVisibility(1.5), { stage: 3, label: '안개', rangeLabel: '1–2 km', tone: 'orange' });
  assert.deepEqual(fogGradeByVisibility(0.7), { stage: 4, label: '안개', rangeLabel: '500 m–1 km', tone: 'red' });
  assert.deepEqual(fogGradeByVisibility(0.3), { stage: 5, label: '짙은 안개', rangeLabel: '200–500 m', tone: 'purple' });
  assert.deepEqual(fogGradeByVisibility(0.1), { stage: 6, label: '짙은 안개', rangeLabel: '200 m 미만', tone: 'maroon' });
});

test('단계 경계와 누락 값을 보수적으로 처리한다', () => {
  assert.equal(fogStageLabel(4), '1/6단계');
  assert.equal(fogStageLabel(2), '2/6단계');
  assert.equal(fogStageLabel(0.2), '5/6단계');
  assert.equal(fogStageLabel(0.19), '6/6단계');
  assert.equal(fogStageLabel(undefined), '—/6단계');
  assert.equal(fogGradeTone(11), 'neutral');
});

test('시안의 AQI 등급 색상을 매핑한다', () => {
  assert.equal(aqiGradeTone('좋음'), 'green');
  assert.equal(displayAqiGrade('양호'), '좋음');
});
