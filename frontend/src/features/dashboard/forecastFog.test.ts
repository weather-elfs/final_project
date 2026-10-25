import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildForecastFogDemoFrames,
  buildMockForecastFogFrames,
  interpolateFogMapLayer,
} from './forecastFog';
import type { FogMapLayer } from './types';

const currentLayer: FogMapLayer = {
  source: 'GK2A',
  observedAt: '2026-09-18T09:00:00+09:00',
  projection: 'EPSG:4326',
  resolutionKm: 2,
  quality: { field: 'fog_class', acceptedValues: [4, 5] },
  legend: [],
  cells: [
    {
      id: 'fog-1',
      fogClass: 5,
      positions: [
        [37.4, 126.5],
        [37.5, 126.6],
      ],
    },
  ],
};

test('실제 API에 안개 격자가 없어도 기존 격자로 예측 지도 시연 프레임을 만든다', () => {
  const timeline = [
    { horizonH: 3, validAt: '2026-09-28T15:00:00+09:00', visibilityPredKm: 29.1 },
    { horizonH: 6, validAt: '2026-09-28T18:00:00+09:00', visibilityPredKm: 28.6 },
    { horizonH: 9, validAt: '2026-09-28T21:00:00+09:00', visibilityPredKm: 27.3 },
    { horizonH: 12, validAt: '2026-09-29T00:00:00+09:00', visibilityPredKm: 26.8 },
  ];
  const original = structuredClone(timeline);
  const frames = buildForecastFogDemoFrames(undefined, timeline);
  assert.deepEqual(frames.map((frame) => frame.horizonH), [3, 6, 9, 12]);
  assert.deepEqual(frames.map((frame) => frame.validAt), timeline.map((point) => point.validAt));
  assert.ok(frames.every((frame) => frame.layer.cells.length > 0));
  assert.notDeepEqual(frames[0]?.layer.cells[0]?.positions, frames[1]?.layer.cells[0]?.positions);
  assert.deepEqual(timeline, original);
});

test('API 격자가 있으면 시연 프레임의 바탕으로 우선 사용하고 원본은 변경하지 않는다', () => {
  const original = structuredClone(currentLayer);
  const frames = buildForecastFogDemoFrames(currentLayer, [{ horizonH: 3 }]);
  assert.equal(frames[0]?.layer.cells.length, 1);
  assert.equal(frames[0]?.layer.cells[0]?.id, 'fog-1');
  assert.deepEqual(currentLayer, original);
});

test('API 예측 시점이 없으면 안개 시연도 임의의 시간으로 만들지 않는다', () => {
  assert.deepEqual(buildForecastFogDemoFrames(undefined, []), []);
});

test('예측 시점별 목 안개 프레임을 만들고 원본 격자는 변경하지 않는다', () => {
  const originalPositions = structuredClone(currentLayer.cells[0]?.positions);
  const frames = buildMockForecastFogFrames(currentLayer, [
    { horizonH: 3, validAt: '2026-09-18T12:00:00+09:00' },
    { horizonH: 6, validAt: '2026-09-18T15:00:00+09:00' },
    { horizonH: 9, validAt: '2026-09-18T18:00:00+09:00' },
    { horizonH: 12, validAt: '2026-09-18T21:00:00+09:00' },
  ]);

  assert.deepEqual(
    frames.map(({ horizonH }) => horizonH),
    [3, 6, 9, 12],
  );
  assert.equal(frames[0]?.layer.source, 'GK2A 분포 변화');
  assert.equal(
    frames[0]?.layer.observedAt,
    '2026-09-18T12:00:00+09:00',
  );
  assert.notDeepEqual(
    frames[0]?.layer.cells[0]?.positions,
    frames[1]?.layer.cells[0]?.positions,
  );
  assert.deepEqual(currentLayer.cells[0]?.positions, originalPositions);
});

test('현재 안개 격자가 없거나 예측 시점에 시간이 없으면 프레임을 만들지 않는다', () => {
  assert.deepEqual(buildMockForecastFogFrames(undefined, [{ horizonH: 3 }]), []);
  assert.deepEqual(buildMockForecastFogFrames(currentLayer, [{}]), []);
});

test('두 예측 프레임 사이의 안개 좌표를 중간값으로 보간한다', () => {
  const nextLayer: FogMapLayer = {
    ...currentLayer,
    observedAt: '2026-09-18T12:00:00+09:00',
    cells: [
      {
        ...currentLayer.cells[0]!,
        positions: [
          [37.6, 126.9],
          [37.7, 127.0],
        ],
      },
    ],
  };

  const middleLayer = interpolateFogMapLayer(currentLayer, nextLayer, 0.5);

  assert.deepEqual(middleLayer.cells[0]?.positions, [
    [37.5, 126.7],
    [37.6, 126.8],
  ]);
  assert.equal(middleLayer.observedAt, nextLayer.observedAt);
});
