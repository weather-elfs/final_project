import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import ForecastPanel from './ForecastPanel';

function renderForecast(visibilityPredKm: number | null, loading = false) {
  return renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { forecastTimeline: [{ horizonH: 3, validAt: '2026-10-26T11:00:00+09:00', visibilityPredKm }] },
    requested: true,
    loading,
  }));
}

test('조회 즉시 카드 로딩을 표시하고 기존 예측 수치는 유지하며 완료 시 제거한다', () => {
  const pending = renderForecast(12, true);
  assert.match(pending, /aria-busy="true"/);
  assert.match(pending, /class="card-loading-overlay" role="status"/);
  assert.match(pending, /예측 결과 조회 중/);
  assert.match(pending, /12.0 km/);
  assert.doesNotMatch(renderForecast(12), /card-loading-overlay/);
});

test('안개 없음은 예측 표와 종합 예측 모두 단계 없이 이름만 표시한다', () => {
  for (const visibility of [10, 50]) {
    const markup = renderForecast(visibility);
    assert.match(markup, /class="stage-criteria-badge forecast-stage-badge grade-tone-sky">안개 없음<\/span>/);
    assert.match(markup, /· 안개 없음<\/p>/);
    assert.doesNotMatch(markup, /\/6단계/);
  }
});

test('안개가 있으면 기존 단계 숫자와 이름을 유지한다', () => {
  const markup = renderForecast(1.5);
  assert.match(markup, /class="stage-criteria-badge forecast-stage-badge grade-tone-orange">3\/6단계<\/span>/);
  assert.match(markup, /class="forecast-grade-description">안개<\/span>/);
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
  assert.match(markup, /<details class="forecast-input-details"><summary>예측 자료 상세<\/summary>/);
  assert.doesNotMatch(markup, /<th scope="row">입력 상태<\/th>/);
});

test('시안의 여섯 항목을 순서대로 표시하고 대기질은 예측 PM 기반 등급을 쓴다', () => {
  const markup = renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { forecastTimeline: [{ horizonH: 3, weatherLabel: '흐림', temperatureC: 17, windDirectionLabel: '북서풍', windSpeedMS: 4, visibilityPredKm: 4.6, pm25PredUgM3: 40, pm10PredUgM3: 50 }] },
    requested: true, loading: false,
  }));
  assert.deepEqual([...markup.matchAll(/<th scope="row"[^>]*>(.*?)<\/th>/g)].map((match) => match[1]), ['날씨', '기온', '풍향·풍속', '시정', '안개 단계', '대기질']);
  for (const text of ['흐림', '17°C', '북서풍', '4.0 m/s', '4.6 km']) assert.ok(markup.includes(text));
  assert.match(markup, /class="stage-criteria-badge forecast-stage-badge grade-tone-orange">2\/5단계<\/span><span class="forecast-grade-description">민감군 주의<\/span>/);
  assert.match(markup, /추정 AQI/);
  assert.doesNotMatch(markup, /<th scope="row">PM/);
});

test('날씨 아이콘은 텍스트와 함께 표시하고 결측·알 수 없는 날씨에는 임의 아이콘을 붙이지 않는다', () => {
  for (const [label, kind] of [['맑음', 'sun'], ['흐림', 'cloud'], ['구름많음', 'cloud'], ['박무', 'mist'], ['안개', 'fog'], ['비', 'rain'], ['눈', 'snow'], ['비 또는 눈', 'sleet']] as const) {
    const markup = renderToStaticMarkup(createElement(ForecastPanel, {
      dashboard: { forecastTimeline: [{ horizonH: 3, weatherLabel: label }] }, requested: true, loading: false,
    }));
    assert.match(markup, new RegExp(`data-weather="${kind}"`));
    assert.match(markup, /aria-hidden="true" focusable="false"/);
    assert.ok(markup.includes(`<span>${label}</span>`));
  }
  assert.doesNotMatch(renderForecast(null), /forecast-weather-icon/);
});

test('기상 예보나 예측 PM이 없으면 현재 관측값으로 대체하지 않는다', () => {
  const markup = renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { current: { temperatureC: 99, weatherLabel: '맑음', pm25UgM3: 3, pm10UgM3: 10 }, forecastTimeline: [{ horizonH: 3, visibilityPredKm: 12, pm25PredUgM3: null, pm10PredUgM3: 20 }] },
    requested: true, loading: false,
  }));
  assert.match(markup, /자료 없음/);
  assert.match(markup, /판단 대기/);
  assert.doesNotMatch(markup, /99°C|>맑음<|1\/5단계/);
});

test('이전 정상 관측값만 재사용한 예측은 누락 대신 이전 자료 사용으로 표시한다', () => {
  const markup = renderToStaticMarkup(createElement(ForecastPanel, {
    dashboard: { sourceStatus: [{ source: 'AIRKOREA', status: 'delayed', reason: 'PREVIOUS_OBSERVATION_USED' }], forecastTimeline: [{ horizonH: 3, status: 'degraded', visibilityPredKm: 12, missingSources: ['AIRKOREA'] }] },
    requested: true, loading: false,
  }));
  assert.match(markup, /이전 자료 사용/);
  assert.doesNotMatch(markup, /일부 입력 누락/);
});
