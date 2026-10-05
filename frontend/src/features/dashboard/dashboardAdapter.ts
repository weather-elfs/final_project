import type { MapViewport } from '../../api';
import type { DashboardConfig, DashboardStation } from './types';

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
  const config = toViewModel<DashboardConfig>(payload);
  return {
    ...config,
    stations: (config.stations ?? [])
      .filter((station) => station.available !== false)
      .map((station) => ({ ...station, id: station.stationId, name: station.stationName })),
    missionTypes: (config.missionTypes ?? []).filter((mission) => mission.enabled),
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
