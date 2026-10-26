import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import ForecastPanel from './ForecastPanel';

function renderForecast(visibilityPredKm: number | null) {
  return renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { forecastTimeline: [{ horizonH: 3, validAt: '2026-10-26T11:00:00+09:00', visibilityPredKm }] },
    requested: true,
    loading: false,
  }));
}

test('안개 없음은 예측 표와 종합 예측 모두 단계 없이 이름만 표시한다', () => {
  for (const visibility of [10, 50]) {
    const markup = renderForecast(visibility);
    assert.match(markup, /<span>안개 없음<\/span>/);
    assert.match(markup, /· 안개 없음<\/p>/);
    assert.doesNotMatch(markup, /\/6단계/);
  }
});

test('안개가 있으면 기존 단계 숫자와 이름을 유지한다', () => {
  const markup = renderForecast(1.5);
  assert.match(markup, /<span>3\/6단계<\/span>/);
  assert.match(markup, /· 3\/6단계 안개<\/p>/);
});

test('시정 자료 없음은 안개 없음과 구분한다', () => {
  const markup = renderForecast(null);
  assert.match(markup, /—\/6단계/);
  assert.match(markup, /판단 대기/);
  assert.doesNotMatch(markup, /안개 없음/);
});
test('누락 입력과 항목별 예측 불가를 표시하면서 가능한 예측은 유지한다', () => {
  const markup = renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { forecastTimeline: [{ horizonH: 3, validAt: '2026-10-26T12:00:00+09:00', status: 'degraded', visibilityPredKm: 12, pm25PredUgM3: null, pm10PredUgM3: 20, missingSources: ['AIRKOREA_FORECAST'], unavailableTargets: ['pm25'] }] },
    requested: true, loading: false,
  }));
  assert.match(markup, /일부 입력 누락/);
  assert.match(markup, /에어코리아 예보/);
  assert.match(markup, /PM2.5 예측 없음/);
  assert.match(markup, /12.0 km/);
  assert.match(markup, /20.0 ㎍\/m³/);
});
