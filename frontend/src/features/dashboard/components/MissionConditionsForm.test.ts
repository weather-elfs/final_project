import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import MissionConditionsForm from './MissionConditionsForm';

test('지도에서 선택한 ASOS 해역은 표시하고 직접 선택은 비활성화하며 지도 밖 선택도 유지한다', () => {
  const markup = renderToStaticMarkup(createElement(MissionConditionsForm, {
    config: { stations: [], forecastIntervalOptionsH: [6], missionTypes: [] },
    values: { stationId: '112', forecastIntervalH: 6, missionType: 'MARITIME_TRANSPORT' },
    selectedStationName: '인천',
    loading: false, onChange: () => {}, onSubmit: () => {},
  }));
  assert.match(markup, /<select id="mission-station" disabled=""/);
  assert.match(markup, /<option value="112" selected="">인천<\/option>/);
  assert.doesNotMatch(markup, /<select id="forecast-interval"[^>]*disabled/);
  assert.doesNotMatch(markup, /<button type="submit" disabled/);
});

test('관측 갱신 중에는 버튼 문구를 유지하고 예측 제출 중에만 조회 중으로 표시한다', () => {
  const render = (submitting: boolean) => renderToStaticMarkup(createElement(MissionConditionsForm, {
    config: { stations: [], forecastIntervalOptionsH: [], missionTypes: [] },
    values: { stationId: '112', forecastIntervalH: 6, missionType: 'MARITIME_TRANSPORT' },
    loading: true, submitting, onChange: () => {}, onSubmit: () => {},
  }));
  assert.match(render(false), /<button type="submit" disabled="">시간대별 예측 보기<\/button>/);
  assert.doesNotMatch(render(false), /조회 중…/);
  assert.match(render(true), /<button type="submit" disabled="">조회 중…<\/button>/);
});

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
