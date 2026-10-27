import type { StationCurrentStatus, StationForecastStatus } from './types';

const SUCCESS_STATUSES = new Set(['OK', 'SUCCESS', 'GOOD', 'FRESH', 'RETRY_SUCCESS']);

export const DATA_SOURCE_LABELS: Record<string, string> = {
  ASOS: '기상청 ASOS', AIRKOREA: '에어코리아 관측', TIDE_OBSERVATORY: '국립해양조사원',
  KMA_FORECAST: '기상청 예보', AIRKOREA_FORECAST: '에어코리아 예보',
};

export const SOURCE_FAILURE_MESSAGES: Record<string, string> = {
  TIMEOUT: '응답 시간이 초과됐습니다.',
  COLLECTION_FAILED: '응답을 받지 못했습니다.',
  EMPTY_DATA: '받은 자료가 없습니다.',
  TARGET_TIME_MISSING_OR_STALE: '해당 시점의 예보가 없거나 오래됐습니다.',
  STALE_OR_FUTURE_OBSERVATION: '사용할 수 있는 최신 관측이 없습니다.',
  BASELINE_MISSING: '예측 기준이 되는 일부 관측값이 없습니다.',
  UPSTREAM_COMMUNICATION_FAILURE: '에어코리아 관측소에서 미세먼지 통신장애를 보고했습니다.',
  UPSTREAM_COMMUNICATION_FAILURE_REUSED: '에어코리아 관측소 통신장애로 2시간 이내 이전 정상 관측값을 사용합니다.',
  PREVIOUS_OBSERVATION_USED: '2시간 이내 이전 정상 관측값을 사용합니다.',
};

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
