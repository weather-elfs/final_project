import type { MapViewport } from '../../api';
import { normalizeCurrentStatus, normalizeForecastStatus } from './stationStatus';
import type { DashboardConfig, DashboardData, DashboardStation, SourceStatusDetail } from './types';

function camelizeKey(key: string) {
  return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

export function toViewModel<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((item) => toViewModel(item)) as T;
  if (!value || typeof value !== 'object') return value as T;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [camelizeKey(key), toViewModel(item)]),
  ) as T;
}

export function toDashboardConfig(payload: unknown): DashboardConfig {
  const config = toViewModel<DashboardConfig & { forecastIntervalsH?: number[] }>(payload);
  return {
    ...config,
    stations: (config.stations ?? [])
      .filter((station) => station.available !== false)
      .map((station) => ({
        ...station,
        id: station.stationId,
        name: station.stationName,
        currentStatus: normalizeCurrentStatus(station.currentStatus),
        forecastStatus: normalizeForecastStatus(station.forecastStatus),
      })),
    missionTypes: (config.missionTypes ?? []).filter((mission) => mission.enabled),
    forecastIntervalOptionsH: config.forecastIntervalOptionsH ?? config.forecastIntervalsH ?? [],
  };
}

export function toDashboardData(payload: unknown): DashboardData {
  const data = toViewModel<Omit<DashboardData, 'sourceStatus'> & {
    sourceStatus?: SourceStatusDetail[] | Record<string, Omit<SourceStatusDetail, 'source'>>;
  }>(payload);
  const sourceStatus = Array.isArray(data.sourceStatus)
    ? data.sourceStatus
    : Object.entries(data.sourceStatus ?? {}).map(([source, detail]) => ({
        source,
        ...(detail as Omit<SourceStatusDetail, 'source'>),
      }));

  const summary = sourceStatus.reduce(
    (counts, source) => {
      const status = source.status.toUpperCase();
      if (status === 'OK' || status === 'FRESH') counts.good += 1;
      else if (status === 'STALE' || status === 'DELAYED') counts.delayed += 1;
      else counts.fail += 1;
      return counts;
    },
    { good: 0, delayed: 0, fail: 0 },
  );

  return {
    ...data,
    sourceStatus,
    apiStatus: data.apiStatus ?? {
      overall: {
        code: summary.fail ? 'FAIL' : summary.delayed ? 'DELAYED' : 'GOOD',
        label: summary.fail ? 'Fail' : summary.delayed ? 'Delayed' : 'Good',
      },
      summary,
      sources: sourceStatus.map((source) => ({
        source: source.source,
        displayName: source.source.toUpperCase(),
        code: source.status,
        label: source.status,
      })),
    },
  };
}

export function stationsInViewport(stations: DashboardStation[], viewport: MapViewport | null) {
  if (!viewport) return stations;
  return stations.filter((station) => (
    station.longitude >= viewport.west
    && station.longitude <= viewport.east
    && station.latitude >= viewport.south
    && station.latitude <= viewport.north
  ));
}
