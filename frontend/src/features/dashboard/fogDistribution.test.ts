import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildFogBlobPositions,
  buildFogCoverageBounds,
  buildFogDistributionClusters,
  buildFogRasterCells,
} from './fogDistribution';
import type { FogLayerCell } from './types';
import { buildFogSurface } from './fogSurface';

function cell(id: string, latitude: number, longitude: number): FogLayerCell {
  return {
    id,
    fogClass: 5,
    positions: [
      [latitude - 0.01, longitude - 0.01],
      [latitude - 0.01, longitude + 0.01],
      [latitude + 0.01, longitude + 0.01],
      [latitude + 0.01, longitude - 0.01],
    ],
  };
}

test('가까운 GK2A 격자를 하나의 안개 분포핵으로 묶는다', () => {
  const clusters = buildFogDistributionClusters([
    cell('a', 37.5, 126.1),
    cell('b', 37.51, 126.11),
    cell('c', 38.0, 124.7),
  ]);

  assert.equal(clusters.length, 2);
  const nearbyCluster = clusters.find((cluster) => cluster.cellCount === 2);
  assert.ok(nearbyCluster);
  assert.ok(Math.abs(nearbyCluster.center[0] - 37.505) < 1e-9);
  assert.equal(nearbyCluster.maxDisplayStage, 4);
});

test('GK2A 안개 분류를 피그마의 화면 단계로 변환한다', () => {
  const lower = cell('a', 37.5, 126.1);
  lower.fogClass = 4;
  const clusters = buildFogDistributionClusters([lower, cell('b', 37.51, 126.11)]);

  assert.equal(clusters[0]?.maxDisplayStage, 4);
});

test('청천·구름·적설 등 안개가 아닌 GK2A 분류는 제외한다', () => {
  const clear = cell('clear', 37.5, 126.1);
  clear.fogClass = 1;
  const snow = cell('snow', 37.51, 126.11);
  snow.fogClass = 6;

  assert.deepEqual(buildFogDistributionClusters([clear, snow]), []);
});

test('격자가 많을수록 분포 반경과 강도가 커진다', () => {
  const single = buildFogDistributionClusters([cell('a', 37.5, 126.1)])[0];
  const dense = buildFogDistributionClusters([
    cell('a', 37.5, 126.1),
    cell('b', 37.51, 126.11),
    cell('c', 37.52, 126.12),
  ])[0];

  assert.ok(single);
  assert.ok(dense);
  assert.ok(dense.radiusM > single.radiusM);
  assert.ok(dense.intensity > single.intensity);
});

test('단일 격자는 작은 분포핵으로 표시한다', () => {
  const single = buildFogDistributionClusters([cell('a', 37.5, 126.1)])[0];

  assert.ok(single);
  assert.ok(single.radiusM < 15_000);
});

test('분포핵을 일정한 원이 아닌 불규칙한 안개 윤곽으로 만든다', () => {
  const cluster = buildFogDistributionClusters([
    cell('organic-shape', 37.5, 126.1),
  ])[0];

  assert.ok(cluster);
  const positions = buildFogBlobPositions(cluster);
  const longitudeMetersPerDegree =
    111_320 * Math.cos(cluster.center[0] * (Math.PI / 180));
  const distances = positions.map(([latitude, longitude]) =>
    Math.round(
      Math.hypot(
        (latitude - cluster.center[0]) * 111_320,
        (longitude - cluster.center[1]) * longitudeMetersPerDegree,
      ),
    ),
  );

  assert.equal(positions.length, 18);
  assert.ok(new Set(distances).size > 5);
});

test('레이더형 격자는 가장자리보다 밀집된 내부를 진한 단계로 표시한다', () => {
  const cells = Array.from({ length: 3 }, (_, row) =>
    Array.from({ length: 3 }, (_, column) =>
      cell(`${row + 10}-${column + 20}`, 37.5 + row * 0.01, 126.1 + column * 0.01),
    ),
  ).flat();
  const rasterCells = buildFogRasterCells(cells);
  const corner = rasterCells.find((rasterCell) => rasterCell.id === '10-20');
  const center = rasterCells.find((rasterCell) => rasterCell.id === '11-21');

  assert.ok(corner);
  assert.ok(center);
  assert.ok(center.displayStage > corner.displayStage);
  assert.ok(center.fillOpacity > corner.fillOpacity);
});

test('안개 격자 전체를 감싸는 중립 색상 영역을 계산한다', () => {
  const bounds = buildFogCoverageBounds(
    [cell('coverage', 37.5, 126.1)],
    0.1,
  );

  assert.deepEqual(bounds, [
    [37.39, 125.99],
    [37.61, 126.21],
  ]);
  assert.equal(buildFogCoverageBounds([]), undefined);
});

test('연속 안개 면은 이웃 격자 사이를 끊김 없이 보간한다', () => {
  const cells = [cell('10-20', 37.5, 126.1), cell('10-21', 37.5, 126.14)];
  const original = JSON.stringify(cells);
  const surface = buildFogSurface(cells);
  assert.ok(surface);
  assert.equal(JSON.stringify(cells), original);

  const row = Math.floor(surface.height / 2);
  const center = Math.floor(surface.width / 2);
  const centerAlpha = surface.pixels[(row * surface.width + center) * 4 + 3]!;
  let peakAlpha = 0;
  for (let index = 3; index < surface.pixels.length; index += 4) {
    peakAlpha = Math.max(peakAlpha, surface.pixels[index]!);
  }
  assert.ok(peakAlpha > 0, '안개 면이 표시되어야 한다');
  assert.ok(
    centerAlpha >= peakAlpha * 0.9,
    '이웃 좌표 사이에도 연속된 색상 면이 있어야 한다',
  );

  let largestColorStep = 0;
  for (let x = 1; x < surface.width; x += 1) {
    for (let channel = 0; channel < 4; channel += 1) {
      const previous = surface.pixels[(row * surface.width + x - 1) * 4 + channel]!;
      const current = surface.pixels[(row * surface.width + x) * 4 + channel]!;
      largestColorStep = Math.max(largestColorStep, Math.abs(current - previous));
    }
  }
  assert.ok(largestColorStep < 12, '색상과 투명도가 격자 경계에서 튀면 안 된다');
});

test('멀리 떨어진 안개 영역 사이를 임의의 안개 면으로 채우지 않는다', () => {
  const surface = buildFogSurface([
    cell('10-20', 37.5, 124.1),
    cell('10-120', 37.5, 127.1),
  ]);
  assert.ok(surface);
  const center = (Math.floor(surface.height / 2) * surface.width +
    Math.floor(surface.width / 2)) * 4;
  assert.equal(surface.pixels[center + 3], 0);
});

test('안개가 없거나 잘못된 좌표만 있으면 캔버스 데이터를 만들지 않는다', () => {
  const clear = { ...cell('clear', 37.5, 126.1), fogClass: 1 };
  const invalid = cell('invalid', Number.NaN, 126.1);
  assert.equal(buildFogSurface([]), undefined);
  assert.equal(buildFogSurface([clear, invalid]), undefined);
});
