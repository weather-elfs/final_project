import assert from 'node:assert/strict';
import test from 'node:test';

import {
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
  assert.equal(frames[0]?.layer.source, 'GK2A 목 예측');
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
