import assert from 'node:assert/strict';
import test from 'node:test';

import { airQualityByParticles, aqiGradeTone, displayAqiGrade, fogGradeByVisibility, fogGradeTone, fogStageLabel } from './gradeTones';

test('시정 거리를 6단계 표준 안개 명칭과 색상으로 변환한다', () => {
  assert.deepEqual(fogGradeByVisibility(7), { stage: 1, label: '옅은 안개', rangeLabel: '4–10 km 미만', tone: 'green' });
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
  assert.equal(fogGradeTone(11), 'sky');
});

test('시안의 AQI 등급 색상을 매핑한다', () => {
  assert.equal(aqiGradeTone('좋음'), 'green');
  assert.equal(displayAqiGrade('양호'), '좋음');
});

test('PM2.5와 PM10의 개별 지수 중 높은 값으로 대기질을 추정한다', () => {
  assert.deepEqual(airQualityByParticles(3, 19), { value: 18, stage: 1, label: '양호', tone: 'green' });
  assert.equal(airQualityByParticles(35.5, 0).value, 101);
  assert.equal(airQualityByParticles(0, 255).value, 151);
  assert.equal(airQualityByParticles(35.5, 255).value, 151);
  assert.deepEqual(airQualityByParticles(0, 0), { value: 0, stage: 1, label: '양호', tone: 'green' });
});

test('PM2.5 농도 구간의 경계값을 AQI와 프로젝트 5단계로 변환한다', () => {
  const cases = [
    [9, 50, 1], [9.1, 51, 1], [35.4, 100, 1], [35.5, 101, 2],
    [55.4, 150, 2], [55.5, 151, 3], [125.4, 200, 3], [125.5, 201, 4],
    [225.4, 300, 4], [225.5, 301, 5], [325.4, 500, 5], [326, 501, 5],
  ];
  for (const [concentration, value, stage] of cases) {
    const grade = airQualityByParticles(concentration, 0);
    assert.equal(grade.value, value, `PM2.5 ${concentration}`);
    assert.equal(grade.stage, stage, `PM2.5 ${concentration}`);
  }
});

test('PM10 농도 구간의 경계값을 AQI와 프로젝트 5단계로 변환한다', () => {
  const cases = [
    [54, 50, 1], [55, 51, 1], [154, 100, 1], [155, 101, 2],
    [254, 150, 2], [255, 151, 3], [354, 200, 3], [355, 201, 4],
    [424, 300, 4], [425, 301, 5], [604, 500, 5], [605, 501, 5],
  ];
  for (const [concentration, value, stage] of cases) {
    const grade = airQualityByParticles(0, concentration);
    assert.equal(grade.value, value, `PM10 ${concentration}`);
    assert.equal(grade.stage, stage, `PM10 ${concentration}`);
  }
});

test('PM2.5는 소수 첫째 자리, PM10은 정수로 버림한 뒤 지수를 계산한다', () => {
  assert.equal(airQualityByParticles(9.09, 0).value, 50);
  assert.equal(airQualityByParticles(9.19, 0).value, 51);
  assert.equal(airQualityByParticles(0, 54.99).value, 50);
  assert.equal(airQualityByParticles(3.09, 19.99).value, 18);
});

test('한 성분이라도 누락되거나 잘못된 값이면 정상으로 추정하지 않는다', () => {
  for (const missing of [null, undefined, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.deepEqual(airQualityByParticles(missing, 19), { value: null, stage: null, label: '판단 대기', tone: 'neutral' });
    assert.deepEqual(airQualityByParticles(3, missing), { value: null, stage: null, label: '판단 대기', tone: 'neutral' });
  }
});

test('안개 6단계 전체 경계와 안개 없음·누락을 구별한다', () => {
  for (const [visibility, stage] of [[9.999, 1], [4, 1], [3.999, 2], [2, 2], [1.999, 3], [1, 3], [0.999, 4], [0.5, 4], [0.499, 5], [0.2, 5], [0.199, 6], [0, 6]]) {
    assert.equal(fogGradeByVisibility(visibility).stage, stage);
  }
  assert.equal(fogGradeByVisibility(50).label, '안개 없음');
  assert.deepEqual(fogGradeByVisibility(10), { stage: null, label: '안개 없음', rangeLabel: '10 km 이상', tone: 'sky' });
  assert.equal(fogStageLabel(10), '안개 없음');
  assert.equal(fogGradeTone(null), 'neutral');
  assert.equal(fogGradeByVisibility(null).label, '판단 대기');
  assert.equal(fogGradeByVisibility(-1).label, '판단 대기');
});
