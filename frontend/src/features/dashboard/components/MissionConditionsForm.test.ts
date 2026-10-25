import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import MissionConditionsForm from './MissionConditionsForm';

test('API 기준 시각 없이도 전달된 현재 시각을 표시한다', () => {
  const markup = renderToStaticMarkup(createElement(MissionConditionsForm, {
    config: { stations: [], forecastIntervalOptionsH: [], missionTypes: [] },
    values: { stationId: '', forecastIntervalH: '', missionType: '' },
    currentTime: '2026-10-26T01:20:30+09:00',
    loading: false,
    onChange: () => {},
    onSubmit: () => {},
  }));
  assert.match(markup, /value="01:20:30 KST"/);
  assert.match(markup, /예측 기준 시각 --:--:-- KST/);
});

test('현재 시각과 실제 관측에 따른 예측 기준 시각을 분리한다', () => {
  const markup = renderToStaticMarkup(createElement(MissionConditionsForm, {
    config: { stations: [], forecastIntervalOptionsH: [], missionTypes: [] },
    values: { stationId: '', forecastIntervalH: '', missionType: '' },
    currentTime: '2026-10-26T01:20:30+09:00',
    forecastBaseTime: '2026-10-26T00:00:00+09:00',
    loading: false,
    onChange: () => {},
    onSubmit: () => {},
  }));
  assert.match(markup, /value="01:20:30 KST"/);
  assert.match(markup, /예측 기준 시각 00:00:00 KST/);
});
