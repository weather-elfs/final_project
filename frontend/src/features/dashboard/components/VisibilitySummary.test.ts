import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import type { DashboardData } from '../types';
import VisibilitySummary from './VisibilitySummary';

function renderSummary(dashboard: DashboardData) {
  return renderToStaticMarkup(createElement(VisibilitySummary, { dashboard, loading: false, onRefresh: () => {} }));
}

test('시정 영향 요인은 원시 관측값으로 계산하고 종합 판정은 서버 값을 유지한다', () => {
  const markup = renderSummary({
    current: {
      visibilityKm: 50,
      pm25UgM3: 3,
      pm10UgM3: 19,
      aqi: { value: 999, displayLevel: 5, displayGrade: '위험' },
    },
    diagnosis: { pmDisplayGrade: '위험', summary: '서버 임무 판정' },
  });
  assert.match(markup, /추정 AQI 18 · 양호/);
  assert.match(markup, /grade-tone-green">1\/5단계/);
  assert.match(markup, /grade-tone-sky">안개 없음/);
  assert.match(markup, /종합 추정: 서버 임무 판정/);
  assert.doesNotMatch(markup, /AQI 999/);
});

test('시정·미세먼지가 악화되면 각 단계와 배지 색상도 함께 바뀐다', () => {
  const markup = renderSummary({ current: { visibilityKm: 1.5, pm25UgM3: 55.5, pm10UgM3: 50 } });
  assert.match(markup, /grade-tone-orange">3\/6단계/);
  assert.match(markup, /추정 AQI 151 · 나쁨/);
  assert.match(markup, /grade-tone-red">3\/5단계/);
});

test('누락된 관측값을 서버 AQI나 정상 단계로 대신 채우지 않는다', () => {
  const markup = renderSummary({ current: { visibilityKm: null, pm25UgM3: null, pm10UgM3: 19, aqi: { value: 18, displayLevel: 1, displayGrade: '양호' } } });
  assert.match(markup, /추정 AQI — · 판단 대기/);
  assert.match(markup, /grade-tone-neutral">—\/5단계/);
  assert.match(markup, /grade-tone-neutral">—\/6단계/);
});
