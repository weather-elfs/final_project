import { DEMO_CENTER, DEMO_MODE, demoAlertOperations, demoHistory, matchesDemoLogin } from './demo';

const SUCCESS_CODES = new Set(['SUCCESS', 'PARTIAL_SUCCESS']);

export interface ApiEnvelope<T> {
  code: string;
  message?: string;
  data: T;
  meta?: { request_id?: string };
}

interface ApiErrorOptions {
  code?: string;
  data?: unknown;
  requestId?: string | null;
  status?: number;
}

export interface DashboardRequest {
  stationId: string;
  forecastIntervalH: number;
  missionType: string;
  asOf?: string;
  mock?: boolean;
}

export interface HistoryRequest {
  historyType?: string;
  missionType?: string;
}

export interface MapViewport {
  west: number;
  south: number;
  east: number;
  north: number;
  zoom: number;
}

export type MapBounds = Omit<MapViewport, 'zoom'>;

export class ApiError extends Error {
  code: string;
  data: unknown;
  requestId: string | null;
  status: number;

  constructor(message: string, { code = 'REQUEST_FAILED', data = null, requestId = null, status = 0 }: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.data = data;
    this.requestId = requestId;
    this.status = status;
  }
}

export async function request<T>(url: string, options: RequestInit = {}): Promise<ApiEnvelope<T>> {
  const { signal = AbortSignal.timeout(10_000), ...fetchOptions } = options;
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...fetchOptions,
    signal,
    headers: { Accept: 'application/json', ...fetchOptions.headers },
  });

  let payload: ApiEnvelope<T>;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('서버 응답 형식을 확인할 수 없습니다.', {
      code: 'INVALID_RESPONSE',
      status: response.status,
    });
  }

  if (!response.ok || !SUCCESS_CODES.has(payload?.code)) {
    const errorData = payload?.data as { meta?: { request_id?: string } } | null;
    const detail = (payload as ApiEnvelope<T> & { detail?: string })?.detail;
    throw new ApiError(payload?.message || detail || '요청을 처리하지 못했습니다.', {
      code: payload?.code,
      data: payload?.data,
      requestId: errorData?.meta?.request_id ?? payload?.meta?.request_id ?? null,
      status: response.status,
    });
  }

  return payload;
}

export function buildDashboardUrl({ stationId, forecastIntervalH, missionType, asOf, mock }: DashboardRequest) {
  const query = new URLSearchParams({
    forecast_interval_h: String(forecastIntervalH),
    mission_type: missionType,
  });

  if (asOf) query.set('as_of', asOf);
  if (mock != null) query.set('mock', String(mock));

  return `/api/v1/stations/${encodeURIComponent(stationId)}/dashboard?${query}`;
}

export function buildDashboardConfigUrl({ south, west, north, east }: MapBounds) {
  const query = new URLSearchParams({
    south: String(south),
    west: String(west),
    north: String(north),
    east: String(east),
  });

  return `/api/v1/dashboard/config?${query}`;
}

export function buildHistoryUrl({ historyType, missionType }: HistoryRequest = {}) {
  const query = new URLSearchParams();
  if (historyType && historyType !== 'ALL') query.set('history_type', historyType);
  if (missionType && missionType !== 'ALL') query.set('mission_type', missionType);
  const suffix = query.toString();
  return `/api/v1/history${suffix ? `?${suffix}` : ''}`;
}

export async function login(centerId: string, password: string, options?: RequestInit) {
  if (DEMO_MODE) {
    options?.signal?.throwIfAborted();
    if (!matchesDemoLogin(centerId, password)) {
      throw new ApiError('시연용 센터 ID와 비밀번호를 확인하세요.', { code: 'INVALID_DEMO_ACCESS', status: 401 });
    }
    return { code: 'SUCCESS', message: '시연 화면에 진입합니다.', data: { center: { ...DEMO_CENTER } } };
  }
  return request<{ center: { id: string; name: string } }>('/api/v1/auth/login', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    body: JSON.stringify({ center_id: centerId, password }),
  });
}

export function getDashboardConfig(bounds: MapBounds, options?: RequestInit) {
  return request<unknown>(buildDashboardConfigUrl(bounds), options);
}

export function getDashboard(params: DashboardRequest, options?: RequestInit) {
  const timeout = AbortSignal.timeout(60_000);
  return request<unknown>(buildDashboardUrl(params), {
    ...options,
    cache: 'no-store',
    signal: options?.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
  });
}

export async function getAlertOperations(options?: RequestInit) {
  if (DEMO_MODE) {
    options?.signal?.throwIfAborted();
    return demoAlertOperations();
  }
  return request<unknown>('/api/v1/alerts/operations', options);
}

export async function getHistory(params: HistoryRequest = {}, options?: RequestInit) {
  if (DEMO_MODE) {
    options?.signal?.throwIfAborted();
    return demoHistory(params);
  }
  return request<unknown>(buildHistoryUrl(params), options);
}
