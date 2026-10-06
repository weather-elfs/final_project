import assert from 'node:assert/strict';
import test from 'node:test';

import { buildFogDistributionClusters } from './fogDistribution';
import type { FogLayerCell } from './types';

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
  assert.equal(nearbyCluster.maxFogClass, 5);
});

test('군집 안에서 가장 높은 안개 등급을 분포 단계로 유지한다', () => {
  const lower = cell('a', 37.5, 126.1);
  lower.fogClass = 4;
  const clusters = buildFogDistributionClusters([lower, cell('b', 37.51, 126.11)]);

  assert.equal(clusters[0]?.maxFogClass, 5);
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
