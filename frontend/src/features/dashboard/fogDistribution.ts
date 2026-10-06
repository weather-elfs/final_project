import type { FogLayerCell } from './types';

const LATITUDE_BUCKET_DEGREES = 0.18;
const LONGITUDE_BUCKET_DEGREES = 0.24;
const MIN_RADIUS_M = 28_000;
const MAX_RADIUS_M = 52_000;

export interface FogDistributionCluster {
  id: string;
  center: [number, number];
  cellCount: number;
  maxFogClass: number;
  intensity: number;
  radiusM: number;
}

function cellCenter(positions: Array<[number, number]>): [number, number] | null {
  if (positions.length === 0) return null;
  const [latitudeTotal, longitudeTotal] = positions.reduce(
    ([latitude, longitude], [nextLatitude, nextLongitude]) => [latitude + nextLatitude, longitude + nextLongitude],
    [0, 0],
  );
  return [latitudeTotal / positions.length, longitudeTotal / positions.length];
}

export function buildFogDistributionClusters(cells: FogLayerCell[]): FogDistributionCluster[] {
  const buckets = new Map<string, { latitudeTotal: number; longitudeTotal: number; cellCount: number; maxFogClass: number }>();

  cells.forEach((cell) => {
    const center = cellCenter(cell.positions);
    if (!center) return;
    const [latitude, longitude] = center;
    const key = `${Math.floor(latitude / LATITUDE_BUCKET_DEGREES)}:${Math.floor(longitude / LONGITUDE_BUCKET_DEGREES)}`;
    const bucket = buckets.get(key) ?? { latitudeTotal: 0, longitudeTotal: 0, cellCount: 0, maxFogClass: 0 };
    bucket.latitudeTotal += latitude;
    bucket.longitudeTotal += longitude;
    bucket.cellCount += 1;
    bucket.maxFogClass = Math.max(bucket.maxFogClass, cell.fogClass);
    buckets.set(key, bucket);
  });

  return [...buckets.entries()].map(([id, bucket]) => {
    const density = Math.sqrt(bucket.cellCount);
    return {
      id,
      center: [bucket.latitudeTotal / bucket.cellCount, bucket.longitudeTotal / bucket.cellCount],
      cellCount: bucket.cellCount,
      maxFogClass: bucket.maxFogClass,
      intensity: Math.min(1, 0.45 + Math.log2(bucket.cellCount + 1) * 0.12),
      radiusM: Math.min(MAX_RADIUS_M, Math.max(MIN_RADIUS_M, MIN_RADIUS_M + density * 3_000)),
    };
  });
}
