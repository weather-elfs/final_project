import { gk2aFogLayer } from '../../mocks/gk2aFogLayer';
import { toViewModel } from './dashboardAdapter';
import type { FogMapLayer, ForecastPoint } from './types';

export interface ForecastFogFrame {
  horizonH: number;
  validAt?: string;
  layer: FogMapLayer;
}

const LATITUDE_DRIFT_PER_FRAME = -0.024;
const LONGITUDE_DRIFT_PER_FRAME = 0.085;
const DEMO_FORECAST_FOG_LAYER = toViewModel<FogMapLayer>(gk2aFogLayer);

// 예측 지도 음영 전용이다. API의 현재 관측·예측 수치나 config는 변경하지 않는다.
export function buildForecastFogDemoFrames(
  currentLayer: FogMapLayer | undefined,
  forecastTimeline: ForecastPoint[],
): ForecastFogFrame[] {
  return buildMockForecastFogFrames(currentLayer ?? DEMO_FORECAST_FOG_LAYER, forecastTimeline);
}

export function interpolateFogMapLayer(
  fromLayer: FogMapLayer,
  toLayer: FogMapLayer,
  progress: number,
): FogMapLayer {
  const ratio = Math.min(1, Math.max(0, progress));
  const fromCells = new Map(fromLayer.cells.map((cell) => [cell.id, cell]));

  return {
    ...toLayer,
    cells: toLayer.cells.map((toCell) => {
      const fromCell = fromCells.get(toCell.id);
      if (!fromCell) return toCell;

      return {
        ...toCell,
        positions: toCell.positions.map((toPosition, positionIndex) => {
          const fromPosition = fromCell.positions[positionIndex];
          if (!fromPosition) return toPosition;

          return [
            fromPosition[0] + (toPosition[0] - fromPosition[0]) * ratio,
            fromPosition[1] + (toPosition[1] - fromPosition[1]) * ratio,
          ] as [number, number];
        }),
      };
    }),
  };
}

export function buildMockForecastFogFrames(
  currentLayer: FogMapLayer | undefined,
  forecastTimeline: ForecastPoint[],
): ForecastFogFrame[] {
  if (!currentLayer) return [];

  return forecastTimeline.flatMap((point, frameIndex) => {
    if (point.horizonH == null) return [];

    const step = frameIndex + 1;
    const cells = currentLayer.cells.map((cell, cellIndex) => {
      const latitudeVariation =
        Math.sin((cellIndex + 1) * 1.7 + step * 0.8) * 0.006;
      const longitudeVariation =
        Math.cos((cellIndex + 1) * 1.3 + step * 0.65) * 0.009;

      return {
        ...cell,
        fogClass:
          cell.fogClass === 5 && (cellIndex + step) % 7 === 0
            ? 4
            : cell.fogClass,
        positions: cell.positions.map(
          ([latitude, longitude]) =>
            [
              latitude + LATITUDE_DRIFT_PER_FRAME * step + latitudeVariation,
              longitude +
                LONGITUDE_DRIFT_PER_FRAME * step +
                longitudeVariation,
            ] as [number, number],
        ),
      };
    });

    return [
      {
        horizonH: point.horizonH,
        validAt: point.validAt,
        layer: {
          ...currentLayer,
          source: `${currentLayer.source} 목 예측`,
          observedAt: point.validAt ?? currentLayer.observedAt,
          cells,
        },
      },
    ];
  });
}
