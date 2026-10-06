import assert from 'node:assert/strict';
import test from 'node:test';

import { aqiGradeTone, displayAqiGrade, fogGradeTone, fogStageLabel } from './gradeTones';

test('시안의 안개·AQI 등급 색상을 매핑한다', () => {
  assert.equal(aqiGradeTone('좋음'), 'green');
  assert.equal(displayAqiGrade('양호'), '좋음');
  assert.equal(fogGradeTone('옅은 안개'), 'green');
  assert.equal(fogGradeTone('안개 가능'), 'yellow');
  assert.equal(fogGradeTone('박무'), 'orange');
  assert.equal(fogGradeTone('안개'), 'red');
  assert.equal(fogGradeTone('짙은 안개'), 'purple');
  assert.equal(fogGradeTone('매우 짙은 안개'), 'maroon');
  assert.equal(fogStageLabel('옅은 안개'), '1/6단계');
  assert.equal(fogStageLabel('안개 가능'), '2/6단계');
  assert.equal(fogStageLabel('짙은 안개'), '5/6단계');
  assert.equal(fogStageLabel('판단 대기'), '—/6단계');
});
