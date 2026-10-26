import type { StationCurrentStatus, StationForecastStatus } from './types';

const SUCCESS_STATUSES = new Set(['OK', 'SUCCESS', 'GOOD', 'FRESH', 'RETRY_SUCCESS']);

export function normalizeCurrentStatus(status?: string): StationCurrentStatus {
  const normalized = status?.toUpperCase();

  if (normalized && SUCCESS_STATUSES.has(normalized)) return 'GOOD';
  if (normalized === 'STALE' || normalized === 'DELAYED' || normalized === 'FAIL') return 'DELAYED';
  if (normalized === 'MISSING') return 'MISSING';
  if (normalized === 'ERROR' || normalized === 'FAILED' || normalized === 'UNAVAILABLE') return 'UNAVAILABLE';
  return 'UNKNOWN';
}

export function normalizeForecastStatus(status?: string): StationForecastStatus {
  const normalized = status?.toUpperCase();

  if (normalized && SUCCESS_STATUSES.has(normalized)) return 'GOOD';
  if (normalized === 'STALE' || normalized === 'DELAYED') return 'DELAYED';
  if (
    normalized === 'FAIL'
    || normalized === 'FAILED'
    || normalized === 'MISSING'
    || normalized === 'ERROR'
    || normalized === 'UNAVAILABLE'
    || normalized === 'NOT_AVAILABLE'
  ) return 'NOT_AVAILABLE';
  return 'UNKNOWN';
}

export function isForecastAvailable(status?: string) {
  return normalizeForecastStatus(status) === 'GOOD';
}
