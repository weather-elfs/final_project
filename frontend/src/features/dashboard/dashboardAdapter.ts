import type { MapViewport } from '../../api';
import { isFiniteNumber } from './formatters';
import { normalizeCurrentStatus, normalizeForecastStatus } from './stationStatus';
import type { DashboardConfig, DashboardData, DashboardStation, SourceStatusDetail } from './types';

const WIND_DIRECTIONS = ['북풍', '북북동풍', '북동풍', '동북동풍', '동풍', '동남동풍', '남동풍', '남남동풍', '남풍', '남남서풍', '남서풍', '서남서풍', '서풍', '서북서풍', '북서풍', '북북서풍'];
// 기상청 단기예보 SKY·PTY 코드: https://www.weather.go.kr/w/resources/pdf/dongnaeforecast_1hr_rss.pdf
const SKY_LABELS: Record<number, string> = { 1: '맑음', 3: '구름많음', 4: '흐림' };
const PRECIPITATION_LABELS: Record<number, string> = { 1: '비', 2: '비 또는 눈', 3: '눈', 4: '소나기' };

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
    forecastTimeline: data.forecastTimeline?.map((point) => {
      const input = data.meta?.forecasts?.find((item) => item.horizonH === point.horizonH
        && item.validAt && point.validAt && Date.parse(item.validAt) === Date.parse(point.validAt));
      const values = input?.values;
      const direction = values?.futureFcstWindDir;
      const sky = values?.futureFcstSky;
      const precipitation = values?.futureFcstPty;
      return {
        temperatureC: values?.futureFcstTemp,
        windSpeedMS: values?.futureFcstWindSpeed,
        windDirectionDeg: direction,
        windDirectionLabel: isFiniteNumber(direction) && direction >= 0 && direction <= 360
          ? WIND_DIRECTIONS[Math.floor((direction % 360 + 11.25) / 22.5) % 16] : undefined,
        weatherLabel: precipitation === 0 && isFiniteNumber(sky) ? SKY_LABELS[sky]
          : isFiniteNumber(precipitation) ? PRECIPITATION_LABELS[precipitation] : undefined,
        ...point,
      };
    }),
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
