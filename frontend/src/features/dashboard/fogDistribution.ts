import type { FogLayerCell } from './types';

const LATITUDE_BUCKET_DEGREES = 0.08;
const LONGITUDE_BUCKET_DEGREES = 0.1;
const MIN_RADIUS_M = 12_000;
const MAX_RADIUS_M = 24_000;
const BLOB_POINT_COUNT = 18;
const FOG_CLASS_TO_DISPLAY_STAGE = new Map([
  [4, 2],
  [5, 4],
]);

export interface FogDistributionCluster {
  id: string;
  center: [number, number];
  cellCount: number;
  maxDisplayStage: number;
  intensity: number;
  radiusM: number;
}

export interface FogRasterCell extends FogLayerCell {
  displayStage: number;
  fillOpacity: number;
}

export type FogCoverageBounds = [
  [south: number, west: number],
  [north: number, east: number],
];

export function buildFogCoverageBounds(
  cells: FogLayerCell[],
  paddingDegrees = 0.6,
): FogCoverageBounds | undefined {
  const positions = cells.flatMap((cell) => cell.positions);
  if (positions.length === 0) return undefined;

  const latitudes = positions.map(([latitude]) => latitude);
  const longitudes = positions.map(([, longitude]) => longitude);

  return [
    [
      Math.min(...latitudes) - paddingDegrees,
      Math.min(...longitudes) - paddingDegrees,
    ],
    [
      Math.max(...latitudes) + paddingDegrees,
      Math.max(...longitudes) + paddingDegrees,
    ],
  ];
}

function gridCoordinate(id: string): [number, number] | null {
  const match = /^(\d+)-(\d+)$/.exec(id);
  if (!match) return null;
  return [Number(match[1]), Number(match[2])];
}

export function buildFogRasterCells(cells: FogLayerCell[]): FogRasterCell[] {
  const fogCells = cells.filter((cell) =>
    FOG_CLASS_TO_DISPLAY_STAGE.has(cell.fogClass),
  );
  const occupied = new Set(fogCells.map((cell) => cell.id));

  return fogCells.map((cell) => {
    const coordinate = gridCoordinate(cell.id);
    let neighborCount = 1;

    if (coordinate) {
      neighborCount = 0;
      for (let rowOffset = -1; rowOffset <= 1; rowOffset += 1) {
        for (let columnOffset = -1; columnOffset <= 1; columnOffset += 1) {
          if (
            occupied.has(
              `${coordinate[0] + rowOffset}-${coordinate[1] + columnOffset}`,
            )
          ) {
            neighborCount += 1;
          }
        }
      }
    }

    const displayStage =
      cell.fogClass === 5
        ? Math.min(6, 2 + Math.floor(neighborCount / 2))
        : Math.min(3, 1 + Math.floor(neighborCount / 3));

    return {
      ...cell,
      displayStage,
      fillOpacity: Math.min(0.64, 0.28 + displayStage * 0.06),
    };
  });
}

function hashId(value: string) {
  return [...value].reduce(
    (hash, character) => (hash * 31 + character.charCodeAt(0)) >>> 0,
    7,
  );
}

export function buildFogBlobPositions(
  cluster: FogDistributionCluster,
): Array<[number, number]> {
  const [centerLatitude, centerLongitude] = cluster.center;
  const seed = (hashId(cluster.id) % 360) * (Math.PI / 180);
  const rotation = seed * 0.37;
  const latitudeMetersPerDegree = 111_320;
  const longitudeMetersPerDegree =
    latitudeMetersPerDegree * Math.cos(centerLatitude * (Math.PI / 180));

  return Array.from({ length: BLOB_POINT_COUNT }, (_, index) => {
    const angle = (index / BLOB_POINT_COUNT) * Math.PI * 2;
    const undulation =
      0.84 +
      Math.sin(angle * 3 + seed) * 0.13 +
      Math.sin(angle * 5 + seed * 0.61) * 0.07;
    const horizontal = Math.cos(angle) * cluster.radiusM * undulation * 1.18;
    const vertical = Math.sin(angle) * cluster.radiusM * undulation * 0.86;
    const rotatedHorizontal =
      horizontal * Math.cos(rotation) - vertical * Math.sin(rotation);
    const rotatedVertical =
      horizontal * Math.sin(rotation) + vertical * Math.cos(rotation);

    return [
      centerLatitude + rotatedVertical / latitudeMetersPerDegree,
      centerLongitude + rotatedHorizontal / longitudeMetersPerDegree,
    ];
  });
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
  const buckets = new Map<string, { latitudeTotal: number; longitudeTotal: number; cellCount: number; maxDisplayStage: number }>();

  cells.forEach((cell) => {
    const displayStage = FOG_CLASS_TO_DISPLAY_STAGE.get(cell.fogClass);
    if (!displayStage) return;
    const center = cellCenter(cell.positions);
    if (!center) return;
    const [latitude, longitude] = center;
    const key = `${Math.round(latitude / LATITUDE_BUCKET_DEGREES)}:${Math.round(longitude / LONGITUDE_BUCKET_DEGREES)}`;
    const bucket = buckets.get(key) ?? { latitudeTotal: 0, longitudeTotal: 0, cellCount: 0, maxDisplayStage: 0 };
    bucket.latitudeTotal += latitude;
    bucket.longitudeTotal += longitude;
    bucket.cellCount += 1;
    bucket.maxDisplayStage = Math.max(bucket.maxDisplayStage, displayStage);
    buckets.set(key, bucket);
  });

  return [...buckets.entries()].map(([id, bucket]) => {
    const density = Math.sqrt(bucket.cellCount);
    return {
      id,
      center: [bucket.latitudeTotal / bucket.cellCount, bucket.longitudeTotal / bucket.cellCount],
      cellCount: bucket.cellCount,
      maxDisplayStage: bucket.maxDisplayStage,
      intensity: Math.min(1, 0.45 + Math.log2(bucket.cellCount + 1) * 0.12),
      radiusM: Math.min(MAX_RADIUS_M, Math.max(MIN_RADIUS_M, MIN_RADIUS_M + density * 1_200)),
    };
  });
}
