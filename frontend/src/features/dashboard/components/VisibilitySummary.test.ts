import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import type { DashboardData } from '../types';
import { toDashboardData } from '../dashboardAdapter';
import VisibilitySummary from './VisibilitySummary';

function renderSummary(dashboard: DashboardData) {
  return renderToStaticMarkup(createElement(VisibilitySummary, { dashboard, loading: false, onRefresh: () => {} }));
}

test('최신 조회 실패로 자료가 없어지면 데이터 상태를 정상으로 표시하지 않는다', () => {
  const markup = renderToStaticMarkup(createElement(VisibilitySummary, { dashboard: null, loading: false, onRefresh: () => {} }));
  assert.match(markup, /데이터 상태 · 자료 없음/);
  assert.doesNotMatch(markup, /데이터 상태 · 정상/);
});

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

test('NowCast 수치는 유지하고 서버 등급 대신 기획안 5단계를 적용한다', () => {
  const markup = renderSummary(toDashboardData({
    current: {
      pm25_ug_m3: 3,
      pm10_ug_m3: 19,
      aqi: { basis: 'NOWCAST_CURRENT', standard: 'US_EPA', status: 'calculated', value: 62, display_level: 5, display_grade: '위험' },
    },
  }));
  assert.match(markup, /AQI \(NowCast\) 62 · 양호/);
  assert.match(markup, /grade-tone-green">1\/5단계/);
  assert.doesNotMatch(markup, /추정 AQI 18/);
});

test('NowCast가 자료 부족이면 현재 PM 값이 있어도 판단 대기로 표시한다', () => {
  const markup = renderSummary({ current: {
    pm25UgM3: 3, pm10UgM3: 19,
    aqi: { basis: 'NOWCAST_CURRENT', status: 'insufficient_data', value: null, displayLevel: null, displayGrade: null },
  } });
  assert.match(markup, /AQI \(NowCast\) — · 판단 대기/);
  assert.match(markup, /grade-tone-neutral">—\/5단계/);
});

test('NowCast 0은 유효하고 누락·음수·비정상 수치는 판단 대기로 표시한다', () => {
  const current = { aqi: { basis: 'NOWCAST_CURRENT', status: 'calculated', value: 0, displayLevel: 1, displayGrade: '양호' } };
  assert.match(renderSummary({ current }), /AQI \(NowCast\) 0 · 양호/);
  for (const value of [undefined, null, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.match(renderSummary({ current: { aqi: { ...current.aqi, value } } }), /AQI \(NowCast\) — · 판단 대기/);
  }
  assert.match(renderSummary({ current: { aqi: { ...current.aqi, displayLevel: 6 } } }), /AQI \(NowCast\) 0 · 양호/);
});

test('500 초과 NowCast는 실제 수치와 기획안 위험 5단계를 표시한다', () => {
  const markup = renderSummary({ current: { aqi: { basis: 'NOWCAST_CURRENT', status: 'calculated', value: 649 } } });
  assert.match(markup, /AQI \(NowCast\) 649 · 위험/);
  assert.match(markup, /grade-tone-maroon">5\/5단계/);
});
