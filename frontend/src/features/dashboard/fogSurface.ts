import { buildFogRasterCells, type FogCoverageBounds } from './fogDistribution';
import type { FogLayerCell } from './types';

const SURFACE_SIZE = 512;
const KERNEL_RADIUS = 3.5;
const SMOOTHING_CELL_WIDTHS = 2.8;
const DEGREES_TO_RADIANS = Math.PI / 180;
const SURFACE_COLORS = [
  [116, 215, 247],
  [158, 255, 145],
  [255, 201, 5],
  [255, 130, 5],
  [240, 34, 0],
  [137, 9, 151],
  [100, 0, 21],
] as const;

export interface FogSurface {
  bounds: FogCoverageBounds;
  width: number;
  height: number;
  pixels: Uint8ClampedArray;
}

function projectLatitude(latitude: number) {
  return Math.asinh(Math.tan(latitude * DEGREES_TO_RADIANS));
}

function unprojectLatitude(projected: number) {
  return Math.atan(Math.sinh(projected)) / DEGREES_TO_RADIANS;
}

/** Interpolate the retained fog samples into one continuous Mercator surface. */
export function buildFogSurface(cells: FogLayerCell[]): FogSurface | undefined {
  const samples = buildFogRasterCells(cells).flatMap((cell) => {
    const positions = cell.positions.filter(
      ([latitude, longitude]) =>
        Number.isFinite(latitude) &&
        Number.isFinite(longitude) &&
        Math.abs(latitude) < 85 &&
        Math.abs(longitude) <= 180,
    );
    if (positions.length < 3) return [];

    const xs = positions.map(([, longitude]) => longitude * DEGREES_TO_RADIANS);
    const ys = positions.map(([latitude]) => projectLatitude(latitude));
    const west = Math.min(...xs);
    const east = Math.max(...xs);
    const south = Math.min(...ys);
    const north = Math.max(...ys);
    const cellSize = Math.max(east - west, north - south);
    if (cellSize <= 0) return [];

    return [
      {
        x: (west + east) / 2,
        y: (south + north) / 2,
        cellSize,
        level: cell.displayStage,
      },
    ];
  });
  if (samples.length === 0) return undefined;

  const cellSizes = samples
    .map((sample) => sample.cellSize)
    .sort((a, b) => a - b);
  const cellSize = cellSizes[Math.floor(cellSizes.length / 2)]!;
  const sigma = cellSize * SMOOTHING_CELL_WIDTHS;
  const padding = sigma * KERNEL_RADIUS;
  const west = Math.min(...samples.map((sample) => sample.x)) - padding;
  const east = Math.max(...samples.map((sample) => sample.x)) + padding;
  const south = Math.min(...samples.map((sample) => sample.y)) - padding;
  const north = Math.max(...samples.map((sample) => sample.y)) + padding;
  const scale = (SURFACE_SIZE - 1) / Math.max(east - west, north - south);
  const width = Math.max(2, Math.round((east - west) * scale) + 1);
  const height = Math.max(2, Math.round((north - south) * scale) + 1);
  const stepX = (east - west) / (width - 1);
  const stepY = (north - south) / (height - 1);
  const density = new Float32Array(width * height);
  const weightedLevels = new Float32Array(width * height);

  // Accumulate scalar values first. Coloring separate shapes would leave seams.
  for (const sample of samples) {
    const centerX = (sample.x - west) / stepX;
    const centerY = (north - sample.y) / stepY;
    const sigmaX = sigma / stepX;
    const sigmaY = sigma / stepY;
    const startX = Math.max(0, Math.floor(centerX - KERNEL_RADIUS * sigmaX));
    const endX = Math.min(
      width - 1,
      Math.ceil(centerX + KERNEL_RADIUS * sigmaX),
    );
    const startY = Math.max(0, Math.floor(centerY - KERNEL_RADIUS * sigmaY));
    const endY = Math.min(
      height - 1,
      Math.ceil(centerY + KERNEL_RADIUS * sigmaY),
    );
    const horizontalWeights = new Float32Array(endX - startX + 1);

    for (let x = startX; x <= endX; x += 1) {
      horizontalWeights[x - startX] = Math.exp(
        -0.5 * ((x - centerX) / sigmaX) ** 2,
      );
    }
    for (let y = startY; y <= endY; y += 1) {
      const verticalWeight = Math.exp(-0.5 * ((y - centerY) / sigmaY) ** 2);
      for (let x = startX; x <= endX; x += 1) {
        const weight = horizontalWeights[x - startX]! * verticalWeight;
        const index = y * width + x;
        density[index] = density[index]! + weight;
        weightedLevels[index] = weightedLevels[index]! + weight * sample.level;
      }
    }
  }

  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < density.length; index += 1) {
    const weight = density[index]!;
    if (weight <= 0) continue;

    const coverage = 1 - Math.exp(-weight / 2.2);
    const level = Math.min(6, (weightedLevels[index]! / weight) * coverage);
    const lowerIndex = Math.min(SURFACE_COLORS.length - 2, Math.floor(level));
    const lower = SURFACE_COLORS[lowerIndex]!;
    const upper = SURFACE_COLORS[lowerIndex + 1]!;
    const fraction = level - lowerIndex;
    const blend = fraction * fraction * (3 - 2 * fraction);

    for (let channel = 0; channel < 3; channel += 1) {
      pixels[index * 4 + channel] =
        lower[channel]! + (upper[channel]! - lower[channel]!) * blend;
    }
    pixels[index * 4 + 3] = (1 - Math.exp(-weight / 0.18)) * 86;
  }

  return {
    bounds: [
      [unprojectLatitude(south), west / DEGREES_TO_RADIANS],
      [unprojectLatitude(north), east / DEGREES_TO_RADIANS],
    ],
    width,
    height,
    pixels,
  };
}
