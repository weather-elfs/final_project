import assert from 'node:assert/strict';
import test from 'node:test';

import { aqiGradeTone, displayAqiGrade, fogGradeTone } from './gradeTones';

test('시안의 안개·AQI 등급 색상을 매핑한다', () => {
  assert.equal(aqiGradeTone('좋음'), 'green');
  assert.equal(displayAqiGrade('양호'), '좋음');
  assert.equal(fogGradeTone('박무'), 'yellow');
  assert.equal(fogGradeTone('안개'), 'purple');
  assert.equal(fogGradeTone('짙은 안개'), 'maroon');
});
